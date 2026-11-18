"""Transporte Responses simulado: prohibidas las solicitudes reales durante estas pruebas."""

import asyncio
import copy
import json
import logging
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from google.genai import errors
from test_gemini import SDKDouble

from app.core.config import Settings
from app.services.gemini import GeminiProvider
from app.services.gemini_schema import reply_schema
from app.services.openai_provider import MODEL, OpenAIProvider, reply_schema_openai
from app.services.provider_runtime import ProviderSession, RequestBudget
from scripts.diagnose_terra import schema_openai


def completed(reply=None):
    return {
        "id": "resp_synthetic",
        "model": MODEL,
        "status": "completed",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 200,
            "output_tokens_details": {"reasoning_tokens": 150},
            "input_tokens_details": {"cached_tokens": 20},
        },
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(reply or {"response": "Comprendí los datos.", "suggested_stage": "goal"}),
                    }
                ],
            },
        ],
    }


def settings(**kwargs):
    return Settings(_env_file=None, openai_api_key="credencial-sintetica", openai_terra_enabled=True, **kwargs)


def test_valid_transport_matches_isolated_schema_and_has_no_tools_or_retries(caplog):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=completed(), headers={"x-request-id": "req_synthetic"})

    provider = OpenAIProvider(settings(openai_max_output_tokens=8000), transport=httpx.MockTransport(handle))
    session = ProviderSession(provider, "openai", MODEL)
    with caplog.at_level(logging.INFO):
        reply = asyncio.run(session.generate({"private": "contenido-sintetico"}, "corrección sintética"))
    assert reply.response == "Comprendí los datos."
    payload = json.loads(calls[0].content)
    assert len(calls) == 1 and str(calls[0].url) == "https://api.openai.com/v1/responses"
    assert calls[0].headers["authorization"] == "Bearer credencial-sintetica"
    assert payload["model"] == MODEL and payload["store"] is False
    assert payload["max_output_tokens"] == 8000 and payload["reasoning"] == {"effort": "medium"}
    assert "tools" not in payload and "previous_response_id" not in payload
    assert payload["text"]["format"]["schema"] == schema_openai(reply_schema()) == reply_schema_openai(reply_schema())
    assert session.trace["requests"] == 1
    assert session.trace["generations"][0]["usage"]["reasoning_tokens"] == 150
    assert session.trace["generations"][0]["request_id"] == "req_synthetic"
    assert session.trace["generations"][0]["response_model"] == MODEL
    assert "credencial-sintetica" not in caplog.text and "contenido-sintetico" not in caplog.text
    assert "corrección sintética" not in caplog.text


@pytest.mark.parametrize("enabled,key,category", [(False, "x", "disabled"), (True, "", "not_configured")])
def test_unconfigured_never_contacts_provider(enabled, key, category):
    def forbidden(_):
        pytest.fail("No debe acceder a red")

    provider = OpenAIProvider(
        Settings(_env_file=None, openai_terra_enabled=enabled, openai_api_key=key),
        transport=httpx.MockTransport(forbidden),
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(provider.generate({}))
    assert exc.value.status_code == 503 and exc.value.headers["X-Statia-Error"] == "openai_" + category


@pytest.mark.parametrize(
    "status,body,category,local",
    [
        (400, {"param": "text.format.schema"}, "schema", 502),
        (400, {"param": "model"}, "model", 502),
        (400, {}, "invalid_request", 502),
        (401, {}, "credentials", 502),
        (403, {}, "permissions", 502),
        (404, {}, "model", 502),
        (429, {}, "quota", 429),
        (500, {}, "unavailable", 503),
        (503, {}, "unavailable", 503),
        (504, {}, "timeout", 504),
        (302, {}, "provider", 502),
    ],
)
def test_http_errors_are_distinct_sanitized_and_not_retried(status, body, category, local, caplog):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={"error": {**body, "message": "contenido-privado credencial-sintetica"}},
            headers={"location": "https://example.com"},
        )

    provider = OpenAIProvider(settings(), transport=httpx.MockTransport(handle))
    with caplog.at_level(logging.INFO), pytest.raises(HTTPException) as exc:
        asyncio.run(provider.generate({}))
    assert len(calls) == 1
    assert exc.value.status_code == local
    assert exc.value.headers == {"X-Statia-Error": "openai_" + category, "X-OpenAI-Status": str(status)}
    assert "contenido-privado" not in caplog.text + str(exc.value.detail)
    assert "credencial-sintetica" not in caplog.text + str(exc.value.detail)


@pytest.mark.parametrize(
    "change,category",
    [
        ({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}, "incomplete"),
        ({"status": "failed"}, "incomplete"),
        ({"output": [{"type": "function_call", "name": "run_code"}]}, "invalid_response"),
        (
            {"output": [{"type": "message", "role": "assistant", "status": "incomplete", "content": []}]},
            "invalid_response",
        ),
        (
            {
                "output": [
                    {"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "refusal"}]}
                ]
            },
            "refusal",
        ),
        ({"output": []}, "invalid_response"),
        ({"output": None}, "invalid_response"),
        ({"output": [None]}, "invalid_response"),
        ({"usage": "invalid"}, "invalid_response"),
    ],
)
def test_incomplete_and_unsupported_output_rejected_with_usage(change, category):
    data = {**completed(), **change}
    provider = OpenAIProvider(settings(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data)))
    session = ProviderSession(provider, "openai", MODEL)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(session.generate({}))
    assert exc.value.headers["X-Statia-Error"] == "openai_" + category
    assert session.trace["generations"][0]["category"] == category


@pytest.mark.parametrize("body", ["no json", "{}", "[]", '{"response":"x","suggested_stage":"goal","unexpected":true}'])
def test_invalid_json_and_internal_contract(body):
    data = completed()
    data["output"][1]["content"][0]["text"] = body
    provider = OpenAIProvider(settings(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data)))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(provider.generate({}))
    assert exc.value.headers["X-Statia-Error"] == "openai_invalid_response"


@pytest.mark.parametrize(
    "error,category", [(httpx.ReadTimeout("privado"), "timeout"), (httpx.ConnectError("privado"), "connectivity")]
)
def test_network_errors_never_retry(error, category):
    calls = []

    def handle(request):
        calls.append(request)
        raise error

    provider = OpenAIProvider(settings(), transport=httpx.MockTransport(handle))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(provider.generate({}))
    assert len(calls) == 1 and exc.value.headers["X-Statia-Error"] == "openai_" + category


def test_cancellation_closes_transport_without_retry():
    class Blocking(httpx.AsyncBaseTransport):
        closed = False

        async def handle_async_request(self, request):
            await asyncio.Event().wait()

        async def aclose(self):
            self.closed = True

    transport = Blocking()
    provider = OpenAIProvider(settings(), transport=transport)

    async def run():
        task = asyncio.create_task(provider.generate({}))
        await asyncio.sleep(0.03)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert transport.closed
    assert len(provider.budget.requests) == 1


def test_wall_clock_timeout_cancels_transport():
    async def blocking(_):
        await asyncio.Event().wait()

    config = settings().model_copy(update={"openai_timeout_seconds": 0.02})
    provider = OpenAIProvider(config, transport=httpx.MockTransport(blocking))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(provider.generate({}))
    assert exc.value.status_code == 504 and len(provider.budget.requests) == 1


def test_request_limits_include_semantic_corrections_and_do_not_leak_traces():
    provider = OpenAIProvider(
        settings(ai_requests_per_minute=2, ai_max_requests_per_turn=1),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=completed())),
    )
    session = ProviderSession(provider, "openai", MODEL)
    asyncio.run(session.generate({}))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(session.generate({}, "corrección"))
    assert exc.value.headers["X-Statia-Error"] == "provider_request_limit"
    other = ProviderSession(provider, "openai", MODEL)
    asyncio.run(other.generate({}))
    assert other.trace is not session.trace and len(other.trace["generations"]) == 1
    with pytest.raises(HTTPException):
        asyncio.run(ProviderSession(provider, "openai", MODEL).generate({}))


def test_sliding_budget_expires(monkeypatch):
    budget = RequestBudget(settings(ai_requests_per_minute=1))
    monkeypatch.setattr("app.services.provider_runtime.time.monotonic", lambda: 100)
    budget.reserve()
    with pytest.raises(HTTPException):
        budget.reserve()
    monkeypatch.setattr("app.services.provider_runtime.time.monotonic", lambda: 161)
    budget.reserve()


def test_metrics_reject_sensitive_ids_and_invalid_counts(caplog):
    data = copy.deepcopy(completed())
    data["id"] = "private response with spaces"
    data["usage"] = {"input_tokens": True, "output_tokens": -1}
    provider = OpenAIProvider(settings(), transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data)))
    session = ProviderSession(provider, "openai", MODEL)
    with caplog.at_level(logging.INFO):
        asyncio.run(session.generate({}))
    generation = session.trace["generations"][0]
    assert generation["response_id"] is None and generation["usage"]["input_tokens"] is None
    assert "private response" not in caplog.text


def test_concurrent_turns_keep_usage_and_response_ids_separate():
    async def handle(request):
        name = json.loads(json.loads(request.content)["input"])["turn"]
        await asyncio.sleep(0.01)
        data = completed()
        data["id"] = "resp_" + name
        data["usage"]["input_tokens"] = 100 if name == "first" else 200
        return httpx.Response(200, json=data)

    provider = OpenAIProvider(settings(), transport=httpx.MockTransport(handle))
    first, second = ProviderSession(provider, "openai", MODEL), ProviderSession(provider, "openai", MODEL)

    async def run():
        await asyncio.gather(first.generate({"turn": "first"}), second.generate({"turn": "second"}))

    asyncio.run(run())
    assert first.trace["requests"] == second.trace["requests"] == 1
    assert first.trace["generations"][0]["response_id"] == "resp_first"
    assert second.trace["generations"][0]["response_id"] == "resp_second"
    assert first.trace["generations"][0]["usage"]["input_tokens"] == 100
    assert second.trace["generations"][0]["usage"]["input_tokens"] == 200


def test_gemini_limits_include_existing_transient_retry(monkeypatch):
    sdk = SDKDouble([errors.ServerError(503, {"error": {"message": "No disponible"}})])
    monkeypatch.setattr("app.services.gemini.genai.Client", lambda **_: sdk)
    monkeypatch.setattr("app.services.gemini.asyncio.sleep", AsyncMock())
    provider = GeminiProvider(
        Settings(
            _env_file=None, gemini_api_key="gemini-sintetica", ai_requests_per_minute=1, gemini_max_output_tokens=512
        )
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(provider.generate({}))
    assert exc.value.headers["X-Statia-Error"] == "provider_request_limit"
    assert len(sdk.calls) == 1 and sdk.calls[0]["config"].max_output_tokens == 512
