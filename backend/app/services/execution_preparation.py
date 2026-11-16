"""Aclaraciones del mismo chat: persistencia con begin/finish_chat_turn existentes."""

import base64

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.chat import Plan
from app.services.analysis_worker import run_calculation
from app.services.statistics.methods import normalized

LIMIT_NAMES = ["max_file_bytes", "max_rows", "max_columns", "max_expanded_bytes", "missing_value_markers"]


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
        "thesis": project.get("project_type") == "thesis",
        "independence_evidence": conversation.get("stage_data", {}).get("independence_evidence", []),
    }


async def preparation_turn(store, project, conversation, turn, settings):
    data = dict(conversation.get("stage_data", {}))
    previous = data.get("execution_preparation") or {}

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
        data["execution_preparation"] = None
        return result(
            "Dejamos pendiente la ejecución. El plan aceptado se conserva. Puedes solicitar una propuesta descriptiva o explicar cómo se recogieron los datos."
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
    answers = dict(previous.get("answers", {})) if previous.get("proposal_id") == proposal_id else {}
    questions = previous.get("result", {}).get("questions", []) if previous.get("proposal_id") == proposal_id else []
    if turn.action == "clarify_execution" or turn.action == "message":
        q = (
            next((q for q in questions if q["id"] == turn.question_id), None)
            if turn.question_id
            else next(iter(questions), None)
        )
        if not q:
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
    originals = await originals_for(store, project, conversation, plan, settings)
    context = preparation_context(project, conversation, answers)
    output = await run_calculation(
        {
            "operation": "prepare",
            "proposal_id": proposal_id,
            "plan": proposal["analysis_plan"],
            "files": originals,
            "limits": {name: getattr(settings, name) for name in LIMIT_NAMES},
            **context,
        }
    )
    preparation = output["preparation"]
    # Solo se aplican decisiones vigentes. Los ids incluyen hashes/plan, por
    # lo que una modificación del original invalida automáticamente las respuestas.
    data["execution_preparation"] = {"proposal_id": proposal_id, "answers": answers, "result": preparation}
    if preparation["status"] == "READY":
        content = "Análisis preparado. Revisa el resumen y confirma «Ejecutar análisis» cuando quieras calcular. Aún no se ha ejecutado ningún cálculo estadístico."
    elif preparation["status"] == "UNSUPPORTED":
        content = (
            "No puedo ejecutar este plan con las condiciones actuales. "
            + " ".join(preparation["blockers"])
            + " Puedes solicitar una propuesta descriptiva o revisar la propuesta."
        )
    else:
        q = preparation["questions"][0]
        content = q["prompt"] + " " + q["explanation"]
        if answers.get(q["id"]) == "unknown":
            content += " Si no lo sabes, conservaremos esta incertidumbre y no ejecutaremos el contraste. Puedes continuar con una propuesta descriptiva."
    return result(content, preparation)
