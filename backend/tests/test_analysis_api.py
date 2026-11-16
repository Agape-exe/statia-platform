"""HTTP + cálculo Python/proceso y ZIP reales; persistencia/Auth con doble controlado.

Las garantías transaccionales y RLS se prueban por separado en PostgreSQL/PGlite.
"""

import asyncio
import base64
import copy
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_chat_api import ControlledProvider, MemoryStore
from test_statistics import job_for

from app.core.auth import Identity, authenticated
from app.core.config import Settings
from app.main import create_app
from app.models.chat import AssistantReply
from app.services.analysis_context import saved_results_context, validate_numeric_claims
from app.services.analysis_worker import run_calculation
from app.services.profiling import inspect_file


class ResultsStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.fail_upload = False
        self.lose_commit_response = False
        self.download_count = 0

    async def rows(self, table, filters=None, order=None, limit=None, select="*", offset=None):
        rows = await super().rows(table, filters, order=order, limit=None, select=select)
        rows = rows[offset or 0 :]
        return rows[:limit] if limit else rows

    async def insert(self, table, data):
        return await super().insert(table, {"created_at": datetime.now(timezone.utc).isoformat(), **data})

    async def download(self, path, **kwargs):
        self.download_count += 1
        if path not in self.objects:
            raise HTTPException(422, "El archivo no está disponible.")
        return self.objects[path]

    async def upload(self, path, data, mime, **kwargs):
        if self.fail_upload:
            raise HTTPException(502, "Fallo de Storage controlado.")
        self.objects[path] = data

    async def remove_object(self, path, **kwargs):
        self.objects.pop(path, None)

    async def rpc(self, name, data):
        if name == "begin_analysis_run":
            previous = next(
                (
                    r
                    for r in self.data["analysis_runs"]
                    if r["request_id"] == data["p_request"] and r["conversation_id"] == data["p_conversation"]
                ),
                None,
            )
            if previous:
                if previous["specification"] != data["p_specification"]:
                    return {"status": "mismatch"}
                if previous.get("result"):
                    return {"status": "replayed", "run_id": previous["id"]}
                if previous["status"] == "running":
                    return {"status": "busy"}
                previous.update(status="running", lease_token=str(uuid4()), finished_at=None, error=None)
                return {"status": "started", "run_id": previous["id"], "lease_token": previous["lease_token"]}
            p = await self.one("analysis_proposals", {"id": data["p_proposal"]})
            r = (
                await self.insert(
                    "analysis_runs",
                    {
                        "project_id": self.project_id,
                        "conversation_id": data["p_conversation"],
                        "proposal_id": p["id"],
                        "request_id": data["p_request"],
                        "lease_token": str(uuid4()),
                        "specification": data["p_specification"],
                        "plan_snapshot": data["p_plan"],
                        "title": p["title"],
                        "status": "running",
                        "result": None,
                        "error": None,
                        "artifact_count": 0,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "finished_at": None,
                    },
                )
            )[0]
            return {"status": "started", "run_id": r["id"], "lease_token": r["lease_token"]}
        if name == "finish_analysis_run":
            for artifact in data["p_artifacts"]:
                await self.insert(
                    "analysis_artifacts", {"run_id": data["p_run"], "project_id": self.project_id, **artifact}
                )
            r = (
                await self.update(
                    "analysis_runs",
                    {"id": data["p_run"]},
                    {
                        "status": data["p_result"]["status"],
                        "result": data["p_result"],
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "artifact_count": len(data["p_artifacts"]),
                    },
                )
            )[0]
            await self.insert(
                "messages",
                {
                    "conversation_id": r["conversation_id"],
                    "role": "assistant",
                    "content": data["p_result"]["summary"],
                    "message_type": "event",
                    "metadata": {"analysis_run_id": data["p_run"]},
                },
            )
            if self.lose_commit_response:
                raise HTTPException(502, "Respuesta de commit perdida.")
            return
        if name == "fail_analysis_run":
            await self.update(
                "analysis_runs",
                {"id": data["p_run"], "lease_token": data["p_token"], "status": "running"},
                {"status": "failed", "error": data["p_error"], "finished_at": datetime.now(timezone.utc).isoformat()},
            )
            return
        return await super().rpc(name, data)


@pytest.fixture
def analysis_client():
    store = ResultsStore()
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[authenticated] = lambda: Identity(store.user_id, store)
    cid = str(uuid4())
    store.data["conversations"] = [
        {
            "id": cid,
            "project_id": store.project_id,
            "title": "Medidas",
            "current_stage": "ready",
            "stage_data": {},
            "active_request_id": None,
        }
    ]
    job = job_for()
    fid = job["files"][0]["id"]
    pid = str(uuid4())
    store.data["analysis_proposals"] = [
        {
            "id": pid,
            "conversation_id": cid,
            "status": "accepted",
            "title": job["plan"]["title"],
            "analysis_plan": job["plan"],
        }
    ]
    store.data["project_files"] = [
        {
            "id": fid,
            "project_id": store.project_id,
            "file_role": "dataset",
            "storage_path": "original",
            **{k: v for k, v in job["files"][0].items() if k != "data"},
        }
    ]
    store.data["conversation_files"] = [{"conversation_id": cid, "project_id": store.project_id, "file_id": fid}]
    original = base64.b64decode(job["files"][0]["data"])
    store.objects["original"] = original
    endpoint = f"/projects/{store.project_id}/conversations/{cid}/proposals/{pid}/runs"
    with TestClient(app) as client:
        yield client, store, endpoint, {"request_id": str(uuid4()), "specification": job["specification"]}
    assert store.objects["original"] == original


def test_execute_reload_list_zip_idempotency_and_context(analysis_client):
    client, store, endpoint, body = analysis_client
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "completed"
    assert run["result"]["components"][0]["statistics"]["difference"] == -2
    base = f"/projects/{store.project_id}/analysis-runs"
    replay = client.post(endpoint, json=body)
    assert replay.status_code == 200
    assert replay.json()["id"] == run["id"]
    assert len(store.data["analysis_runs"]) == 1
    assert store.download_count == 1  # Reintentar no vuelve a calcular ni descargar el original.
    assert client.get(f"{base}/{run['id']}").json()["result"] == run["result"]
    listed = client.get(base).json()
    assert len(listed) == 1 and listed[0]["result"] is None
    assert listed[0]["methods"] == ["t de Welch"]
    assert client.get(base + "?offset=1").json() == []
    assert client.get(base + "?conversation_id=" + str(uuid4())).status_code == 404
    downloaded = client.get(f"{base}/{run['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.headers["cache-control"] == "private, no-store"
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert archive.testzip() is None
        assert json.loads(archive.read("resultados.json")) == run["result"]
    chart = next(a for a in run["artifacts"] if a["mime_type"] == "image/png")
    assert client.get(f"{base}/{run['id']}/artifacts/{chart['id']}").content.startswith(b"\x89PNG")
    context = asyncio.run(saved_results_context(store, store.data["conversations"][0]))
    assert context[0]["components"][0]["statistics"]["difference"] == -2
    assert "original" not in json.dumps(context)
    validate_numeric_claims("La diferencia estandarizada es d = -1.2649.", {"analysis_results": context})
    with pytest.raises(ValueError, match="no coincide"):
        validate_numeric_claims("t = 999.", {"analysis_results": context})
    artifact = next(a for a in store.data["analysis_artifacts"] if a["id"] == chart["id"])
    store.objects[artifact["storage_path"]] = b"alterado"
    assert client.get(f"{base}/{run['id']}/artifacts/{chart['id']}").status_code == 409


def test_rejected_cross_scope_unlinked_and_ambiguous_requests(analysis_client):
    client, store, endpoint, body = analysis_client
    store.data["projects"][0]["project_type"] = "thesis"
    assert client.post(endpoint, json=body).status_code == 422
    assert not store.data["analysis_runs"]
    store.data["projects"][0]["project_type"] = "general"
    store.data["analysis_proposals"][0]["status"] = "rejected"
    assert client.post(endpoint, json=body).status_code == 409
    store.data["analysis_proposals"][0]["status"] = "accepted"
    wrong = endpoint.replace(store.project_id, str(uuid4()))
    assert client.post(wrong, json=body).status_code == 404
    invalid = copy.deepcopy(body)
    invalid["specification"]["components"][0]["method"] = "python_libre"
    assert client.post(endpoint, json=invalid).status_code == 422
    invalid["specification"]["components"][0]["method"] = "student_t"
    assert client.post(endpoint, json=invalid).status_code == 422
    store.data["conversation_files"] = []
    assert client.post(endpoint, json=body).status_code == 422
    assert store.data["analysis_runs"][0]["status"] == "failed"
    assert not store.data["analysis_artifacts"]


def test_storage_failure_retries_and_commit_response_reconciliation(analysis_client):
    client, store, endpoint, body = analysis_client
    store.fail_upload = True
    assert client.post(endpoint, json=body).status_code == 502
    assert store.data["analysis_runs"][0]["status"] == "failed"
    assert not store.data["analysis_runs"][0]["result"]
    store.fail_upload = False
    store.lose_commit_response = True
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert len(store.data["analysis_runs"]) == 1
    assert len([m for m in store.data["messages"] if m["metadata"].get("analysis_run_id")]) == 1
    assert all(a["storage_path"] in store.objects for a in store.data["analysis_artifacts"])


def test_expired_run_recovered_on_read(analysis_client):
    client, store, endpoint, body = analysis_client
    # Crear la concesión sin cálculo para representar una caída real del proceso HTTP.
    state = asyncio.run(
        store.rpc(
            "begin_analysis_run",
            {
                "p_conversation": store.data["conversations"][0]["id"],
                "p_proposal": store.data["analysis_proposals"][0]["id"],
                "p_request": body["request_id"],
                "p_specification": body["specification"],
                "p_plan": store.data["analysis_proposals"][0]["analysis_plan"],
            },
        )
    )
    store.data["analysis_runs"][0]["started_at"] = (datetime.now(timezone.utc) - timedelta(seconds=181)).isoformat()
    response = client.get(f"/projects/{store.project_id}/analysis-runs/{state['run_id']}")
    assert response.json()["status"] == "failed"


def test_worker_timeout_is_real_cancellation():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(run_calculation(job_for(), timeout=0.001))
    assert exc.value.status_code == 504


def test_new_routes_require_real_auth_by_default():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get(f"/projects/{uuid4()}/analysis-runs")
        assert response.status_code == 401


def test_followup_context_ready_stage_and_provider_failure_preserves_downloads(analysis_client):
    client, store, endpoint, body = analysis_client
    run = client.post(endpoint, json=body).json()
    assert run["status"] == "completed"
    file = store.data["project_files"][0]
    file["metadata"] = inspect_file(
        file["original_name"], store.objects["original"], "dataset", Settings(_env_file=None)
    )
    conversation = store.data["conversations"][0]
    conversation["primary_goal"] = "Comparar medidas entre grupos"
    provider = ControlledProvider()
    provider.replies = [
        AssistantReply(
            response="La g de Hedges aplica una corrección del sesgo a d usando SD combinada. No demuestra causalidad. ¿Tienes alguna duda?",
            suggested_stage="understanding",
        )
    ]
    client.app.state.provider = provider
    turns = f"/projects/{store.project_id}/conversations/{conversation['id']}/turns"
    response = client.post(
        turns, json={"request_id": str(uuid4()), "content": "¿Qué significa la g de Hedges de este resultado?"}
    )
    assert response.status_code == 200, response.text
    context = provider.contexts[0][0]
    assert context["analysis_results"][0]["run_id"] == run["id"]
    assert (
        context["analysis_results"][0]["components"][0]["statistics"]["hedges_g"]
        == run["result"]["components"][0]["statistics"]["hedges_g"]
    )
    assert conversation["current_stage"] == "ready"
    provider.replies = [HTTPException(503, "Gemini no está disponible.")]
    failed = client.post(turns, json={"request_id": str(uuid4()), "content": "¿Qué significa ese valor p?"})
    assert failed.status_code == 503
    base = f"/projects/{store.project_id}/analysis-runs/{run['id']}"
    assert client.get(base).json()["result"] == run["result"]
    assert client.get(base + "/download").status_code == 200
