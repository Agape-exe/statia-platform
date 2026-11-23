"""Regresiones HTTP con proveedores simulados y cálculo real tras confirmación."""

import copy
from uuid import uuid4

import pytest
from test_chat_api import new, reply, turn
from test_instruments import pdf
from test_session6 import local as local
from test_session6 import upload
from test_thesis_stability import frequency_plan, thesis_context

from app.models.chat import Turn
from app.services.conversation_text import interaction_mode, proposal_limit

REQUEST = (
    "Prepara una única propuesta descriptiva de frecuencias categóricas de sun_reaction con todos los registros. "
    "Solo quiero una tabla con categorías, frecuencias absolutas y porcentajes, denominador y valores ausentes. "
    "Sin filtros, sin comparaciones ni agrupaciones, sin gráficos, sin otras variables, sin pruebas inferenciales "
    "y sin resultados adicionales. No ejecutes antes de aceptar."
)
FALSE_CLAIM = (
    "De acuerdo con el objetivo confirmado en el Contexto, he preparado la propuesta descriptiva "
    "de frecuencias absolutas y porcentajes no ponderados para sun_reaction."
)


@pytest.mark.parametrize(
    "text, limit",
    [
        ("Genera tres alternativas estadísticas para mis objetivos", 3),
        ("Deja lista una propuesta descriptiva. No ejecutes", 1),
        ("Quiero un plan de frecuencias para esta variable", 1),
    ],
)
def test_explicit_plan_requests_bind_the_count_without_running_analyses(text, limit):
    assert proposal_limit(text) == limit
    assert interaction_mode(Turn(request_id=uuid4(), content=text)) == "planning"


def prepare_chat(local, project_mode):
    client, store, _ = local
    if project_mode == "thesis":
        thesis_context(store, 1)
        document = store.data["research_contexts"][0]["document"]
        document["specific_objectives"] = ["Describir la reacción solar.", "Comparar exposición en la muestra."]
        document["general_objective"] = "Medir la exposición solar con tablas, gráficos y resúmenes globales."
    path = new(client, store)
    assert turn(client, path, action="instrument_yes").status_code == 200
    upload(client, path, "instrumento.pdf", pdf(["Section 1. Does your skin burn? Options: yes, no."]), "instrument")
    assert turn(client, path, action="instruments_done").status_code == 200
    csv = b"sun_reaction,grupo\n" + b"Sensible,A\nLeve,B\n,A\n" * 1139 + b"Sensible,A\nLeve,B\n"
    dataset = upload(client, path, "dermatologia.csv", csv)
    assert dataset["metadata"]["profile"]["row_count"] == 3419
    return path, dataset["id"]


@pytest.mark.parametrize("mode", ["thesis", "general"])
def test_understanding_and_questions_do_not_announce_or_create_plans(local, mode):
    client, store, provider = local
    path, fid = prepare_chat(local, mode)
    good = reply(response="El CSV contiene 3419 registros y tiene un instrumento PDF asociado.")
    provider.replies.extend(
        [reply(response=FALSE_CLAIM, proposals=[frequency_plan(fid, "sun_reaction")]), good, good, good, good]
    )
    assert turn(client, path, action="files_ready").status_code == 200
    assert "proposal_missing" in provider.contexts[1][1]
    for question, intent in (
        ("¿Qué contiene mi dataset?", "understanding"),
        ("¿Qué procedimientos podrían utilizarse para esta variable?", "methodology"),
        ("¿Qué análisis podría utilizar para analizar las frecuencias?", "methodology"),
    ):
        assert turn(client, path, content=question).status_code == 200
        assert provider.contexts[-1][0]["interaction_mode"] == intent
        assert "requested_scope" not in provider.contexts[-1][0]
    context = provider.contexts[0][0]
    assert (context["research_context"] or {}).get("revision") == (1 if mode == "thesis" else None)
    assert all(not file.get("instrument", {}).get("fragments_shared") for file in context["files"])
    assert not any("he preparado" in msg["content"] for msg in client.get(path).json()["messages"])
    assert not store.data["analysis_proposals"] and not store.data["analysis_runs"]


def test_independent_frequency_plan_preserves_scope_across_rejection_and_execution(local):
    client, store, provider = local
    path, fid = prepare_chat(local, "thesis")
    original_context = copy.deepcopy(store.data["research_contexts"])
    older = frequency_plan(fid, "sun_reaction")
    older["expected_outputs"] = ["Frecuencias categóricas", "Resúmenes globales"]
    provider.replies.append(reply(proposals=[older]))
    assert turn(client, path, content="Prepara una propuesta con resúmenes globales.").status_code == 200
    previous = client.get(path).json()["proposals"][0]
    assert client.patch(f"{path}/proposals/{previous['id']}", json={"status": "rejected"}).status_code == 200

    current = frequency_plan(fid, "sun_reaction")
    extra = copy.deepcopy(current)
    extra["expected_outputs"] += ["Tablas y gráficos"]
    request_id = str(uuid4())
    provider.replies.extend([reply(proposals=[extra]), reply(proposals=[current])])
    assert turn(client, path, content=REQUEST, request_id=request_id).status_code == 200
    assert "requested_scope" in provider.contexts[-1][1]
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 2
    pending = next(row for row in detail["proposals"] if row["status"] == "proposed")
    assert pending["analysis_plan"]["expected_outputs"] == ["Frecuencias categóricas"]
    assert pending["source_message_id"] == detail["messages"][-1]["id"]
    scope = detail["messages"][-1]["metadata"]["requested_scope"]
    assert scope["products"] == ["frequencies"] and scope["product_sources"] == {"frequencies": [request_id]}
    assert scope["variables"] == [{"file_id": fid, "sheet": "tabla", "column": "sun_reaction"}]
    assert not detail["messages"][-1]["metadata"]["questions"]

    # Un turno posterior pide un producto que la tarjeta anterior no cumple.
    grouped = copy.deepcopy(current)
    grouped["variables"].append({**current["variables"][0], "column": "grupo", "role": "group"})
    grouped["method"] = "Frecuencias de sun_reaction por grupo"
    grouped["expected_outputs"] = ["Frecuencias categóricas por grupo"]
    provider.replies.append(reply(proposals=[grouped]))
    assert (
        turn(client, path, content="Prepara una nueva propuesta con frecuencias categóricas por grupo.").status_code
        == 200
    )
    assert client.get(path).json()["conversation"]["stage_data"]["requested_scope"]["products"] == [
        "grouped_frequencies"
    ]
    endpoint = f"{path}/proposals/{pending['id']}"
    body = {
        "request_id": str(uuid4()),
        "specification": {
            "decisions_confirmed": True,
            "components": [{"source_index": 0, "method": "descriptive", "descriptive_intervals": False}],
            "decisions": [
                {
                    "variable": current["variables"][0],
                    "statistical_type": "ordinal",
                    "ordinal_order": ["Leve", "Sensible"],
                }
            ],
        },
    }
    assert client.post(endpoint + "/runs", json=body).status_code == 409
    assert client.patch(endpoint, json={"status": "accepted"}).status_code == 200
    assert not store.data["analysis_runs"]
    run = client.post(endpoint + "/runs", json=body)
    assert run.status_code == 200, run.text
    result = run.json()
    assert result["status"] == "completed"
    component = result["result"]["components"][0]
    assert component["charts"] == [] and len(component["tables"]) == 1
    assert {"Categoría", "Frecuencia", "Porcentaje válido", "N válido", "Ausentes"} <= set(
        component["tables"][0]["columns"]
    )
    rows = component["tables"][0]["rows"]
    assert sum(row["Frecuencia"] for row in rows) == 2280
    assert {row["Ausentes"] for row in rows} == {1139}
    assert all(item["mime_type"] != "image/png" for item in result["artifacts"])
    assert client.post(endpoint + "/runs", json=body).json()["id"] == result["id"]
    assert turn(client, path, content=REQUEST, request_id=request_id).json()["replayed"]
    assert len(store.data["analysis_runs"]) == 1
    assert len([m for m in store.data["messages"] if m["content"] == REQUEST]) == 1
    assert store.data["research_contexts"] == original_context


def test_missing_variable_clarification_does_not_change_known_scope(local):
    client, store, provider = local
    path, fid = prepare_chat(local, "general")
    request_id = str(uuid4())
    unknown = REQUEST.replace("sun_reaction", "medicion_desconocida")
    wrong = frequency_plan(fid, "medicion_desconocida")
    provider.replies.extend([reply(proposals=[wrong]), reply(proposals=[wrong])])
    failed = turn(client, path, content=unknown, request_id=request_id)
    assert failed.status_code == 502 and "column_reference" in failed.headers["X-Statia-Validation"]
    provider.replies.append(
        reply(
            response="No aparece esa variable en el perfil.",
            clarification_required=True,
            questions=["¿Qué columna del archivo corresponde a esa variable?"],
        )
    )
    assert turn(client, path, content=unknown, request_id=request_id).status_code == 200
    detail = client.get(path).json()
    assert detail["messages"][-1]["metadata"]["questions"] == ["¿Qué columna del archivo corresponde a esa variable?"]
    assert len([msg for msg in detail["messages"] if msg["content"] == unknown]) == 1
    assert not store.data["analysis_proposals"] and not store.data["analysis_runs"]
