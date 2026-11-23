"""API/proveedor controlados; RLS y RPC reales se prueban aparte con SQL/PGlite."""

import asyncio
import copy

import pytest
import test_chat_api
from fastapi import HTTPException
from pydantic import ValidationError
from test_chat_api import attach_dataset, new, reply, turn

from app.models.research_context import ContextSave, ResearchContext
from app.services.research_context import current_context

api = test_chat_api.api


def document(**kwargs):
    return ResearchContext(**kwargs).model_dump(mode="json")


def test_unknown_information_and_discipline_specific_fields():
    doc = document(additional_fields={"Enfoque epistemológico": None})
    assert doc["hypotheses"] == [] and doc["population_sample"] is None
    for invalid in (
        {"schema_version": True},
        {"variables": [42]},
        {"hypotheses": None},
        {"invented": "x"},
        {"research_title": "x" * 2001},
    ):
        with pytest.raises(ValidationError):
            ResearchContext.model_validate(invalid)
    with pytest.raises(ValidationError):
        ResearchContext(research_title="x" * 2000, additional_fields={str(i): "x" * 2000 for i in range(8)})
    for confirmed in (False, 1, "true"):
        with pytest.raises(ValidationError):
            ContextSave(document=ResearchContext(), expected_revision=0, confirmed=confirmed)


def test_context_routes_require_thesis_ownership_and_explicit_confirmation(api):
    client, store, _ = api
    path = f"/projects/{store.project_id}/research-context"
    assert client.get(path).status_code == 404
    store.data["projects"][0]["project_type"] = "thesis"
    assert client.get(path).json() == {"context": None}
    assert client.put(path, json={"document": document(), "expected_revision": 0}).status_code == 422
    assert (
        client.put(path, json={"document": document(), "expected_revision": 0, "confirmed": False}).status_code == 422
    )
    store.data["projects"][0]["user_id"] = "another-user"
    assert client.get(path).status_code == 404
    assert client.put(path, json={"document": document(), "expected_revision": 0, "confirmed": True}).status_code == 404


def test_save_revision_and_conflict_preserve_current_context(api):
    client, store, _ = api
    store.data["projects"][0]["project_type"] = "thesis"
    original_rpc = store.rpc

    async def rpc(name, data):
        if name != "save_research_context":
            return await original_rpc(name, data)
        current = store.data["research_contexts"]
        if data["p_expected_revision"] != (current[0]["revision"] if current else 0):
            raise HTTPException(409, "El contexto cambió. Recarga y revisa antes de guardar.")
        saved = {
            "project_id": data["p_project"],
            "document": copy.deepcopy(data["p_document"]),
            "revision": data["p_expected_revision"] + 1,
            "updated_at": "2026-11-16T12:00:00Z",
        }
        store.data["research_contexts"] = [saved]
        return saved

    store.rpc = rpc
    path = f"/projects/{store.project_id}/research-context"
    body = {"document": document(research_title="Estudio exploratorio"), "expected_revision": 0, "confirmed": True}
    response = client.put(path, json=body)
    assert response.status_code == 200
    assert response.json()["context"]["revision"] == 1
    same = client.put(path, json={**body, "expected_revision": 1})
    assert same.status_code == 200 and same.json()["context"]["revision"] == 1
    assert store.data["research_contexts"][0]["revision"] == 1
    # Una revisión obsoleta sigue en conflicto aunque el contenido coincida.
    assert client.put(path, json=body).status_code == 409
    assert (
        client.put(path, json={**body, "document": document(research_title="Sobrescritura obsoleta")}).status_code
        == 409
    )
    assert client.get(path).json()["context"]["document"]["research_title"] == "Estudio exploratorio"


def test_assistant_uses_latest_confirmed_context_without_mutating_history(api):
    client, store, provider = api
    store.data["projects"][0]["project_type"] = "thesis"
    path = new(client, store)
    attach_dataset(client, path)
    conversation = store.data["conversations"][0]
    conversation["current_stage"] = "goal"
    store.data["research_contexts"] = [
        {
            "project_id": store.project_id,
            "document": document(research_title="Primera versión", additional_information="Contacto ana@example.org"),
            "revision": 1,
        }
    ]
    provider.replies.append(reply(response="Podemos revisar tu metodología sin cambiar el contexto."))
    assert turn(client, path, content="Explícame el diseño del estudio").status_code == 200
    assert provider.contexts[-1][0]["research_context"]["document"]["research_title"] == "Primera versión"
    assert "ana@example.org" not in str(provider.contexts[-1])
    old_messages = copy.deepcopy(store.data["messages"])
    store.data["research_contexts"][0].update(document=document(research_title="Nueva versión"), revision=2)
    provider.replies.append(reply(response="Revisa y confirma los cambios propuestos en Contexto."))
    assert turn(client, path, content="Quiero revisar la información metodológica").status_code == 200
    assert provider.contexts[-1][0]["research_context"]["revision"] == 2
    assert store.data["messages"][: len(old_messages)] == old_messages
    assert store.data["research_contexts"][0]["document"]["research_title"] == "Nueva versión"
    assert store.data["messages"][-1]["metadata"]["research_context_revision"] == 2


def test_general_never_queries_context_and_invalid_stored_context_is_rejected():
    class Store:
        async def rows(self, *args, **kwargs):
            return [{"document": {"schema_version": 99}, "revision": 1}]

    assert asyncio.run(current_context(None, {"project_type": "general"})) is None
    with pytest.raises(HTTPException) as exc:
        asyncio.run(current_context(Store(), {"id": "id", "project_type": "thesis"}))
    assert exc.value.status_code == 422
