"""Reproduce rollback del backend real 74b9577 sobre 007 y demuestra la barrera 008.

No se usa un doble de begin_chat_turn: FastAPI/Auth/REST reales del checkout histórico
consumen RPC PostgreSQL local. Solo Auth remoto/REST y los modelos están simulados.
"""

import base64
import io
import json
import os
import subprocess
import sys
import tarfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx
import psutil
import pytest

from app.core.config import Settings
from app.services.profiling import inspect_file

ROOT = Path(__file__).resolve().parents[2]
OLD = "74b957700dd1eca34e59a2c488bc44e85f26ec4d"
A = "00000000-0000-0000-0000-000000000001"


def archived_backend(tmp_path_factory, revision):
    path = tmp_path_factory.mktemp("historical-backend")
    archive = subprocess.check_output(["git", "archive", revision, "backend/app"], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as package:
        package.extractall(path, filter="data")
    return path / "backend"


@pytest.fixture(scope="module")
def old_backend(tmp_path_factory):
    return archived_backend(tmp_path_factory, OLD)


@pytest.fixture(scope="module")
def audited_backend(tmp_path_factory):
    return archived_backend(tmp_path_factory, "f6df957af358e5cf6f2c781a936c16d3e16b8aff")


@contextmanager
def postgres_server(version):
    helper = ROOT / "supabase/tests/helpers/postgrest-bridge.mjs"
    process = subprocess.Popen(
        ["node", str(helper), version],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        line = process.stdout.readline()
        assert line, process.stderr.read()
        endpoint = "http://127.0.0.1:" + str(json.loads(line)["port"])
        with httpx.Client(base_url=endpoint, headers={"Authorization": "Bearer synthetic-a"}, timeout=15) as client:
            yield version, client, endpoint
    finally:
        process.terminate()
        process.wait(timeout=15)


@pytest.fixture(params=["007", "008"])
def postgres(request):
    with postgres_server(request.param) as result:
        yield result


@pytest.fixture
def protected_postgres():
    with postgres_server("008") as result:
        yield result


def rpc(client, name, **args):
    response = client.post("/rest/v1/rpc/" + name, json=args)
    assert response.status_code == 200, response.text
    return response.json()


def query(client, sql, *params):
    response = client.post("/test/query", json={"sql": sql, "params": list(params)})
    assert response.status_code == 200, response.text
    return response.json()


def seed(client, provider="openai"):
    project, cid, fid = str(uuid4()), None, str(uuid4())
    query(
        client,
        "insert into public.projects(id,user_id,name,project_type) values($1,$2,'Sintético','general')",
        project,
        A,
    )
    cid = rpc(client, "create_provider_conversation", p_project=project, p_provider=provider, p_source=None)
    query(client, "update public.conversations set current_stage='goal' where id=$1", cid)
    metadata = inspect_file(
        "sintetico.csv", b"medida,grupo\n10,A\n20,B\n30,A\n40,B\n", "dataset", Settings(_env_file=None)
    )
    query(
        client,
        "insert into public.project_files(id,project_id,uploaded_by,original_name,storage_path,file_type,file_role,file_size,metadata) values($1,$2,$3,'sintetico.csv',$4,'csv','dataset',50,$5::jsonb)",
        fid,
        project,
        A,
        f"{A}/{project}/{fid}/sintetico.csv",
        json.dumps(metadata),
    )
    query(
        client,
        "insert into public.conversation_files(conversation_id,file_id,project_id) values($1,$2,$3)",
        cid,
        fid,
        project,
    )
    response = client.post(
        "/test/put-object",
        json={
            "path": f"{A}/{project}/{fid}/sintetico.csv",
            "data": base64.b64encode(b"medida,grupo\n10,A\n20,B\n30,A\n40,B\n").decode("ascii"),
        },
    )
    assert response.status_code == 200, response.text
    return project, cid, str(uuid4())


def run_local_python(command, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GEMINI_", "OPENAI_", "SUPABASE_"))}
    env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen(
        command,
        cwd=tmp_path,
        env=env,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = process.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        parent = psutil.Process(process.pid)
        for child in reversed(parent.children(recursive=True)):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        process.kill()
        process.communicate(timeout=10)
        pytest.fail("El backend histórico excedió el tiempo local; se terminó todo su árbol de procesos.")
    assert process.returncode == 0, stderr
    return json.loads(stdout.strip().splitlines()[-1])


def run_backend(path, endpoint, ids, mode, tmp_path):
    return run_local_python(
        [
            sys.executable,
            str(ROOT / "backend/tests/helpers/run_historical_backend.py"),
            str(path),
            endpoint,
            *ids,
            mode,
        ],
        tmp_path,
    )


def test_real_backend_rollback_after_failed_terra(postgres, old_backend, audited_backend, tmp_path):
    migration, client, endpoint = postgres
    ids = seed(client)
    first = run_backend(audited_backend, endpoint, ids, "terra-fail", tmp_path)
    assert first["status"] == 503 and first["terra_calls"] == 1 and first["gemini_calls"] == 0
    before = query(client, "select provider,model,status from public.chat_requests where request_id=$1", ids[2])[0]
    assert before == {"provider": "openai", "model": "gpt-6.1-terra", "status": "failed"}
    assert (
        query(client, "select assistant_provider from public.conversations where id=$1", ids[1])[0][
            "assistant_provider"
        ]
        == "openai"
    )
    rollback = run_backend(old_backend, endpoint, ids, "gemini-success", tmp_path)
    after = query(client, "select provider,model,status from public.chat_requests where request_id=$1", ids[2])[0]
    assert (
        query(client, "select assistant_provider from public.conversations where id=$1", ids[1])[0][
            "assistant_provider"
        ]
        == "openai"
    )
    if migration == "007":
        # Defecto comprobado: llamada Gemini real en el flujo histórico, atribución Terra intacta.
        assert rollback["status"] == 200 and rollback["gemini_calls"] == 1
        assert after == {**before, "status": "completed"}
    else:
        assert rollback["status"] == 409 and rollback["gemini_calls"] == 0
        assert after == before
        correct = run_backend(ROOT / "backend", endpoint, ids, "terra-success", tmp_path)
        assert correct["status"] == 200 and correct["terra_calls"] == 1 and correct["gemini_calls"] == 0
        replay = run_backend(old_backend, endpoint, ids, "gemini-success", tmp_path)
        assert replay["status"] == 200 and replay["reply"]["replayed"] and replay["gemini_calls"] == 0
        messages = query(
            client,
            "select metadata from public.messages where conversation_id=$1 and metadata->'generation'->>'provider'='openai'",
            ids[1],
        )
        assert len(messages) == 1 and messages[0]["metadata"]["generation"]["model"] == "gpt-6.1-terra"


def test_legacy_gemini_remains_compatible(postgres, old_backend, tmp_path):
    _, client, endpoint = postgres
    ids = seed(client, provider="gemini")
    first = run_backend(old_backend, endpoint, ids, "gemini-success", tmp_path)
    assert first["status"] == 200 and first["gemini_calls"] == 1
    replay = run_backend(old_backend, endpoint, ids, "gemini-success", tmp_path)
    assert replay["status"] == 200 and replay["reply"]["replayed"] and replay["gemini_calls"] == 0
    assert query(client, "select provider,model from public.chat_requests where request_id=$1", ids[2])[0] == {
        "provider": "gemini",
        "model": None,
    }


def test_runtime_gate_refuses_terra_without_008(postgres, tmp_path):
    version, client, endpoint = postgres
    ids = seed(client)
    result = run_backend(ROOT / "backend", endpoint, ids, "terra-fail", tmp_path)
    assert result["status"] == 503 and result["gemini_calls"] == 0
    if version == "007":
        assert result["terra_calls"] == 0
        assert not query(client, "select * from public.chat_requests where request_id=$1", ids[2])
    else:
        assert result["terra_calls"] == 1


def test_protected_sql_retry_binding_rls_and_concurrent_requests(protected_postgres):
    _, client, endpoint = protected_postgres
    project, cid, rid = seed(client)
    payload = {"action": "message", "display": "Sintético"}
    args = dict(p_conversation=cid, p_request=rid, p_payload=payload, p_provider="openai", p_model="gpt-6.1-terra")
    assert rpc(client, "begin_provider_chat_turn", **args) == "started"
    assert rpc(client, "begin_provider_chat_turn", **args) == "busy"
    # Tampoco completar con una respuesta legacy sin procedencia.
    wrong = client.post(
        "/rest/v1/rpc/finish_chat_turn",
        json={
            "p_conversation": cid,
            "p_request": rid,
            "p_result": {"content": "Respuesta Gemini ajena", "stage": "goal", "message_type": "text"},
        },
    )
    assert wrong.status_code == 400 and wrong.json()["code"] == "P0001"
    rpc(client, "fail_chat_turn", p_conversation=cid, p_request=rid)
    rpc(client, "select_conversation_provider", p_conversation=cid, p_provider="gemini", p_expected="openai")
    assert (
        rpc(client, "begin_provider_chat_turn", **{**args, "p_provider": "gemini", "p_model": "gemini-test"})
        == "provider_changed"
    )
    # No se alteran la selección explícita ni la procedencia de la solicitud fallida.
    assert (
        query(client, "select assistant_provider from public.conversations where id=$1", cid)[0]["assistant_provider"]
        == "gemini"
    )
    assert query(client, "select provider,model from public.chat_requests where request_id=$1", rid)[0] == {
        "provider": "openai",
        "model": "gpt-6.1-terra",
    }
    forbidden = client.post(
        "/test/query",
        json={"sql": "update public.chat_requests set provider='gemini' where request_id=$1", "params": [rid]},
    )
    assert forbidden.status_code == 400
    rpc(client, "select_conversation_provider", p_conversation=cid, p_provider="openai", p_expected="gemini")
    # Dos solicitudes HTTP concurrentes sobre el mismo UUID: solo una adquiere el turno.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = list(pool.map(lambda _: rpc(client, "begin_provider_chat_turn", **args), range(2)))
    assert sorted(states) == ["busy", "started"]
    assert (
        len(
            query(
                client,
                "select id from public.messages where conversation_id=$1 and metadata->>'request_id'=$2",
                cid,
                rid,
            )
        )
        == 1
    )
    rpc(
        client,
        "finish_chat_turn",
        p_conversation=cid,
        p_request=rid,
        p_result={
            "stage": "goal",
            "content": "Terra sintético",
            "message_type": "text",
            "metadata": {"generation": {"provider": "openai", "model": "gpt-6.1-terra"}},
        },
    )
    assert rpc(client, "begin_chat_turn", p_conversation=cid, p_request=rid, p_payload=payload) == "completed"
    other = client.post(
        "/test/query",
        json={"sql": "select * from public.chat_requests where conversation_id=$1", "params": [cid]},
        headers={"Authorization": "Bearer synthetic-b"},
    )
    assert other.json() == []
    foreign = client.post(
        "/rest/v1/rpc/begin_provider_chat_turn", json=args, headers={"Authorization": "Bearer synthetic-b"}
    )
    assert foreign.status_code == 400
    functions = query(
        client,
        "select proname,prosecdef from pg_proc where proname in ('begin_chat_turn','begin_provider_chat_turn','provider_rollback_safety')",
    )
    assert len(functions) == 3 and all(not f["prosecdef"] for f in functions)
    assert not query(
        client, "select has_function_privilege('anon','public.provider_rollback_safety()','execute') as allowed"
    )[0]["allowed"]


def test_known_gemini_model_cannot_be_retried_by_legacy_backend(protected_postgres, old_backend, tmp_path):
    _, client, endpoint = protected_postgres
    ids = seed(client, provider="gemini")
    # Backend auditado deja un modelo conocido que el legacy no puede acreditar.
    from app.models.chat import Turn

    body = Turn(request_id=ids[2], content="Describe las mediciones").model_dump(
        mode="json", exclude={"request_id"}, exclude_none=True
    )
    body["display"] = "Describe las mediciones"
    rpc(
        client,
        "begin_provider_chat_turn",
        p_conversation=ids[1],
        p_request=ids[2],
        p_payload=body,
        p_provider="gemini",
        p_model="gemini-original",
    )
    rpc(client, "fail_chat_turn", p_conversation=ids[1], p_request=ids[2])
    result = run_backend(old_backend, endpoint, ids, "gemini-success", tmp_path)
    assert result["status"] == 409 and result["gemini_calls"] == 0
    assert (
        rpc(
            client,
            "begin_provider_chat_turn",
            p_conversation=ids[1],
            p_request=ids[2],
            p_payload=body,
            p_provider="gemini",
            p_model="gemini-otro",
        )
        == "provider_changed"
    )
    assert (
        rpc(
            client,
            "begin_provider_chat_turn",
            p_conversation=ids[1],
            p_request=ids[2],
            p_payload=body,
            p_provider="gemini",
            p_model="gemini-original",
        )
        == "started"
    )


@pytest.mark.parametrize("historically_accepted", [False, True])
def test_descriptive_audit_with_real_audited_backend_and_fixed_backend(
    protected_postgres, audited_backend, tmp_path, historically_accepted
):
    _, client, endpoint = protected_postgres
    project, cid, _ = seed(client, provider="gemini")
    file = query(client, "select * from public.project_files where project_id=$1", project)[0]
    variables = [
        {"file_id": file["id"], "sheet": "tabla", "column": column, "role": role}
        for column, role in [("medida", "outcome"), ("grupo", "group")]
    ]
    plan = {
        "schema_version": 1,
        "title": "Reproducción descriptiva",
        "objective": "Describir `medida` por `grupo`",
        "variables": variables,
        "procedure": "descriptive",
        "method": "Descriptivos de `medida` por `grupo`",
        "justification": "Descripción de datos sintéticos",
        "requirements": ["Revisar tipos y datos"],
        "limitations": ["Sin inferencia"],
        "expected_outputs": ["Resúmenes globales", "Resúmenes por grupo", "Frecuencias de la variable de agrupación"],
    }
    pid = str(uuid4())
    query(
        client,
        "insert into public.analysis_proposals(id,conversation_id,title,objective,analysis_plan) values($1,$2,$3,$4,$5::jsonb)",
        pid,
        cid,
        plan["title"],
        plan["objective"],
        json.dumps(plan),
    )
    helper = ROOT / "backend/tests/helpers/run_historical_statistics.py"

    def run(path):
        return run_local_python([sys.executable, str(helper), str(path), endpoint, project, cid, pid], tmp_path)

    if historically_accepted:
        before = run(audited_backend)
        assert before["acceptance"] == 200 and before["conversation_stage"] == "ready"
        assert before["preparation_status"] == "READY" and before["calculation_status"] == "completed"
        assert before["table_rows"] == [2]  # Solo A/B; falta resumen global.
        assert not any("Frecuencias" in title for title in before["table_titles"])
    history = query(client, "select * from public.analysis_proposals where id=$1", pid)
    after = run(ROOT / "backend")
    assert after["calculation_status"] == "blocked"
    if historically_accepted:
        assert after["acceptance"] == 200  # Replay: no reescribir la decisión anterior.
        assert after["preparation_status"] == "UNSUPPORTED"
    else:
        assert after["acceptance"] == 422 and after["conversation_stage"] == "goal"
    assert query(client, "select * from public.analysis_proposals where id=$1", pid) == history
