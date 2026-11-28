"""Transiciones y persistencia del flujo desconocido; Auth/Storage/Gemini controlados."""

import base64
import copy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from test_automatic_preparation import penguins_job
from test_automatic_preparation import preparation_client as base_client
from test_chat_api import ControlledProvider
from test_statistics import job_for

from app.core.config import Settings
from app.models.chat import AssistantReply
from app.services.execution_preparation import (
    bind_descriptive_scope,
    normalized_preparation,
)
from app.services.planning_errors import PlanningError
from app.services.profiling import inspect_file
from app.services.statistics.automatic import assess, digest


@pytest.fixture
def uncertainty_client():
    for client, store, endpoint, body in base_client.__wrapped__():
        original = store.objects["original"]
        job = penguins_job()
        raw = base64.b64decode(job["files"][0]["data"])
        file = store.data["project_files"][0]
        file.update({k: v for k, v in job["files"][0].items() if k != "data"})
        file["metadata"] = inspect_file(file["original_name"], raw, "dataset", Settings(_env_file=None))
        store.objects["original"] = raw
        store.data["conversation_files"][0]["file_id"] = file["id"]
        proposal = store.data["analysis_proposals"][0]
        proposal["created_at"] = "2026-11-16T00:00:00+00:00"
        proposal.update(analysis_plan=job["plan"], objective=job["plan"]["objective"])
        try:
            yield client, store, endpoint, body
            assert store.objects["original"] == raw
        finally:
            store.objects["original"] = original


def send(client, path, action="message", **kwargs):
    response = client.post(path + "/turns", json={"request_id": str(uuid4()), "action": action, **kwargs})
    assert response.status_code == 200, response.text
    return response


def state_for(client, path):
    return client.get(path).json()["conversation"]["stage_data"]["execution_preparation"]


def blocked(client, store, endpoint, *, text=False):
    path = endpoint.rsplit("/proposals/", 1)[0]
    pid = store.data["analysis_proposals"][0]["id"]
    send(client, path, "prepare_execution", proposal_id=pid)
    q = state_for(client, path)["result"]["questions"][0]
    assert q["variable"]["column"] == "sex"
    send(client, path, "clarify_execution", question_id=q["id"], answer="missing")
    design = state_for(client, path)["result"]["questions"][0]
    assert "recolección" in design["choices"][0]["label"]
    request = {
        "request_id": str(uuid4()),
        "action": "message" if text else "clarify_execution",
        **({"content": "No lo sé"} if text else {"question_id": design["id"], "answer": "unknown"}),
    }
    response = client.post(path + "/turns", json=request)
    assert response.status_code == 200, response.text
    return path, pid, q, design, request


@pytest.mark.parametrize("text", [False, True], ids=["boton", "texto"])
def test_unknown_repeated_and_reloaded_is_not_an_unanswered_question(uncertainty_client, text):
    client, store, endpoint, _ = uncertainty_client
    source = copy.deepcopy(store.data["analysis_proposals"][0])
    path, _, marker, design, request = blocked(client, store, endpoint, text=text)
    initial = state_for(client, path)
    assert initial["result"]["status"] == "BLOCKED_UNCERTAINTY"
    assert initial["result"]["questions"] == []
    assert initial["answers"][marker["id"]] == "missing"
    assert initial["answers"][design["id"]] == "unknown"
    assert {q["status"] for q in initial["result"]["clarifications"]} == {"answered", "unknown"}
    before = len(store.data["messages"])
    assert client.post(path + "/turns", json=request).json()["replayed"] is True
    assert len(store.data["messages"]) == before
    for _ in range(3):
        send(client, path, content="No lo sé")
        assert state_for(client, path) == initial
        assert design["prompt"] not in store.data["messages"][-1]["content"]
    assert sum(design["prompt"] in m["content"] for m in store.data["messages"]) == 1
    assert store.data["analysis_proposals"][0] == source
    assert not store.data["analysis_runs"]
    body = {
        "request_id": initial["result"]["request_id"],
        "preparation_fingerprint": initial["result"]["fingerprint"],
        "specification": {**initial["result"]["specification"], "decisions_confirmed": True},
    }
    assert client.post(endpoint, json=body).status_code in {409, 422}
    assert not store.data["analysis_runs"]


def test_explicit_revision_keeps_other_decisions_and_can_finish_execution(uncertainty_client):
    client, store, endpoint, _ = uncertainty_client
    path, _, marker, design, _ = blocked(client, store, endpoint)
    send(client, path, "review_execution", question_id=design["id"])
    revising = state_for(client, path)
    assert revising["result"]["status"] == "NEEDS_CLARIFICATION"
    assert revising["result"]["questions"][0]["id"] == design["id"]
    assert revising["answers"][design["id"]] == "unknown"
    assert revising["answers"][marker["id"]] == "missing"
    send(client, path, content="Sí, conozco la recolección y lo confirmo")
    ready = state_for(client, path)["result"]
    assert ready["status"] == "READY", ready
    assert not ready["questions"]
    assert all(q["status"] == "answered" for q in ready["clarifications"])
    body = {
        "request_id": ready["request_id"],
        "preparation_fingerprint": ready["fingerprint"],
        "specification": {**ready["specification"], "decisions_confirmed": True},
    }
    result = client.post(endpoint, json=body)
    assert result.status_code == 200, result.text
    assert result.json()["result"]["components"][0]["sample"]["used"] == 146
    assert client.post(endpoint, json=body).json()["id"] == result.json()["id"]
    assert len(store.data["analysis_runs"]) == 1


def test_leaving_pending_preserves_answers_and_does_not_restart_question(uncertainty_client):
    client, store, endpoint, _ = uncertainty_client
    path, pid, _, _, _ = blocked(client, store, endpoint)
    before = state_for(client, path)
    send(client, path, "cancel_execution")
    paused = state_for(client, path)
    assert paused["paused"] is True
    assert paused["answers"] == before["answers"]
    assert paused["result"] == before["result"]
    send(client, path, "prepare_execution", proposal_id=pid)
    resumed = state_for(client, path)
    assert resumed["result"]["status"] == "BLOCKED_UNCERTAINTY"
    assert resumed["result"]["fingerprint"] == before["result"]["fingerprint"]
    assert resumed["result"]["questions"] == []


def descriptive_reply(source):
    plan = copy.deepcopy(source["analysis_plan"])
    plan.update(
        procedure="descriptive",
        method="Frecuencias y resúmenes descriptivos",
        title="Descripción alternativa",
        objective="Describir body_mass_g, sex y species dentro del alcance Adelie",
        comparison=None,
        components=[],
        requirements=["Conservar el alcance y las decisiones de datos"],
        limitations=["La independencia es desconocida; no se contrastan hipótesis"],
        justification="Describir las observaciones disponibles sin conclusiones inferenciales",
    )
    return {
        "response": "Puedes aceptar esta nueva propuesta descriptiva; el análisis original queda pendiente.",
        "suggested_stage": "proposal",
        "proposals": [plan],
        "confirmation_required": True,
    }


def test_descriptive_alternative_is_generated_validated_accepted_and_prepared_separately(uncertainty_client):
    client, store, endpoint, _ = uncertainty_client
    path, pid, marker, _, _ = blocked(client, store, endpoint)
    original = copy.deepcopy(store.data["analysis_proposals"][0])
    original_state = state_for(client, path)
    provider = ControlledProvider()
    provider.replies = [descriptive_reply(original)]
    client.app.state.provider = provider
    request = {"request_id": str(uuid4()), "action": "request_descriptive", "proposal_id": pid}
    response = client.post(path + "/turns", json=request)
    assert response.status_code == 200, response.text
    assert client.post(path + "/turns", json=request).json()["replayed"] is True
    assert len(provider.contexts) == 1
    assert len(store.data["conversations"]) == 1
    assert provider.contexts[0][0]["execution_alternative"]["source_proposal_id"] == pid
    assert store.data["analysis_proposals"][0] == original
    assert state_for(client, path) == original_state
    alternative = store.data["analysis_proposals"][1]
    assert alternative["status"] == "proposed"
    assert alternative["analysis_plan"]["filters"] == original["analysis_plan"]["comparison"]["filters"]
    assert not store.data["analysis_runs"]
    assert client.patch(path + "/proposals/" + alternative["id"], json={"status": "accepted"}).status_code == 200
    send(client, path, "prepare_execution", proposal_id=alternative["id"])
    prepared = state_for(client, path)
    assert prepared["result"]["status"] == "READY", prepared
    assert prepared["answers"][marker["id"]] == "missing"
    assert prepared["result"]["specification"]["filters"] == original["analysis_plan"]["comparison"]["filters"]
    assert not any(q["status"] == "unknown" for q in prepared["result"]["clarifications"])
    assert not store.data["analysis_runs"]
    send(client, path, "prepare_execution", proposal_id=pid)
    assert state_for(client, path)["result"]["status"] == "BLOCKED_UNCERTAINTY"
    assert state_for(client, path)["answers"] == original_state["answers"]


def test_provider_unavailable_preserves_source_and_retry_does_not_duplicate_requests(uncertainty_client):
    client, store, endpoint, _ = uncertainty_client
    path, pid, _, _, _ = blocked(client, store, endpoint)
    before = state_for(client, path)
    source = copy.deepcopy(store.data["analysis_proposals"][0])
    provider = ControlledProvider()
    provider.replies = [HTTPException(503, "Gemini no está disponible.")]
    client.app.state.provider = provider
    request = {"request_id": str(uuid4()), "action": "request_descriptive", "proposal_id": pid}
    response = client.post(path + "/turns", json=request)
    assert response.status_code == 503
    assert "se conservan" in response.json()["detail"]
    assert state_for(client, path) == before
    assert store.data["analysis_proposals"] == [source]
    provider.replies = [descriptive_reply(source)]
    assert client.post(path + "/turns", json=request).status_code == 200
    user_messages = [
        m
        for m in store.data["messages"]
        if m["role"] == "user" and m["metadata"].get("request_id") == request["request_id"]
    ]
    assert len(user_messages) == 1
    assert len(store.data["analysis_proposals"]) == 2


def test_existing_unknown_state_is_adapted_without_changing_ids_or_fingerprint():
    job = job_for()
    initial = assess(job)
    scope = digest({"plan": job["plan"], "files": initial["files"]})
    old_questions, answers = [], {}
    for q in initial["clarifications"]:
        old = {k: q[k] for k in ["prompt", "explanation", "choices", "variable"]}
        old["id"] = digest([scope, q["subject"]])
        old_questions.append(old)
        answers[old["id"]] = "unknown"
    old_state = {
        "proposal_id": job["proposal_id"],
        "answers": answers,
        "result": {**initial, "status": "NEEDS_CLARIFICATION", "questions": old_questions},
    }
    old_state["result"].pop("clarifications")
    normalized = normalized_preparation(old_state)
    assert normalized["result"]["status"] == "BLOCKED_UNCERTAINTY"
    assert normalized["result"]["questions"] == []
    assert normalized["result"]["fingerprint"] == old_state["result"]["fingerprint"]
    updated = assess({**job, "answers": answers})
    assert {q["id"] for q in updated["clarifications"]} == set(answers)
    assert updated["status"] == "BLOCKED_UNCERTAINTY"
    assert old_state["result"]["status"] == "NEEDS_CLARIFICATION"


def test_changing_one_file_invalidates_only_its_clarifications():
    first = job_for(b"cantidad,estrato,otra\n1,A,2\n2,A,NA\n3,B,4\n", procedure="descriptive")
    second = job_for(b"cantidad,estrato,otra\n1,A,2\n2,A,NA\n3,B,4\n", procedure="descriptive")
    job = {
        **first,
        "plan": {**first["plan"], "variables": first["plan"]["variables"] + second["plan"]["variables"]},
        "files": first["files"] + second["files"],
    }
    initial = assess(job)
    job["answers"] = {
        q["id"]: "continuous" if q["subject"].endswith(":type") else "missing" for q in initial["questions"]
    }
    ready = assess(job)
    assert ready["status"] == "READY"
    job["clarifications"] = ready["clarifications"]
    job["files"][1] = {
        **job["files"][1],
        "data": base64.b64encode(b"cantidad,estrato,otra\n1,A,3\n2,A,NA\n3,B,4\n").decode(),
    }
    changed = assess(job)
    kept = [q for q in changed["clarifications"] if q["variable"]["file_id"] == first["files"][0]["id"]]
    assert all(q["status"] == "answered" and q["id"] in job["answers"] for q in kept)
    assert all(q["variable"]["file_id"] == second["files"][0]["id"] for q in changed["questions"])
    assert changed["status"] == "NEEDS_CLARIFICATION"


@pytest.mark.parametrize("change", ["inferential", "column", "filter"])
def test_invalid_descriptive_alternatives_are_rejected(change):
    job = penguins_job()
    reply = AssistantReply.model_validate(descriptive_reply({"analysis_plan": job["plan"]}))
    request = {"variables": job["plan"]["variables"], "filters": job["plan"]["comparison"]["filters"]}
    if change == "inferential":
        reply.proposals[0].procedure = "group_comparison"
    elif change == "column":
        reply.proposals[0].variables[0].column = "otra_columna"
    else:
        reply.proposals[0].filters = (
            copy.deepcopy(reply.proposals[0].comparison.filters) if reply.proposals[0].comparison else []
        )
        from app.models.chat import Selection

        reply.proposals[0].filters = [Selection.model_validate({**request["filters"][0], "values": ["otra categoría"]})]
    with pytest.raises(PlanningError, match="descriptiva|filtros"):
        bind_descriptive_scope(reply, request)


def test_design_question_is_shared_by_components_of_the_same_table_and_scope():
    job = job_for()
    fid = job["files"][0]["id"]
    a, group = job["plan"]["variables"]
    b = {"file_id": fid, "sheet": "tabla", "column": "otra", "role": "predictor"}
    job["plan"].update(
        procedure="integral",
        variables=[a, group, b],
        components=[
            {"procedure": "correlation", "method": "Pearson", "variables": [a, b]},
            {"procedure": "group_comparison", "method": "t de Welch", "variables": [a, group]},
        ],
    )
    initial = assess(job)
    design = [q for q in initial["clarifications"] if q["subject"].startswith("design:")]
    assert len(design) == 1
    job["answers"] = {q["id"]: "yes" if q["id"] == design[0]["id"] else "continuous" for q in initial["questions"]}
    assert assess(job)["status"] == "READY"
