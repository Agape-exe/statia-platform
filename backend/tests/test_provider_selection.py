"""API multiproveedor con persistencia controlada y transporte OpenAI simulado."""

import copy
import json
from uuid import uuid4

import httpx
import pytest
import test_chat_api
from test_chat_api import attach_dataset, new, plan, reply, turn
from test_openai_provider import completed
from test_result_conversation import result_client as result_client

from app.models.chat import AssistantReply, Plan
from app.services.openai_provider import MODEL, OpenAIProvider
from app.services.plan_capabilities import warn_capabilities

api = test_chat_api.api


def terra(client, responses):
    settings = client.app.state.settings
    settings.openai_terra_enabled = True
    settings.openai_api_key = type(settings.openai_api_key)("credencial-sintetica")
    settings.gemini_api_key = type(settings.gemini_api_key)("gemini-sintetica")
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        response = responses.pop(0)
        return response if isinstance(response, httpx.Response) else httpx.Response(200, json=completed(response))

    client.app.state.openai_provider = OpenAIProvider(settings, transport=httpx.MockTransport(handle))
    return calls


def select(client, path, provider, expected="gemini"):
    return client.patch(path + "/provider", json={"provider": provider, "expected_provider": expected})


def ready(client, store):
    path = new(client, store)
    turn(client, path, action="instrument_no")
    fid = attach_dataset(client, path)
    return path, fid


def test_default_and_legacy_conversations_use_gemini(api):
    client, store, gemini = api
    path, _ = ready(client, store)
    assert client.get(path).json()["conversation"]["assistant_provider"] == "gemini"
    del store.data["conversations"][0]["assistant_provider"]  # Compatibilidad de lectura histórica.
    gemini.replies.append(reply())
    assert turn(client, path, content="Comprende los datos").status_code == 200
    metadata = client.get(path).json()["messages"][-1]["metadata"]
    assert metadata["generation"]["provider"] == "gemini"
    assert metadata["generation"]["model"] == client.app.state.settings.gemini_model
    assert store.data["chat_requests"][-1]["provider"] == "gemini"


def test_explicit_selection_preserves_history_proposals_and_results_and_replays(api):
    client, store, gemini = api
    path, fid = ready(client, store)
    gemini.replies.append(reply(proposals=[plan(fid)]))
    assert turn(client, path, content="Describe las notas").status_code == 200
    before = copy.deepcopy(client.get(path).json())
    proposal = before["proposals"][0]
    assert client.patch(path + "/proposals/" + proposal["id"], json={"status": "accepted"}).status_code == 200
    preserved_proposals = copy.deepcopy(store.data["analysis_proposals"])
    preserved_results = copy.deepcopy(store.data["analysis_runs"])
    calls = terra(client, [reply()])
    assert select(client, path, "openai").status_code == 200
    request_id = str(uuid4())
    assert turn(client, path, content="Explica las notas", request_id=request_id).status_code == 200
    messages = client.get(path).json()["messages"]
    assert messages[: len(before["messages"])] == before["messages"]
    assert messages[-1]["metadata"]["generation"]["provider"] == "openai"
    assert messages[-1]["metadata"]["generation"]["model"] == MODEL
    assert messages[-1]["metadata"]["generation"]["generations"][0]["usage"]["input_tokens"] == 100
    assert len(calls) == 1 and len(gemini.contexts) == 1
    assert store.data["analysis_proposals"] == preserved_proposals
    assert store.data["analysis_runs"] == preserved_results
    assert select(client, path, "gemini", expected="openai").status_code == 200
    replay = turn(client, path, content="Explica las notas", request_id=request_id)
    assert replay.status_code == 200 and replay.json()["replayed"]
    assert len(calls) == 1
    # El historial anterior entra en el contexto compartido tras la decisión explícita.
    assert any("Comprendí" in entry["content"] for entry in json.loads(calls[0]["input"])["history"])


@pytest.mark.parametrize("provider", ["unknown", "gpt-6.1-terra", "", "OPENAI"])
def test_unknown_provider_and_arbitrary_model_rejected(api, provider):
    client, store, _ = api
    path = new(client, store)
    assert select(client, path, provider).status_code == 422
    assert client.post(f"/projects/{store.project_id}/conversations", json={"provider": provider}).status_code == 422
    assert (
        client.post(
            f"/projects/{store.project_id}/conversations", json={"provider": "gemini", "model": MODEL}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("enabled,key,error", [(False, "test", "disabled"), (True, "", "not_configured")])
def test_unconfigured_selection_and_creation_do_not_mutate(api, enabled, key, error):
    client, store, _ = api
    path = new(client, store)
    settings = client.app.state.settings
    settings.openai_terra_enabled = enabled
    settings.openai_api_key = type(settings.openai_api_key)(key)
    before = copy.deepcopy(store.data)
    response = select(client, path, "openai")
    assert response.status_code == 503 and response.headers["X-Statia-Error"] == "openai_" + error
    assert client.post(f"/projects/{store.project_id}/conversations", json={"provider": "openai"}).status_code == 503
    assert store.data == before


def test_catalog_has_only_safe_configuration_and_requires_project_access(api):
    client, store, _ = api
    terra(client, [])
    response = client.get(f"/projects/{store.project_id}/assistant-providers")
    assert response.status_code == 200
    assert response.json()["default"] == "gemini"
    assert "credencial-sintetica" not in response.text and "gemini-sintetica" not in response.text
    assert "credencial-sintetica" not in repr(client.app.state.settings)
    assert client.get(f"/projects/{uuid4()}/assistant-providers").status_code == 404
    assert (
        client.patch(
            f"/projects/{uuid4()}/conversations/{uuid4()}/provider",
            json={"provider": "openai", "expected_provider": "gemini"},
        ).status_code
        == 404
    )


def test_create_with_explicit_terra_and_selection_conflicts(api):
    client, store, _ = api
    terra(client, [])
    response = client.post(f"/projects/{store.project_id}/conversations", json={"provider": "openai"})
    assert response.status_code == 201 and response.json()["assistant_provider"] == "openai"
    path = f"/projects/{store.project_id}/conversations/{response.json()['id']}"
    assert select(client, path, "gemini").status_code == 409
    store.data["conversations"][-1]["active_request_id"] = str(uuid4())
    assert select(client, path, "gemini", expected="openai").status_code == 409


def test_http_failure_does_not_fallback_and_failed_retry_cannot_change_provider(api):
    client, store, gemini = api
    path, _ = ready(client, store)
    calls = terra(client, [httpx.Response(503, json={"error": {"message": "privado"}})])
    select(client, path, "openai")
    request_id = str(uuid4())
    response = turn(client, path, content="Describe las notas", request_id=request_id)
    assert response.status_code == 503 and response.headers["X-Statia-Error"] == "openai_unavailable"
    assert len(calls) == 1 and not gemini.contexts
    assert client.get(path).json()["retry_turn"]["request_id"] == request_id
    assert select(client, path, "gemini", expected="openai").status_code == 200
    assert turn(client, path, content="Describe las notas", request_id=request_id).status_code == 409
    assert len(calls) == 1 and not gemini.contexts
    assert not store.data["analysis_proposals"]


def test_same_semantic_validation_repairs_once_and_records_both_generations(api):
    client, store, gemini = api
    path, fid = ready(client, store)
    invalid = plan(fid)
    invalid["variables"][0]["column"] = "inexistente"
    calls = terra(client, [reply(proposals=[invalid]), reply(proposals=[plan(fid)])])
    select(client, path, "openai")
    assert turn(client, path, content="Describe las notas").status_code == 200
    assert len(calls) == 2 and "Corrige TODOS" in calls[1]["input"]
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 1 and not gemini.contexts
    metadata = detail["messages"][-1]["metadata"]
    assert metadata["planning_validation"]["attempts"][0]["issues"][0]["category"] == "column_reference"
    assert len(metadata["generation"]["generations"]) == 2


def test_invalid_after_one_correction_never_persists(api):
    client, store, _ = api
    path, fid = ready(client, store)
    invalid = plan(fid)
    invalid["variables"][0]["file_id"] = str(uuid4())
    calls = terra(client, [reply(proposals=[invalid]), reply(proposals=[invalid])])
    select(client, path, "openai")
    result = turn(client, path, content="Describe las notas")
    assert result.status_code == 502 and result.headers["X-Statia-Error"] == "planning_validation"
    assert len(calls) == 2 and not store.data["analysis_proposals"]


def test_turn_request_budget_blocks_paid_semantic_correction(api):
    client, store, _ = api
    path, fid = ready(client, store)
    invalid = plan(fid)
    invalid["variables"][0]["column"] = "otra"
    calls = terra(client, [reply(proposals=[invalid])])
    client.app.state.settings.ai_max_requests_per_turn = 1
    select(client, path, "openai")
    result = turn(client, path, content="Describe las notas")
    assert result.status_code == 429 and len(calls) == 1
    assert not store.data["analysis_proposals"]


def test_deterministic_flow_never_claims_model_generated_text(api):
    client, store, _ = api
    terra(client, [])
    path = new(client, store)
    select(client, path, "openai")
    assert turn(client, path, action="instrument_no").status_code == 200
    assert client.get(path).json()["messages"][-1]["metadata"]["generation"] == {"source": "deterministic"}


def test_descriptive_warning_does_not_repair_incompatible_products():
    original = Plan.model_validate(plan(str(uuid4())))
    grouped = original.model_dump()
    grouped["variables"].append({**grouped["variables"][0], "column": "grupo", "role": "group"})
    grouped["expected_outputs"] = ["Resumen global, agrupado y frecuencias de grupo"]
    reply = AssistantReply(response="Propuesta", suggested_stage="proposal", proposals=[Plan.model_validate(grouped)])
    before = reply.model_dump()
    warned = warn_capabilities(reply)
    assert reply.model_dump() == before
    assert warned.model_dump() == before
    from app.services.plan_capabilities import validate_products
    from app.services.planning_errors import PlanningError

    with pytest.raises(PlanningError, match="no está cubierto"):
        validate_products(warned.proposals[0])
    assert warned.proposals[0].expected_outputs == grouped["expected_outputs"]
    assert AssistantReply.model_validate(warned.model_dump())
    assert not warn_capabilities(
        AssistantReply(response="Plan", suggested_stage="proposal", proposals=[original])
    ).warnings


def test_switch_after_python_results_preserves_artifacts_and_numeric_validation(result_client):
    client, store, path, send, run, gemini = result_client
    runs = copy.deepcopy(store.data["analysis_runs"])
    artifacts = copy.deepcopy(store.data["analysis_artifacts"])
    objects = copy.deepcopy(store.objects)
    state = copy.deepcopy(client.get(path).json()["conversation"]["stage_data"])
    calls = terra(
        client,
        [
            reply(response="El valor p = 0.123456789."),
            reply(response="El componente descriptivo presenta una media de 20 en A. Pearson sigue pendiente."),
        ],
    )
    assert select(client, path, "openai").status_code == 200
    result = send(content="Explícame los resultados obtenidos")
    assert result.status_code == 200, result.text
    assert len(calls) == 2 and not gemini.contexts
    assert json.loads(calls[0]["input"])["analysis_results"]
    assert store.data["analysis_runs"] == runs
    assert store.data["analysis_artifacts"] == artifacts and artifacts
    assert store.objects == objects
    assert client.get(path).json()["conversation"]["stage_data"] == {
        **state,
        "independence_evidence": state.get("independence_evidence", []),
    }
