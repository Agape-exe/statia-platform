"""Solo respuestas sintéticas y transporte HTTP simulado; nunca valida al modelo real."""

import ast
import copy
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.models.chat import AssistantReply, Plan
from app.services.gemini_schema import reply_schema
from app.services.planning_errors import PlanningError
from scripts import diagnose_terra as diagnostic
from scripts.diagnose_terra import (
    protect_evidence_directory as real_protect_evidence_directory,
)

LEGACY_SHA256 = "95d8581522b1635c2f208fc6303ac808fd1e5279a8de09d6dee94298447a5c26"


@pytest.fixture(autouse=True)
def isolate_private_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(diagnostic, "protect_evidence_directory", lambda _: None)


def variable(column, role="outcome"):
    return {"file_id": diagnostic.FILE_ID, "sheet": "tabla", "column": column, "role": role}


def plan(procedure, variables, method, **changes):
    return {
        "title": "Alternativa exploratoria",
        "objective": "Explorar " + ", ".join("`" + v["column"] + "`" for v in variables),
        "variables": variables,
        "procedure": procedure,
        "method": method,
        "justification": "Las medidas y categorías permiten explorar opciones tentativas.",
        "requirements": [
            "Independencia: supuesto pendiente de verificar con el diseño; revisar muestreo, "
            "repeticiones, pareamiento y conglomerados.",
            "Revisar distribuciones, atípicos, linealidad y significado de las variables antes de inferir.",
        ],
        "limitations": ["Sin inferencia hasta confirmar diseño y supuestos; asociación no implica causalidad."],
        "expected_outputs": ["Tablas y gráficos únicamente tras aceptación y ejecución autorizadas."],
        "methodology_confirmed": False,
        **changes,
    }


def simulated_reply(identifier):
    measures = [variable("medida_a"), variable("medida_b", "predictor")]
    grouped = [variable("medida_a"), variable("grupo", "group")]
    all_variables = measures + [variable("grupo", "group")]
    descriptive = plan("descriptive", all_variables, "Estadística descriptiva y frecuencias por tipo.")
    correlation = plan("correlation", measures, "Pearson condicionado a independencia, linealidad y supuestos.")
    comparison = plan("group_comparison", grouped, "ANOVA de Welch global, condicionado a diseño y supuestos.")
    components = [
        {"procedure": p["procedure"], "method": p["method"], "variables": copy.deepcopy(p["variables"])}
        for p in (descriptive, correlation, comparison)
    ]
    integral = plan(
        "integral", all_variables, "Exploración conjunta mediante componentes compatibles.", components=components
    )
    return AssistantReply.model_validate(
        {
            "response": "Opciones tentativas: independencia pendiente de verificar con el diseño, sin cálculos.",
            "suggested_stage": "proposal",
            "involved_file_ids": [diagnostic.FILE_ID],
            "selected_variables": all_variables,
            "confirmation_required": True,
            "proposals": [descriptive, correlation, comparison, integral] if identifier == "M" else [integral],
        }
    )


def wire_value(value, schema):
    # Simular exactamente las claves requeridas del transporte D, sin campos internos.
    if value is None:
        assert "null" in schema["type"]
        return None
    kinds = schema.get("type")
    if kinds == "object" or isinstance(kinds, list) and "object" in kinds:
        return {key: wire_value(value[key], spec) for key, spec in schema["properties"].items()}
    if kinds == "array":
        return [wire_value(item, schema["items"]) for item in value]
    if "enum" in schema:
        assert value in schema["enum"]
    return value


def response_body(identifier="I"):
    case = diagnostic.build_case(identifier)
    reply = wire_value(simulated_reply(identifier).model_dump(), case.schema)
    return {
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(reply)}],
            },
        ],
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 500,
            "input_tokens_details": {"cached_tokens": 200},
            "output_tokens_details": {"reasoning_tokens": 100},
        },
    }


def live_args(identifier="I"):
    # Tarifas de prueba aritmética, NO tarifas comerciales verificadas.
    return [
        "--live",
        "--case",
        identifier,
        "--input-usd-per-m",
        "2",
        "--output-usd-per-m",
        "6",
        "--cached-input-usd-per-m",
        "0.5",
        "--pricing-source",
        "fixture local sin valor comercial",
    ]


def test_legacy_a_d_bytes_and_converter_unchanged_without_import_or_execution():
    legacy = Path(diagnostic.ROOT / "test_terra_statia_env.py")
    if not legacy.exists():
        pytest.skip("Evidencia A/D local no versionada, ausente en este checkout.")
    assert hashlib.sha256(legacy.read_bytes()).hexdigest() == LEGACY_SHA256
    module = ast.parse(legacy.read_text(encoding="utf-8"))
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "schema_openai")
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "legacy_converter_only", "exec"), namespace)
    expected = namespace["schema_openai"](reply_schema())
    assert diagnostic.schema_openai(reply_schema()) == expected
    assert diagnostic.build_case("M").schema == diagnostic.build_case("I").schema == expected


def test_contexts_reproducible_and_separate_without_invented_design():
    multi, integral = [diagnostic.build_case(key) for key in ("M", "I")]
    assert multi.context["recommendations_requested"] is True
    assert integral.context["recommendations_requested"] is False
    assert multi.files == integral.files
    assert diagnostic.digest(multi.context) == diagnostic.digest(diagnostic.build_case("M").context)
    assert multi.context["independence_evidence"] == integral.context["independence_evidence"] == []
    assert multi.context["analysis_results"] == []
    assert "samples" not in multi.context["files"][0]
    assert multi.files[0]["metadata"]["profile"]["row_count"] == 30
    for case in (multi, integral):
        wire = wire_value(simulated_reply(case.identifier).model_dump(), case.schema)
        reply = AssistantReply.model_validate(wire)
        assert all(p.schema_version == 1 and p.filters == [] for p in reply.proposals)
        assert all(c.depends_on == [] for p in reply.proposals for c in p.components)
        diagnostic.validate_scenario(case, reply)


def test_i_accepts_two_distinct_components_without_forcing_all_families():
    case = diagnostic.build_case("I")
    reply = simulated_reply("I")
    reply.proposals[0].components.pop()  # descripción + correlación bastan
    diagnostic.validate_scenario(case, reply)


def test_m_accepts_two_options_when_components_cover_requested_families():
    reply = simulated_reply("M")
    reply.proposals = [reply.proposals[0], reply.proposals[-1]]
    diagnostic.validate_scenario(diagnostic.build_case("M"), reply)


@pytest.mark.parametrize("problem", ["context", "required", "nullable", "open_object"])
def test_local_preparation_rejects_corrupted_context_and_schema(problem):
    case = diagnostic.build_case("I")
    if problem == "context":
        case.context["recommendations_requested"] = True
    elif problem == "required":
        case.schema["required"].pop()
    elif problem == "nullable":
        case.schema["properties"]["detected_goal"]["nullable"] = True
    else:
        case.schema["additionalProperties"] = True
    with pytest.raises(ValueError):
        diagnostic.validate_case(case)


def test_default_does_not_construct_http_client_or_read_credentials(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "clave-local-no-imprimir")
    monkeypatch.setattr(diagnostic.httpx, "Client", lambda **_: pytest.fail("Red en modo seco"))
    monkeypatch.setattr(diagnostic, "dotenv_values", lambda *_: pytest.fail("Credenciales en modo seco"))
    assert diagnostic.main([]) == 0
    output = capsys.readouterr().out
    records = [json.loads(line) for line in output.splitlines()]
    assert [r["case"] for r in records] == ["M", "I"]
    assert all(r["result"] == "dry_run" and r["requests_attempted"] == 0 and r["tokens"] is None for r in records)
    assert all(r["contract_valid"] is None and r["scenario_valid"] is None for r in records)
    assert "clave-local-no-imprimir" not in output


@pytest.mark.parametrize(
    "args",
    [
        ["--live"],
        ["--live", "--case", "M"],
        ["--case", "M", "I"],
        ["--case", "A"],
        ["--input-usd-per-m", "nan"],
        ["--output-usd-per-m", "-1"],
        ["--input-usd-per-m", "inf"],
    ],
)
def test_cli_rejects_unsafe_or_unbounded_execution(args):
    with pytest.raises(SystemExit):
        diagnostic.parse_args(args)


@pytest.mark.parametrize("identifier", ["M", "I"])
def test_live_with_mock_transport_one_post_metrics_and_no_content(monkeypatch, capsys, identifier):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.method == "POST" and str(request.url) == diagnostic.URL
        body = json.loads(request.content)
        assert body == diagnostic.payload(diagnostic.build_case(identifier), "gpt-6.1-terra")
        assert "tools" not in body and body["store"] is False
        return httpx.Response(200, json=response_body(identifier))

    def transport(**kwargs):
        assert kwargs == {"retries": 0}
        return httpx.MockTransport(respond)

    monkeypatch.setenv("OPENAI_API_KEY", "clave-local-no-imprimir")
    monkeypatch.setattr(diagnostic.httpx, "HTTPTransport", transport)
    assert diagnostic.main(live_args(identifier)) == 0
    output = capsys.readouterr().out
    record = json.loads(output)
    assert len(calls) == record["requests_attempted"] == 1
    assert record["result"] == "success" and record["scenario_valid"] is True
    assert record["tokens"] == {
        "input": 1000,
        "output": 500,
        "cached_input": 200,
        "reasoning": 100,
        "visible_output": 400,
    }
    assert record["estimated_cost_usd"] == pytest.approx(0.0047)
    assert record["manual_review_required"] is True
    assert "clave-local-no-imprimir" not in output and "Opciones tentativas" not in output


@pytest.mark.parametrize("problem", [429, 503, 307, "timeout", "network", "json", "shape"])
def test_errors_never_retry_or_expose_provider_message(monkeypatch, capsys, problem):
    calls = []

    def respond(request):
        calls.append(request)
        if problem == "timeout":
            raise httpx.ReadTimeout("clave-local-no-imprimir", request=request)
        if problem == "network":
            raise httpx.ConnectError("respuesta-privada", request=request)
        if problem == "json":
            return httpx.Response(200, text="respuesta-privada")
        if problem == "shape":
            return httpx.Response(200, json=["respuesta-privada"])
        return httpx.Response(
            problem,
            json={"error": {"message": "respuesta-privada clave-local-no-imprimir"}},
            headers={"location": "https://example.invalid/no-seguir"},
        )

    monkeypatch.setenv("OPENAI_API_KEY", "clave-local-no-imprimir")
    monkeypatch.setattr(diagnostic.httpx, "HTTPTransport", lambda **_: httpx.MockTransport(respond))
    assert diagnostic.main(live_args()) == 1
    output = capsys.readouterr().out
    record = json.loads(output)
    assert len(calls) == record["requests_attempted"] == 1
    assert record["result"] == "failed"
    assert "respuesta-privada" not in output and "clave-local-no-imprimir" not in output


@pytest.mark.parametrize(
    "problem", ["incomplete", "failed", "queued", "refusal", "empty", "contract", "tool", "message_status"]
)
def test_completed_required_even_when_incomplete_contains_valid_json(problem):
    body = response_body()
    if problem in {"incomplete", "failed", "queued"}:
        body["status"] = problem
    elif problem == "refusal":
        body["output"][1]["content"] = [{"type": "refusal", "refusal": "respuesta-privada"}]
    elif problem == "empty":
        body["output"] = []
    elif problem == "contract":
        body["output"][1]["content"][0]["text"] = '{"response":"incompleta"}'
    elif problem == "tool":
        body["output"] = [{"type": "function_call", "name": "no_ejecutar"}]
    else:
        body["output"][1]["status"] = "incomplete"
    record = {}
    diagnostic.parse_response(diagnostic.build_case("I"), body, record)
    assert record["result"] == "failed" and not record.get("scenario_valid")


@pytest.mark.parametrize(
    "problem",
    [
        "file",
        "sheet",
        "column",
        "identifier",
        "identifier_component",
        "nested",
        "single_family",
        "cycle",
        "dependency",
        "component_foreign",
        "uncovered_variable",
        "catalog",
        "two_group_method",
        "family",
        "categorical_correlation",
        "confirmed_design",
        "confirmed_prose",
        "missing_pending",
        "false_independence",
        "number_response",
        "number_plan",
        "number_component",
        "multiple_i",
        "no_integral",
        "missing_family",
        "no_confirmation",
        "too_few_m",
        "extra_field",
    ],
)
def test_rejects_invalid_references_components_design_coverage_and_numbers(problem):
    identifier = "M" if problem in {"no_integral", "missing_family", "too_few_m"} else "I"
    data = simulated_reply(identifier).model_dump()
    p = data["proposals"][-1]
    if problem in {"file", "sheet", "column"}:
        p["variables"][0][{"file": "file_id", "sheet": "sheet", "column": "column"}[problem]] = "inexistente"
    elif problem == "identifier":
        p["variables"][0] = variable("registro_id")
    elif problem == "identifier_component":
        p["variables"].append(variable("registro_id", "description"))
        p["components"][0]["variables"].append(variable("registro_id"))
    elif problem == "nested":
        p["components"][0]["procedure"] = "integral"
    elif problem == "single_family":
        p["components"] = [p["components"][0]] * 2
    elif problem == "cycle":
        p["components"][0]["depends_on"] = [1]
        p["components"][1]["depends_on"] = [0]
    elif problem == "dependency":
        p["components"][0]["depends_on"] = [9]
    elif problem == "component_foreign":
        p["components"][0]["variables"].append(variable("inexistente"))
    elif problem == "uncovered_variable":
        p["variables"].append(variable("registro_id", "description"))
    elif problem == "catalog":
        p["components"][0]["method"] = "Algoritmo de regresión desconocido"
    elif problem == "two_group_method":
        p["components"][2]["method"] = "t de Student"
    elif problem == "family":
        p["components"][0]["method"] = "Pearson"
    elif problem == "categorical_correlation":
        p["components"][1]["variables"] = [variable("medida_a"), variable("grupo")]
    elif problem == "confirmed_design":
        p["methodology_confirmed"] = True
    elif problem == "confirmed_prose":
        p["components"][0]["method"] += "; independencia confirmada."
    elif problem == "missing_pending":
        p["requirements"] = ["Revisar tipos."]
    elif problem == "false_independence":
        data["response"] = "Filas distintas garantizan independencia."
    elif problem == "number_response":
        data["response"] += " r = 0.95"
    elif problem == "number_plan":
        p["limitations"] = ["La media = 15.3"]
    elif problem == "number_component":
        p["components"][1]["method"] += "; r = 0.95"
    elif problem == "multiple_i":
        data["proposals"] *= 2
    elif problem == "no_integral":
        data["proposals"].pop()
    elif problem == "missing_family":
        data["proposals"] = [data["proposals"][0], p]
        p["components"].pop()
    elif problem == "no_confirmation":
        data["confirmation_required"] = False
    elif problem == "too_few_m":
        data["proposals"] = [p]
    else:
        p["campo_inventado"] = True
    with pytest.raises((PlanningError, ValidationError)):
        diagnostic.validate_scenario(diagnostic.build_case(identifier), AssistantReply.model_validate(data))


def test_valid_dependencies_use_existing_contract_even_though_d_transport_omits_them():
    reply = simulated_reply("I")
    reply.proposals[0].components[1].depends_on = [0]
    reply.proposals[0].components[2].depends_on = [0]
    diagnostic.validate_scenario(diagnostic.build_case("I"), reply)


def reply_with_single_plan(index):
    reply = simulated_reply("M")
    reply.proposals = [reply.proposals[index]]
    case = diagnostic.build_case("M")
    # La comprobación por plan no aplica una cuota de recomendaciones múltiples.
    return case, reply.proposals[0]


def validate_local_plan(case, source):
    from app.services.gemini import validate_plan

    validate_plan(source, case.files, diagnostic.PROJECT, case.context)
    diagnostic.validate_plan_scenario(case, source)
    diagnostic.validate_scenario_prose(source.model_dump(), case.context)


@pytest.mark.parametrize("warning", [None, "La independencia es desconocida; solo se describen registros observados."])
def test_observed_descriptive_needs_no_independence_requirement(warning):
    case, source = reply_with_single_plan(0)
    source.requirements = ["Revisar unidades, categorías, ausencias y atípicos."]
    source.limitations = [warning or "Descripción de registros observados sin generalización."]
    validate_local_plan(case, source)
    assert not source.methodology_confirmed


@pytest.mark.parametrize("index", [1, 2])
@pytest.mark.parametrize("location", ["requirements", "limitations", "method"])
def test_inferential_pending_warning_can_be_local_in_different_fields(index, location):
    case, source = reply_with_single_plan(index)
    source.requirements = ["Revisar tipos y distribuciones."]
    source.limitations = ["No implica causalidad."]
    warning = "Independencia pendiente de verificar con el diseño antes de inferir."
    if location == "method":
        source.method += "; " + warning
    else:
        getattr(source, location).append(warning)
    validate_local_plan(case, source)
    assert not source.methodology_confirmed and not case.context["independence_evidence"]


@pytest.mark.parametrize("index", [1, 2, 3])
def test_inferential_cannot_replace_independence_warning_with_other_pending_assumptions(index):
    case, source = reply_with_single_plan(index)
    source.requirements = ["Pendiente verificar unidades y tipos."]
    source.limitations = ["No implica causalidad."]
    with pytest.raises(PlanningError, match="Cada procedimiento inferencial"):
        validate_local_plan(case, source)


@pytest.mark.parametrize("scope", ["componente descriptivo", "correlación de Pearson"])
def test_integral_warning_scoped_to_one_component_does_not_cover_others(scope):
    case, source = reply_with_single_plan(3)
    source.requirements = [f"Verificar independencia únicamente para el {scope}."]
    source.limitations = ["No implica causalidad."]
    with pytest.raises(PlanningError, match="Cada procedimiento inferencial"):
        validate_local_plan(case, source)


def test_integral_all_inferential_components_can_use_explicit_shared_warning():
    case, source = reply_with_single_plan(3)
    source.requirements = ["Revisar unidades."]
    source.limitations = [
        "Independencia pendiente de verificar con el diseño para todos los componentes inferenciales."
    ]
    validate_local_plan(case, source)
    source.limitations = ["La independencia del componente descriptivo es desconocida."]
    source.components[1].method += "; verificar independencia antes de inferir."
    source.components[2].method += "; independencia pendiente de revisión del diseño."
    validate_local_plan(case, source)


@pytest.mark.parametrize("with_warning", [False, True])
def test_descriptive_confidence_interval_requires_pending_design_warning(with_warning):
    case, source = reply_with_single_plan(0)
    source.requirements = ["Revisar unidades."]
    source.limitations = ["No implica causalidad."]
    source.expected_outputs = ["Intervalo de confianza de la media."]
    if with_warning:
        source.limitations.append("Independencia desconocida, pendiente de verificar antes de estimar intervalos.")
        validate_local_plan(case, source)
    else:
        with pytest.raises(PlanningError, match="Cada procedimiento inferencial"):
            validate_local_plan(case, source)


@pytest.mark.parametrize("negation", ["sin inferencia", "sin inferencias ni intervalos de confianza"])
def test_descriptive_expressly_without_inference_remains_descriptive(negation):
    case, source = reply_with_single_plan(0)
    source.requirements = ["Revisar unidades."]
    source.limitations = ["Descripción de registros observados."]
    source.method = "Estadística descriptiva " + negation + "."
    source.expected_outputs = ["Tablas descriptivas sin intervalos de confianza."]
    validate_local_plan(case, source)


def test_integral_pearson_interval_does_not_turn_descriptive_component_into_inference():
    case, source = reply_with_single_plan(3)
    source.expected_outputs = ["Intervalo de confianza para Pearson."]
    source.requirements = ["Revisar unidades."]
    source.limitations = ["No implica causalidad."]
    source.components[1].method += "; independencia pendiente de verificar."
    source.components[2].method += "; verificar independencia con el diseño."
    assert not diagnostic.requires_independence(source.components[0], source)
    validate_local_plan(case, source)


def test_saved_live_plans_preserve_evidence_and_unverified_outputs_require_scope(monkeypatch):
    path = diagnostic.ROOT.parent / "docs/TERRA_M_LIVE_RESULT_2026-11-16.json"
    if not path.exists():
        pytest.skip("Evidencia real local ausente en este checkout.")
    original_bytes = path.read_bytes()
    assert (
        hashlib.sha256(original_bytes).hexdigest() == "62c6e9021c08cbb796851a5a2d077e6a9ca1422d34feb5e0235b529349130758"
    )
    saved = json.loads(original_bytes)
    monkeypatch.setattr(diagnostic.httpx, "Client", lambda **_: pytest.fail("Red en reevaluación local"))
    case = diagnostic.build_case("M")
    metrics = saved["metrics"][0]
    assert metrics["result"] == "failed" and metrics["category"] == "independence"
    assert diagnostic.digest(case.context) == metrics["context_sha256"]
    assert diagnostic.digest(diagnostic.payload(case, metrics["model"])) == metrics["payload_sha256"]
    # Solo adaptar nombres de campos persistidos a Plan. No fabricar los campos
    # raíz ausentes de AssistantReply ni sustituirlos por una respuesta simulada.
    plans = []
    for item in saved["proposals"]:
        fields = {key: value for key, value in item.items() if key in Plan.model_fields}
        fields["requirements"] = item["pending_assumptions"]
        source = Plan.model_validate(fields)
        # La independencia corregida no acredita productos de texto libre, tampoco
        # en inferenciales. No reinterpretar los condicionales ni adaptar evidencia
        # para que pase: sus originales y hashes permanecen intactos.
        with pytest.raises(PlanningError) as output_error:
            validate_local_plan(case, source)
        assert output_error.value.category in {"output_scope", "output_capability"}
        plans.append(source)
    assert len(plans) == 4 and len({p.procedure for p in plans}) == 4
    with pytest.raises(PlanningError) as original_failure:
        diagnostic.validate_independence("\n".join(plans[0].requirements), case.context)
    assert original_failure.value.category == "independence"
    diagnostic.validate_scenario_prose(
        {key: saved[key] for key in ("assistant_response", "questions", "warnings")}, case.context
    )
    assert path.read_bytes() == original_bytes


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_unknown_independence_is_never_confirmed_even_for_descriptive(index):
    case, source = reply_with_single_plan(index)
    source.limitations.append("Independencia confirmada por tener filas diferentes.")
    with pytest.raises(PlanningError):
        validate_local_plan(case, source)


def test_integral_descriptive_warning_does_not_excuse_false_inferential_component_claim():
    case, source = reply_with_single_plan(3)
    source.components[1].method += "; independencia confirmada."
    with pytest.raises(PlanningError):
        validate_local_plan(case, source)


def test_global_response_warning_does_not_excuse_missing_plan_warning():
    case = diagnostic.build_case("M")
    reply = simulated_reply("M")
    reply.proposals[1].requirements = ["Revisar unidades."]
    reply.proposals[1].limitations = ["No implica causalidad."]
    with pytest.raises(PlanningError, match="Cada procedimiento inferencial"):
        diagnostic.validate_scenario(case, reply)


def test_usage_absent_is_unknown_and_reasoning_is_not_billed_twice():
    args = diagnostic.parse_args(live_args())
    record = {}
    diagnostic.record_usage({}, record, args)
    assert all(value is None for value in record["tokens"].values())
    body = response_body()
    args.cached_input_usd_per_m = None
    diagnostic.record_usage(body, record, args)
    assert record["estimated_cost_usd"] == pytest.approx(0.005)
    assert record["cost_basis"] == "configured_rates_no_cache_discount"


def test_missing_key_stops_before_http(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(diagnostic, "dotenv_values", lambda *_: {})
    monkeypatch.setattr(diagnostic.httpx, "Client", lambda **_: pytest.fail("Red sin credencial"))
    assert diagnostic.main(live_args()) == 2
    assert json.loads(capsys.readouterr().out)["requests_attempted"] == 0


def test_live_i_saves_exact_complete_original_and_separate_validations(monkeypatch, capsys):
    body = response_body("I")
    # Conservar espacios, campos anulables y valores originales, sin model_dump.
    original = " \n" + body["output"][1]["content"][0]["text"] + "\n "
    body["output"][1]["content"][0]["text"] = original
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=body)

    monkeypatch.setenv("OPENAI_API_KEY", "clave-sintetica-no-persistir")
    monkeypatch.setattr(diagnostic.httpx, "HTTPTransport", lambda **_: httpx.MockTransport(respond))
    assert diagnostic.main(live_args("I")) == 0
    record = json.loads(capsys.readouterr().out)
    folder = Path(record["evidence_dir"])
    assert len(calls) == 1 and not folder.is_relative_to(diagnostic.ROOT.parent)
    assert (folder / "assistant_reply.json").read_bytes() == original.encode("utf-8")
    stored = json.loads((folder / "metrics_and_validations.json").read_text(encoding="utf-8"))
    assert stored == record
    assert stored["json_integrity_valid"] and stored["statia_native_valid"] and stored["scenario_valid"]
    assert stored["proposal_count"] == 1 and stored["component_count"] == 3
    assert stored["assistant_reply_sha256"] == hashlib.sha256(original.encode()).hexdigest()
    assert all("clave-sintetica-no-persistir" not in p.read_text(encoding="utf-8") for p in folder.iterdir())
    assert json.loads((folder / "criteria.json").read_text(encoding="utf-8"))["max_output_tokens"] == 8000


def test_evidence_protection_failure_prevents_any_request(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "clave-sintetica-no-persistir")
    monkeypatch.setattr(diagnostic, "protect_evidence_directory", lambda _: (_ for _ in ()).throw(OSError("privado")))
    monkeypatch.setattr(diagnostic.httpx, "Client", lambda **_: pytest.fail("Red antes de proteger evidencia"))
    assert diagnostic.main(live_args("I")) == 2
    assert json.loads(capsys.readouterr().out)["category"] == "evidence_preparation"


def test_evidence_store_never_overwrites_or_saves_secrets():
    evidence = diagnostic.EvidenceStore("I", "clave-sintetica-no-persistir")
    evidence.write("assistant_reply.json", '{"original": true}')
    with pytest.raises(FileExistsError):
        evidence.write("assistant_reply.json", '{"otro": true}')
    for text in ("clave-sintetica-no-persistir", "persona@example.org", "sk-1234567890abcdef"):
        with pytest.raises(diagnostic.EvidenceError):
            evidence.write("prohibido.json", text)
    assert not (evidence.directory / "prohibido.json").exists()


def test_windows_evidence_acl_removes_inheritance_and_grants_only_user_and_system(monkeypatch, tmp_path):
    if diagnostic.os.name != "nt":
        pytest.skip("Protección ACL específica de Windows.")
    from types import SimpleNamespace

    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout='"usuario","S-1-5-21-100-200-300-1001"' if args[0] == "whoami" else "")

    monkeypatch.setattr(diagnostic.subprocess, "run", run)
    real_protect_evidence_directory(tmp_path)
    assert len(calls) == 4
    assert calls[1][0] == ["icacls", str(tmp_path), "/reset"]
    assert calls[2][0][-2:] == ["*S-1-5-21-100-200-300-1001:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"]
    assert "/inheritance:r" in calls[2][0]
    args, kwargs = calls[3]
    assert Path(args[0]).stem in {"pwsh", "powershell"}
    assert args[1:3] == ["-NoProfile", "-Command"]
    assert "Get-Acl -LiteralPath" in args[3] and "AreAccessRulesProtected" in args[3]
    assert "'S-1-5-18'" in args[3] and "$rules.Count -ne 2" in args[3]
    assert kwargs["env"]["STATIA_EVIDENCE_DIRECTORY"] == str(tmp_path)


def test_incomplete_generation_keeps_original_fragment_and_failure_without_retry(monkeypatch, capsys):
    body = response_body("I")
    body["status"] = "incomplete"
    body["incomplete_details"] = {"reason": "max_output_tokens"}
    original = body["output"][1]["content"][0]["text"]
    monkeypatch.setenv("OPENAI_API_KEY", "clave-sintetica-no-persistir")
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=body)

    monkeypatch.setattr(diagnostic.httpx, "HTTPTransport", lambda **_: httpx.MockTransport(respond))
    assert diagnostic.main(live_args("I")) == 1
    record = json.loads(capsys.readouterr().out)
    assert record["category"] == "response_not_completed" and len(calls) == 1
    assert record["contract_valid"] is None and record["incomplete_reason"] == "max_output_tokens"
    assert (Path(record["evidence_dir"]) / "assistant_reply.json").read_bytes() == original.encode()


def test_invalid_json_is_persisted_without_reconstructing_fields(monkeypatch, capsys):
    body = response_body("I")
    original = '{"response": "fragmento"'
    body["output"][1]["content"][0]["text"] = original
    monkeypatch.setenv("OPENAI_API_KEY", "clave-sintetica-no-persistir")
    monkeypatch.setattr(
        diagnostic.httpx,
        "HTTPTransport",
        lambda **_: httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )
    assert diagnostic.main(live_args("I")) == 1
    record = json.loads(capsys.readouterr().out)
    assert record["category"] == "invalid_json" and record["requests_attempted"] == 1
    assert (Path(record["evidence_dir"]) / "assistant_reply.json").read_bytes() == original.encode()


def test_sensitive_response_is_not_saved_or_printed_and_no_retry(monkeypatch, capsys):
    body = response_body("I")
    body["output"][1]["content"][0]["text"] = '{"response":"persona@example.org"}'
    monkeypatch.setenv("OPENAI_API_KEY", "clave-sintetica-no-persistir")
    monkeypatch.setattr(
        diagnostic.httpx,
        "HTTPTransport",
        lambda **_: httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )
    assert diagnostic.main(live_args("I")) == 1
    output = capsys.readouterr().out
    record = json.loads(output)
    assert record["category"] == "evidence_sensitive_or_unwritable" and record["requests_attempted"] == 1
    assert "persona@example.org" not in output
    assert not (Path(record["evidence_dir"]) / "assistant_reply.json").exists()


def test_evidence_cannot_be_created_inside_checkout(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(diagnostic.ROOT.parent))
    monkeypatch.setenv("XDG_STATE_HOME", str(diagnostic.ROOT.parent))
    with pytest.raises(diagnostic.EvidenceError):
        diagnostic.EvidenceStore("I", "")


def test_i_requires_different_statistical_methods_not_just_family_labels():
    case = diagnostic.build_case("I")
    reply = simulated_reply("I")
    source = reply.proposals[0]
    source.components = [source.components[0], source.components[0].model_copy(deep=True)]
    source.components[1].procedure = "exploratory"
    with pytest.raises(PlanningError, match="dos métodos estadísticos distintos"):
        diagnostic.validate_scenario(case, reply)
