"""Aclaraciones del mismo chat: persistencia con begin/finish_chat_turn existentes."""

import base64
from copy import deepcopy

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.chat import Plan
from app.services.analysis_worker import run_calculation
from app.services.planning_errors import PlanningError
from app.services.statistics.methods import normalized
from app.services.statistics.preparation import key, plan_filters

LIMIT_NAMES = ["max_file_bytes", "max_rows", "max_columns", "max_expanded_bytes", "missing_value_markers"]
EXECUTION_ACTIONS = {
    "prepare_execution": "Preparar el análisis aceptado",
    "clarify_execution": "Responder aclaración de ejecución",
    "review_execution": "Revisar una respuesta de ejecución",
    "request_descriptive": "Solicitar una propuesta descriptiva alternativa",
    "cancel_execution": "Dejar pendiente el análisis",
}


def normalized_preparation(state):
    """Adaptación de estados ya persistidos por la versión anterior, sin reescrituras."""
    state = deepcopy(state or {})
    result = state.get("result", {})
    questions = result.get("questions", [])
    clarifications = result.setdefault("clarifications", [])
    for q in questions:
        if not any(c["id"] == q["id"] for c in clarifications):
            answer = state.get("answers", {}).get(q["id"])
            clarifications.append(
                {
                    **q,
                    "status": "unknown" if answer == "unknown" else "pending",
                    "answer": answer,
                    "limitation": q.get("limitation")
                    or "No tenemos información suficiente para resolver esta decisión. " + q["explanation"],
                }
            )
    result["questions"] = [
        q for q in questions if not any(c["id"] == q["id"] and c["status"] == "unknown" for c in clarifications)
    ]
    if (
        result.get("status") not in {"UNSUPPORTED", "PARTIALLY_READY", "COMPLETED"}
        and any(c["status"] == "unknown" for c in clarifications)
        and not state.get("review_question_id")
    ):
        result["status"] = "BLOCKED_UNCERTAINTY"
    return state


def preparation_message(preparation):
    if preparation["status"] == "COMPLETED":
        return "Todos los componentes compatibles de este plan ya están completados. Conservamos sus resultados; no es necesario recalcularlos."
    if preparation["status"] == "PARTIALLY_READY":
        return "He preparado tu análisis integral. Algunos procedimientos pueden ejecutarse, pero otros necesitan información adicional. Revisa los estados y confirma «Ejecutar componentes disponibles» para realizar una ejecución parcial. No se ejecutarán los componentes pendientes."
    if preparation["status"] == "READY":
        if any(c["status"] == "COMPLETED" for c in preparation.get("components", [])):
            return "Los componentes pendientes están preparados. Conservamos los resultados compatibles anteriores. Revisa y confirma «Ejecutar componentes pendientes» para completar el plan."
        return "Análisis preparado. Revisa el resumen y confirma «Ejecutar análisis» cuando quieras calcular. Aún no se ha ejecutado ningún cálculo estadístico."
    if preparation["status"] == "UNSUPPORTED":
        return "No puedo ejecutar este plan con las condiciones actuales. " + " ".join(preparation["blockers"])
    if preparation["status"] == "BLOCKED_UNCERTAINTY":
        return (
            " ".join(
                dict.fromkeys(
                    q.get("limitation") or q["explanation"]
                    for q in preparation.get("clarifications", [])
                    if q["status"] == "unknown"
                )
            )
            + " Tu respuesta «No lo sé» está guardada; no volveré a preguntarlo automáticamente. Puedes solicitar una propuesta descriptiva alternativa, revisar tu respuesta o dejar pendiente el análisis."
        )
    if not preparation["questions"]:
        return "Hay componentes pendientes. Revisa sus motivos y las respuestas metodológicas para continuar."
    q = preparation["questions"][0]
    return q["prompt"] + " " + q["explanation"]


def text_answer(question, text):
    text = normalized(text).strip(".¡!¿? ")
    selected = next((c["value"] for c in question["choices"] if normalized(c["label"]) == text), None)
    aliases = {
        "yes": {"si", "si lo confirmo"},
        "no": {"no", "son observaciones relacionadas"},
        "missing": {
            "son datos faltantes",
            "son ausencias",
            "es informacion faltante",
            "representan informacion faltante",
        },
        "retained": {"es una categoria valida", "son categorias validas", "son valores validos"},
        "continuous": {"son cantidades", "son medidas cuantitativas"},
        "nominal": {"son codigos", "son categorias sin orden"},
        "unknown": {
            "no se",
            "no lo se",
            "no conozco el significado de esos codigos",
            "no entiendo que significa independencia",
            "no se si esos valores son datos faltantes",
            "no se que metodo corresponde",
            "haz el analisis que consideres apropiado",
        },
    }
    return selected or next((c["value"] for c in question["choices"] if text in aliases.get(c["value"], set())), None)


async def originals_for(store, project, conversation, plan, settings):
    links = await store.rows("conversation_files", {"conversation_id": conversation["id"], "project_id": project["id"]})
    ids = {v.file_id for v in plan.variables}
    if not ids <= {link["file_id"] for link in links}:
        raise HTTPException(422, "Un archivo del plan ya no está asociado a la conversación.")
    files = await store.rows("project_files", {"project_id": project["id"], "id": sorted(ids)})
    if len(files) != len(ids) or not 1 <= len(files) <= 4:
        raise HTTPException(422, "La preparación admite de 1 a 4 datasets accesibles.")
    total, originals = 0, []
    for file in files:
        if file["file_role"] != "dataset":
            raise HTTPException(422, "Solo los datasets pueden suministrar observaciones estadísticas.")
        data = await store.download(file["storage_path"], max_bytes=min(settings.max_file_bytes, 10 * 1024 * 1024))
        total += len(data)
        if total > 20 * 1024 * 1024:
            raise HTTPException(413, "Los originales exceden el límite conjunto de 20 MB.")
        originals.append(
            {
                **{k: file[k] for k in ["id", "original_name", "file_type", "metadata"]},
                "data": base64.b64encode(data).decode("ascii"),
            }
        )
    return originals


def preparation_context(project, conversation, answers):
    return {
        "answers": answers,
        "clarifications": (conversation.get("stage_data", {}).get("execution_preparation") or {})
        .get("result", {})
        .get("clarifications", []),
        "thesis": project.get("project_type") == "thesis",
        "independence_evidence": conversation.get("stage_data", {}).get("independence_evidence", []),
    }


async def execution_history(store, conversation, proposal):
    compatible, offset = [], 0
    while True:
        page = await store.rows(
            "analysis_runs",
            {"conversation_id": conversation["id"], "proposal_id": proposal["id"]},
            order="created_at.asc,id.asc",
            limit=100,
            offset=offset,
            select="id,status,result_status:result->>status,component_states:result->component_states,plan_snapshot:result->plan_snapshot",
        )
        for run in page:
            result = run.get("result") or (run if run.get("result_status") else None)
            if result and result.get("plan_snapshot") == proposal["analysis_plan"]:
                compatible.append(
                    {"id": run["id"], "status": run["status"], "components": result.get("component_states") or []}
                )
        if len(page) < 100:
            break
        offset += len(page)
    return {
        "completed_components": [
            {**component, "completed_run_id": run["id"]}
            for run in compatible
            for component in run["components"]
            if component["status"] == "COMPLETED" and component.get("completed_run_id") in (None, run["id"])
        ],
        "previous_runs": [{"id": r["id"], "status": r["status"]} for r in compatible],
    }


async def preparation_turn(store, project, conversation, turn, settings):
    data = dict(conversation.get("stage_data", {}))
    previous = normalized_preparation(data.get("execution_preparation"))
    data["execution_preparation"] = previous or None

    def result(content, preparation=None):
        return {
            "stage": conversation["current_stage"],
            "content": content,
            "message_type": "question",
            "stage_data": data,
            "proposals": [],
            "metadata": {"execution_preparation": preparation},
        }

    if turn.action == "cancel_execution":
        previous["paused"] = True
        previous["review_question_id"] = None
        return result(
            "Dejamos pendiente el análisis y conservamos el plan y tus respuestas. Puedes seguir conversando o volver a prepararlo cuando tengas más información."
        )
    proposal_id = str(turn.proposal_id) if turn.proposal_id else previous.get("proposal_id")
    if not proposal_id:
        raise HTTPException(422, "Selecciona una propuesta aceptada para preparar el análisis.")
    proposal = await store.one("analysis_proposals", {"id": proposal_id, "conversation_id": conversation["id"]})
    if proposal["status"] != "accepted":
        raise HTTPException(409, "Solo se pueden preparar propuestas aceptadas.")
    try:
        plan = Plan.model_validate(proposal["analysis_plan"])
    except ValidationError:
        raise HTTPException(
            422, "El plan antiguo no tiene un contrato válido. Solicita una propuesta revisada."
        ) from None
    archives = dict(data.get("execution_preparations", {}))
    if previous.get("proposal_id") and previous["proposal_id"] != proposal_id:
        archives[previous["proposal_id"]] = previous
        previous = normalized_preparation(archives.get(proposal_id)) or previous
    data["execution_preparations"] = archives
    answers = dict(previous.get("answers", {}))
    questions = previous.get("result", {}).get("questions", [])
    clarifications = previous.get("result", {}).get("clarifications", [])
    reviewing = previous.get("review_question_id") if previous.get("proposal_id") == proposal_id else None
    if turn.action == "message" and (
        previous.get("result", {}).get("status") == "BLOCKED_UNCERTAINTY"
        or previous.get("result", {}).get("status") == "PARTIALLY_READY"
        and not questions
    ):
        return result(preparation_message(previous["result"]), previous["result"])
    if turn.action == "review_execution":
        q = next((q for q in clarifications if q["id"] == turn.question_id), None)
        if not q:
            raise HTTPException(
                409, "Esa aclaración ya no corresponde a esta preparación. Vuelve a preparar el análisis."
            )
        reviewing = q["id"]
    if turn.action == "clarify_execution" or turn.action == "message":
        q = (
            next((q for q in clarifications if q["id"] == turn.question_id), None)
            if turn.question_id
            else next(iter(questions), None)
        )
        if not q:
            if turn.action == "message" and previous.get("result", {}).get("status") == "BLOCKED_UNCERTAINTY":
                return result(preparation_message(previous["result"]), previous["result"])
            raise HTTPException(409, "Esta pregunta ya no está pendiente. Vuelve a preparar el análisis.")
        answer = turn.answer
        if turn.action == "message":
            answer = text_answer(q, turn.content)
        if answer not in {c["value"] for c in q["choices"]}:
            return result(
                "Para no interpretar mal tu respuesta, elige una opción de la pregunta pendiente. " + q["explanation"],
                previous.get("result"),
            )
        answers[q["id"]] = answer
        reviewing = None
    originals = await originals_for(store, project, conversation, plan, settings)
    context = preparation_context(
        project, {**conversation, "stage_data": {**data, "execution_preparation": previous}}, answers
    )
    context.update(await execution_history(store, conversation, proposal))
    output = await run_calculation(
        {
            "operation": "prepare",
            "proposal_id": proposal_id,
            "plan": proposal["analysis_plan"],
            "files": originals,
            "limits": {name: getattr(settings, name) for name in LIMIT_NAMES},
            "review_question_id": reviewing,
            **context,
        }
    )
    preparation = output["preparation"]
    # Solo se aplican decisiones vigentes. Los ids incluyen hashes/plan, por
    # lo que una modificación del original invalida automáticamente las respuestas.
    data["execution_preparation"] = {
        "proposal_id": proposal_id,
        "answers": answers,
        "result": preparation,
        "paused": False,
        "review_question_id": reviewing,
    }
    return result(preparation_message(preparation), preparation)


async def descriptive_request(store, conversation, turn):
    state = normalized_preparation(conversation.get("stage_data", {}).get("execution_preparation"))
    pid = str(turn.proposal_id) if turn.proposal_id else state.get("proposal_id")
    if not pid or state.get("proposal_id") != pid:
        raise HTTPException(409, "Selecciona el análisis original antes de solicitar la alternativa descriptiva.")
    proposal = await store.one("analysis_proposals", {"id": pid, "conversation_id": conversation["id"]})
    if proposal["status"] != "accepted":
        raise HTTPException(409, "El análisis original debe conservar su propuesta aceptada.")
    try:
        plan = Plan.model_validate(proposal["analysis_plan"])
    except ValidationError:
        raise HTTPException(422, "Revisa el contrato del plan original antes de solicitar una alternativa.") from None
    filters = list(plan_filters(plan))
    if plan.comparison and plan.comparison.strata:
        filters.append(plan.comparison.strata)
    return {
        "source_proposal_id": pid,
        "variables": [v.model_dump(mode="json") for v in plan.variables],
        "filters": [s.model_dump(mode="json") for s in filters],
        "clarifications": state.get("result", {}).get("clarifications", []),
    }


def bind_descriptive_scope(reply, request):
    """La nueva propuesta mantiene el alcance aceptado; no reutiliza inferencias."""
    if len(reply.proposals) != 1 or reply.clarification_required:
        raise PlanningError(
            "comparison_scope",
            "Devuelve una única propuesta descriptiva alternativa, sin preguntas sobre independencia.",
        )
    plan = reply.proposals[0]
    expected = {key(type(plan.variables[0]).model_validate(v)) for v in request["variables"]}
    if (
        plan.procedure not in {"descriptive", "exploratory"}
        or plan.comparison
        or plan.joins
        or plan.components
        or {key(v) for v in plan.variables} != expected
        or sum(v.role == "group" for v in plan.variables) > 1
        or not any(v.role != "group" for v in plan.variables)
    ):
        raise PlanningError(
            "comparison_scope",
            "La alternativa debe ser exclusivamente descriptiva, sin uniones, y conservar las mismas referencias de archivo, hoja y columna del análisis original.",
        )
    if plan.filters and [s.model_dump(mode="json") for s in plan.filters] != request["filters"]:
        raise PlanningError("comparison_scope", "La alternativa no puede cambiar los filtros del alcance aceptado.")
    # El servidor añade únicamente selecciones estructuradas ya aceptadas; se
    # validarán junto al resto del plan antes de persistir y de nuevo al aceptar.
    values = plan.model_dump(mode="json")
    values["filters"] = request["filters"]
    plan = Plan.model_validate(values)
    return reply.model_copy(
        update={
            "proposals": [plan],
            "questions": [],
            "clarification_required": False,
            "goal_change": False,
            "goal_change_reason": None,
            "detected_goal": None,
            "suggested_title": None,
        }
    )
