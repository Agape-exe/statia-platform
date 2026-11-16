"""El diagnóstico es acotado y su salida solo contiene métricas, con HTTP simulado."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.core.config import Settings
from scripts import diagnose_gemini as diagnostic


def settings():
    return Settings(_env_file=None, gemini_api_key="clave-que-no-debe-salir")


def test_cases_keep_controlled_dataset_context_and_explicit_counts():
    cases = {key: diagnostic.build_case(key, settings(), diagnostic.SYSTEM) for key in "ABCDEF"}
    assert cases["A"].system == "" and cases["B"].files == []
    assert cases["D"].context == cases["E"].context
    assert cases["D"].schema and cases["E"].schema is None
    for key in "CDEF":
        assert cases[key].files == cases["D"].files
        assert cases[key].context["recommendations_requested"] == (key == "F")
        assert "samples" not in cases[key].context["files"][0]


@pytest.mark.parametrize("args", [["--repeat", "3"], ["--cases", "A", "A"], ["--cases", "G"]])
def test_cli_rejects_unbounded_or_duplicate_requests(args):
    with pytest.raises(SystemExit):
        diagnostic.parse_args(args)


def test_dry_run_never_creates_provider_or_reports_live_success(monkeypatch, capsys):
    monkeypatch.setattr(diagnostic, "Settings", settings)
    monkeypatch.setattr(diagnostic.genai, "Client", lambda **_: pytest.fail("Llamada real en modo seco"))
    assert asyncio.run(diagnostic.main(["--cases", "A", "D", "E"])) == 0
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(records) == 3
    assert all(r["result"] == "dry_run" and r["provider_http_status"] is None for r in records)


@pytest.mark.parametrize("code", [429, 500, 503, 504])
def test_live_diagnostic_single_attempt_and_no_sensitive_output(monkeypatch, capsys, code):
    class SDK:
        def __init__(self, **kwargs):
            assert kwargs["http_options"].retry_options.attempts == 1
            self.aio = self.models = self
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def generate_content(self, **kwargs):
            self.calls += 1
            raise errors.APIError(code, {"error": {"message": "no-imprimir-respuesta-privada"}})

    sdk = SDK(http_options=SimpleNamespace(retry_options=SimpleNamespace(attempts=1)))
    monkeypatch.setattr(diagnostic, "Settings", settings)
    monkeypatch.setattr(diagnostic.genai, "Client", lambda **_: sdk)
    assert asyncio.run(diagnostic.main(["--live", "--cases", "D"])) == 1
    output = capsys.readouterr().out
    record = json.loads(output)
    assert record["provider_http_status"] == code
    assert record["contract_valid"] is None and sdk.calls == 1
    assert "no-imprimir" not in output and "clave-que-no-debe-salir" not in output


def test_http_success_is_separate_from_invalid_contract_and_usage():
    case = diagnostic.build_case("D", settings(), diagnostic.SYSTEM)
    record = diagnostic.metadata(case, settings(), "current")
    record["provider_http_status"] = 200
    response = SimpleNamespace(text='{"proposals":[]}', usage_metadata=SimpleNamespace(total_token_count=100))
    diagnostic.validate_response(case, response, record)
    assert record["result"] == "failed" and record["category"] == "gemini_invalid_response"
    assert record["provider_http_status"] == 200 and record["tokens"]["total_token_count"] == 100
