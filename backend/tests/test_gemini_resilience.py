"""Límites reales asyncio y SDK oficial sobre HTTP simulado; nunca llaman a Google."""

import asyncio
import copy
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import test_chat_api
from fastapi import HTTPException
from google import genai
from google.genai import errors
from test_chat_api import attach_dataset, new, plan, reply, turn
from test_gemini import SDKDouble

from app.core.config import Settings
from app.services import gemini

api = test_chat_api.api


def provider():
    return gemini.GeminiProvider(Settings(_env_file=None, gemini_api_key="clave-ficticia"))


def test_single_retry_jitter_is_bounded_and_keeps_identical_request(monkeypatch):
    sdk = SDKDouble([errors.APIError(503, {}), json.dumps(reply())])
    sleep = AsyncMock()
    original_uniform = gemini.random.uniform

    def jitter(low, high):
        assert (low, high) == (1.0, 2.0)
        value = original_uniform(low, high)
        assert low <= value <= high
        return value

    monkeypatch.setattr(gemini.genai, "Client", lambda **_: sdk)
    monkeypatch.setattr(gemini.asyncio, "sleep", sleep)
    monkeypatch.setattr(gemini.random, "uniform", jitter)
    asyncio.run(provider().generate({"stage": "goal"}))
    assert len(sdk.calls) == 2
    assert sdk.calls[0] == sdk.calls[1]
    sleep.assert_awaited_once()
    assert 1 <= sleep.await_args.args[0] <= 2


@pytest.mark.parametrize("blocked_phase", ["client", "backoff", "second_attempt"])
def test_generation_budget_cancels_client_wait_and_retry(monkeypatch, blocked_phase):
    class BlockingSDK(SDKDouble):
        closed = False

        async def __aenter__(self):
            if blocked_phase == "client":
                await asyncio.Event().wait()
            return self

        async def __aexit__(self, *args):
            self.closed = True

        async def generate_content(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise errors.APIError(503, {})
            await asyncio.Event().wait()

    async def wait(_):
        if blocked_phase == "backoff":
            await asyncio.Event().wait()

    sdk = BlockingSDK([])
    monkeypatch.setattr(gemini.genai, "Client", lambda **_: sdk)
    monkeypatch.setattr(gemini, "GENERATION_BUDGET_SECONDS", 0.04)
    monkeypatch.setattr(gemini.asyncio, "sleep", wait)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(provider().generate({}))
    assert caught.value.status_code == 504
    assert caught.value.headers == {"X-Statia-Error": "gemini_timeout"}
    assert len(sdk.calls) == {"client": 0, "backoff": 1, "second_attempt": 2}[blocked_phase]
    if blocked_phase != "client":
        assert sdk.closed


def test_attempt_timeout_does_not_retry_uncertain_remote_result(monkeypatch):
    class BlockingSDK(SDKDouble):
        async def generate_content(self, **kwargs):
            self.calls.append(kwargs)
            await asyncio.Event().wait()

    sdk = BlockingSDK([])
    instance = provider()
    instance.settings = instance.settings.model_copy(update={"gemini_timeout_seconds": 0.02})
    monkeypatch.setattr(gemini.genai, "Client", lambda **_: sdk)
    monkeypatch.setattr(gemini, "GENERATION_BUDGET_SECONDS", 1)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(instance.generate({}))
    assert caught.value.status_code == 504
    assert len(sdk.calls) == 1


def test_external_cancellation_is_preserved_and_closes_client(monkeypatch):
    entered = asyncio.Event()

    class BlockingSDK(SDKDouble):
        closed = False

        async def generate_content(self, **kwargs):
            entered.set()
            await asyncio.Event().wait()

        async def __aexit__(self, *args):
            self.closed = True

    async def scenario():
        task = asyncio.create_task(provider().generate({}))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    sdk = BlockingSDK([])
    monkeypatch.setattr(gemini.genai, "Client", lambda **_: sdk)
    asyncio.run(scenario())
    assert sdk.closed


@pytest.mark.parametrize("code,attempts", [(429, 2), (500, 2), (503, 2), (504, 1)])
def test_official_sdk_has_no_hidden_retries_and_preserves_upstream_status(monkeypatch, code, attempts):
    original_client = genai.Client
    requests = []
    clients = []

    async def scenario():
        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(code, json={"error": {"code": code, "message": "Fallo sintético"}})

        transport = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        def client(**kwargs):
            assert kwargs["http_options"].retry_options.attempts == 1
            assert kwargs["http_options"].timeout == 35000
            kwargs["http_options"].httpx_async_client = transport
            instance = original_client(**kwargs)
            clients.append(instance)
            return instance

        monkeypatch.setattr(gemini.genai, "Client", client)
        monkeypatch.setattr(gemini.asyncio, "sleep", AsyncMock())
        try:
            with pytest.raises(HTTPException) as caught:
                await provider().generate({"stage": "goal"})
            assert caught.value.headers["X-Gemini-Status"] == str(code)
            assert len(requests) == attempts
        finally:
            await transport.aclose()
            for instance in clients:
                instance.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("code,attempts", [(429, 2), (500, 2), (503, 2), (504, 1)])
def test_transient_failure_keeps_turn_files_and_safe_replay(api, monkeypatch, code, attempts):
    client, store, _ = api
    path = new(client, store)
    assert turn(client, path, action="instrument_no").status_code == 200
    fid = attach_dataset(client, path)
    sdk = SDKDouble([errors.APIError(code, {})] * attempts + [json.dumps(reply(proposals=[plan(fid)]))])
    monkeypatch.setattr(gemini.genai, "Client", lambda **_: sdk)
    monkeypatch.setattr(gemini.asyncio, "sleep", AsyncMock())
    client.app.state.provider = provider()
    before = client.get(path).json()
    originals = copy.deepcopy(store.objects)
    files = copy.deepcopy(store.data["project_files"])
    request_id = str(uuid4())

    failed_response = turn(client, path, action="files_ready", request_id=request_id)
    assert failed_response.headers["X-Gemini-Status"] == str(code)
    failed = client.get(path).json()
    assert failed["retry_turn"]["request_id"] == request_id
    assert failed["conversation"]["active_request_id"] is None
    assert failed["conversation"]["current_stage"] == before["conversation"]["current_stage"]
    assert failed["conversation"]["stage_data"] == before["conversation"]["stage_data"]
    assert len(failed["messages"]) == len(before["messages"]) + 1
    assert not failed["proposals"]
    assert store.objects == originals and store.data["project_files"] == files

    assert turn(client, path, action="files_ready", request_id=request_id).status_code == 200
    completed = client.get(path).json()
    assert len(completed["proposals"]) == 1
    assert len(completed["messages"]) == len(before["messages"]) + 2
    assert turn(client, path, action="files_ready", request_id=request_id).json()["replayed"]
    assert client.get(path).json() == completed
    assert len(sdk.calls) == attempts + 1


def test_diagnostics_do_not_log_private_errors_during_retries(monkeypatch, caplog):
    secret = "no-imprimir-clave"
    sdk = SDKDouble([errors.APIError(503, {"error": {"message": secret}})] * 2)
    monkeypatch.setattr(gemini.genai, "Client", lambda **_: sdk)
    monkeypatch.setattr(gemini.asyncio, "sleep", AsyncMock())
    with pytest.raises(HTTPException) as caught:
        asyncio.run(provider().generate({"private": secret}))
    assert secret not in caplog.text and secret not in caught.value.detail
    assert "upstream_status=503" in caplog.text


def test_invalid_json_never_triggers_semantic_or_transport_retry(monkeypatch):
    sdk = SDKDouble(["{incompleto"])
    monkeypatch.setattr(gemini.genai, "Client", lambda **_: sdk)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(provider().generate({}))
    assert caught.value.headers["X-Statia-Error"] == "gemini_invalid_response"
    assert len(sdk.calls) == 1


def test_generation_budget_leaves_room_for_turn_persistence():
    assert 2 * gemini.GENERATION_BUDGET_SECONDS <= 130 < 150
