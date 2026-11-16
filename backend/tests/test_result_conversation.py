"""Conversación posterior a resultados: HTTP/cálculo reales con Auth y proveedor controlados."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
from test_analysis_api import analysis_client as original_client
from test_chat_api import ControlledProvider
from test_statistics import job_for

from app.core.config import Settings
from app.models.chat import AssistantReply
from app.services.analysis_context import saved_results_context, validate_numeric_claims
from app.services.planning_errors import PlanningError
from app.services.profiling import inspect_file


def test_descriptive_rounding_checks_scientific_notation():
    context = {
        "analysis_results": [{"components": [{"statistics": {}, "tables": [{"rows": [{"Media": 0.00012345}]}]}]}]
    }
    validate_numeric_claims("La media es 1.23e-4.", context)
    with pytest.raises(PlanningError):
        validate_numeric_claims("La media es 2e-4.", context)


@pytest.fixture
def result_client():
    for client, store, endpoint, _ in original_client.__wrapped__():
        raw = b"cantidad,estrato,otra,resultado\n10,A,2,0\n20,A,4,1\n30,A,3,1\n20,B,5,0\n40,B,7,0\n60,B,9,1\n"
        job = job_for(raw)
        quantity, group = job["plan"]["variables"]
        other = {**quantity, "column": "otra", "role": "predictor"}
        outcome = {**quantity, "column": "resultado", "role": "description"}
        job["plan"].update(
            procedure="integral",
            variables=[quantity, group, other, outcome],
            components=[
                {"procedure": "descriptive", "method": "Descriptivos", "variables": [quantity, group, other, outcome]},
                {"procedure": "correlation", "method": "Pearson", "variables": [quantity, other]},
                {"procedure": "group_comparison", "method": "t de Welch", "variables": [quantity, group]},
            ],
        )
        original = store.objects["original"]
        file = store.data["project_files"][0]
        file.update({k: v for k, v in job["files"][0].items() if k != "data"})
        file["metadata"] = inspect_file("arbitrario.csv", raw, "dataset", Settings(_env_file=None))
        store.data["conversation_files"][0]["file_id"] = file["id"]
        store.objects["original"] = raw
        proposal = store.data["analysis_proposals"][0]
        proposal["analysis_plan"] = job["plan"]
        conversation = store.data["conversations"][0]
        conversation["primary_goal"] = "Describir las medidas y estudiar sus relaciones"
        path = endpoint.rsplit("/proposals/", 1)[0]

        def turn(action="message", content="", **values):
            return client.post(
                path + "/turns",
                json={
                    "request_id": str(uuid4()),
                    "action": action,
                    "content": content,
                    "proposal_id": proposal["id"],
                    **values,
                },
            )

        assert turn("prepare_execution").status_code == 200
        for _ in range(12):
            state = client.get(path).json()["conversation"]["stage_data"]["execution_preparation"]
            questions = state["result"]["questions"]
            if not questions:
                break
            q = questions[0]
            answer = (
                "unknown"
                if q["subject"].startswith("design:")
                else "nominal"
                if (q.get("variable") or {}).get("column") == "resultado"
                else "continuous"
            )
            response = turn("clarify_execution", question_id=q["id"], answer=answer)
            assert response.status_code == 200, response.text
        assert state["result"]["status"] == "PARTIALLY_READY"
        prepared = state["result"]
        response = client.post(
            endpoint,
            json={
                "request_id": prepared["request_id"],
                "preparation_fingerprint": prepared["fingerprint"],
                "specification": {**prepared["specification"], "decisions_confirmed": True},
            },
        )
        assert response.status_code == 200, response.text
        run = response.json()
        assert run["status"] == "partial"
        provider = ControlledProvider()
        client.app.state.provider = provider
        try:
            yield client, store, path, turn, run, provider
        finally:
            store.objects["original"] = original


def test_consecutive_questions_use_aggregates_and_preserve_pending_state(result_client, monkeypatch):
    client, store, path, turn, run, provider = result_client
    original = copy.deepcopy(client.get(path).json()["conversation"])
    immutable = copy.deepcopy(store.data["analysis_runs"])
    questions = [
        "Explícame los resultados obtenidos",
        "Necesito que me expliques mis resultados parciales obtenidos",
        "Explícame las medias y medianas",
        "¿Qué indican las frecuencias de resultado?",
        "¿Qué procedimientos quedaron pendientes?",
        "¿Qué es Pearson y por qué no se ejecutó?",
        "¿Qué significa la desviación estándar?",
        "Quiero revisar la independencia",
        "No entiendo qué significa independencia",
    ]
    for index, question in enumerate(questions):
        if index == 4:
            unknown = next(
                q
                for q in original["stage_data"]["execution_preparation"]["result"]["clarifications"]
                if q["status"] == "unknown"
            )
            assert turn("review_execution", question_id=unknown["id"]).status_code == 200
            original = copy.deepcopy(client.get(path).json()["conversation"])
            assert original["stage_data"]["execution_preparation"]["result"]["status"] == "NEEDS_CLARIFICATION"
        provider.replies = [
            AssistantReply(
                response="El descriptivo calculado presenta en A una media de 20 y mediana de 20. La frecuencia de la categoría 1 es 2, con 66.67% de los valores válidos de A. Pearson y Welch siguen pendientes por independencia desconocida; estos descriptivos no justifican causalidad.",
                suggested_stage="goal",
            )
        ]
        with monkeypatch.context() as patch:
            patch.setattr(
                "app.services.execution_preparation.run_calculation", lambda *_: pytest.fail("Preparó por consultar")
            )
            response = turn(content=question)
        assert response.status_code == 200, response.text
        current = client.get(path).json()
        assert (
            current["conversation"]["stage_data"]["execution_preparation"]
            == original["stage_data"]["execution_preparation"]
        )
        assert current["conversation"]["primary_goal"] == original["primary_goal"]
        assert current["conversation"]["current_stage"] == original["current_stage"]
        assert current["latest_analysis_run"]["status"] == "partial"
        assert "elige una opción" not in current["messages"][-1]["content"]
    context = provider.contexts[-1][0]
    assert context["result_discussion"] is True
    summary = context["analysis_results"][0]
    assert summary["run_id"] == run["id"]
    assert [c["status"] for c in summary["component_states"]] == [
        "COMPLETED",
        "BLOCKED_UNCERTAINTY",
        "BLOCKED_UNCERTAINTY",
    ]
    tables = summary["components"][0]["tables"]
    assert summary["components"][0]["grouping"] == ["estrato"]
    assert any(any(row.get("Frecuencia") == 2 for row in t["rows"]) for t in tables)
    assert all("samples" not in file and "row_count" not in file for file in context["files"])
    assert store.data["analysis_runs"] == immutable


def test_ambiguous_message_does_not_resolve_and_real_answer_still_revalidates(result_client):
    client, store, path, turn, _, provider = result_client
    before = client.get(path).json()["conversation"]["stage_data"]["execution_preparation"]
    response = turn(content="vale")
    assert response.status_code == 200
    assert "¿Quieres responder" in client.get(path).json()["messages"][-1]["content"]
    assert turn(content="Haz el análisis que consideres apropiado").status_code == 200
    assert "¿Quieres responder" in client.get(path).json()["messages"][-1]["content"]
    assert not provider.contexts
    assert turn(content="No lo sé").status_code == 200
    assert client.get(path).json()["conversation"]["stage_data"]["execution_preparation"] == before
    unknown = next(q for q in before["result"]["clarifications"] if q["status"] == "unknown")
    assert turn("clarify_execution", question_id=unknown["id"], answer="cualquier cosa").status_code == 200
    assert client.get(path).json()["conversation"]["stage_data"]["execution_preparation"] == before
    response = turn("clarify_execution", question_id=unknown["id"], answer="yes")
    assert response.status_code == 200, response.text
    current = client.get(path).json()["conversation"]["stage_data"]["execution_preparation"]["result"]
    assert current["components"][0]["status"] == "COMPLETED"
    assert [c["source_index"] for c in current["specification"]["components"]] == [1, 2]
    assert len(store.data["analysis_runs"]) == 1


def test_numeric_guard_scope_old_runs_and_privacy(result_client):
    client, store, path, turn, run, provider = result_client
    conversation = store.data["conversations"][0]
    summaries = asyncio.run(saved_results_context(store, conversation))
    validate_numeric_claims("La media es 20; mediana: 20 y 66.67%.", {"analysis_results": summaries})
    for text in ("La media es 999.", "El porcentaje es 99%.", "p = 0.04"):
        with pytest.raises(PlanningError):
            validate_numeric_claims(text, {"analysis_results": summaries})
    outsider = copy.deepcopy(store.data["analysis_runs"][0])
    outsider.update(id=str(uuid4()), conversation_id=str(uuid4()), project_id=str(uuid4()))
    store.data["analysis_runs"].append(outsider)
    assert asyncio.run(saved_results_context(store, conversation, outsider["id"])) == []
    assert asyncio.run(saved_results_context(store, conversation, run["id"]))[0]["run_id"] == run["id"]
    failure = {
        **copy.deepcopy(store.data["analysis_runs"][0]),
        "id": str(uuid4()),
        "status": "failed",
        "result": None,
        "error": "Fallo de Storage.",
        "created_at": "2020-01-01T00:00:00Z",
    }
    store.data["analysis_runs"].append(failure)
    failed_context = asyncio.run(saved_results_context(store, conversation, failure["id"]))
    assert failed_context[0]["error"] == "Fallo de Storage."
    assert failed_context[0]["components"] == []
    stored = store.data["analysis_runs"][0]["result"]
    frequency = next(t for t in stored["components"][0]["tables"] if "Frecuencia" in t["columns"])
    frequency["rows"].append({"Variable / grupo": "correo", "Categoría": "privado@example.org", "Frecuencia": 1})
    result = asyncio.run(saved_results_context(store, conversation))
    assert "privado@example.org" not in json.dumps(result)
    assert len(json.dumps(result, ensure_ascii=False)) <= 16000


def test_provider_cannot_invent_inference_or_replace_plan_for_interpretation(result_client):
    client, store, path, turn, run, provider = result_client
    previous = copy.deepcopy(client.get(path).json()["conversation"]["stage_data"]["execution_preparation"])
    provider.replies = [
        AssistantReply(response="ANOVA fue estadísticamente significativo.", suggested_stage="understanding")
    ] * 2
    response = turn(content="Explícame los resultados parciales")
    assert response.status_code == 502, response.text
    assert len(provider.contexts) == 2
    assert len(store.data["analysis_runs"]) == 1
    assert client.get(path).json()["conversation"]["stage_data"]["execution_preparation"] == previous
