"""Preparación aislada M/I. Seco por defecto; --live permite UNA solicitud sin reintentos.

No importar ni ejecutar test_terra_statia_env.py: se conserva íntegro como evidencia A/D.
Solo métricas JSONL en stdout. En --live, conservar la respuesta original en un
directorio local protegido fuera del repositorio; nunca guardar credenciales.
"""

import argparse
import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from dotenv import dotenv_values  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.models.chat import AssistantReply, Turn  # noqa: E402
from app.services.analysis_context import validate_numeric_claims  # noqa: E402
from app.services.conversation_text import normalize  # noqa: E402
from app.services.gemini import (  # noqa: E402
    SYSTEM,
    build_context,
    reference_validator,
    validate_reply,
)
from app.services.gemini_schema import reply_schema  # noqa: E402
from app.services.independence import validate_independence  # noqa: E402
from app.services.planning_errors import PlanningError  # noqa: E402
from app.services.profiling import inspect_file  # noqa: E402
from app.services.statistics.catalog import CATALOG  # noqa: E402
from app.services.statistics.methods import named_methods  # noqa: E402
from scripts.diagnose_gemini import PROJECT, Case  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
URL = "https://api.openai.com/v1/responses"
FILE_ID = "00000000-0000-0000-0000-000000000002"
LIMITS = {"M": 12000, "I": 8000}
QUESTIONS = {
    "M": (
        "Analiza las características del dataset y recomiéndame entre dos y cuatro alternativas estadísticas "
        "apropiadas y diferenciadas. Cubre descripción, comparación entre grupos y correlación; incluye una "
        "alternativa integral con componentes explícitos cuando sea viable. La cobertura puede estar repartida "
        "entre alternativas y componentes. No ejecutes cálculos ni presentes resultados. "
    ),
    "I": (
        "Genera una única propuesta de análisis integral (procedure=integral) con al menos dos procedimientos "
        "distintos compatibles, expresados como componentes explícitos. Puedes combinar descripción, correlación "
        "o comparación exploratoria global entre grupos si se justifican; no necesitas incluirlos todos. "
        "No ejecutes cálculos ni presentes resultados. "
    ),
}
PENDING = (
    "Son datos sintéticos, sin diseño de recolección informado. La independencia es un supuesto pendiente de "
    "verificar con el diseño: revisar muestreo, repeticiones, pareamiento y conglomerados. No la confirmes. "
    "Las opciones inferenciales son tentativas y condicionadas a esa revisión; methodology_confirmed=false. "
    "Usa medida_a, medida_b y grupo; registro_id es solo un identificador. No inventes hipótesis, observaciones "
    "ni diseños. No unas, limpies ni modifiques datos. No elijas dos grupos excluyendo el tercero. "
    "Cada componente debe nombrar métodos reconocibles del catálogo execution_methods; comparison=null para "
    "ANOVA global, descripción y correlación. Identifica requisitos pendientes en cada plan y explica límites. "
    "No incluyas cifras estadísticas, tampoco resúmenes numéricos del perfil, en esta propuesta de métodos."
)


def schema_openai(n):
    """Misma conversión que en D: nullable, campos requeridos y objetos cerrados."""
    if isinstance(n, list):
        return [schema_openai(item) for item in n]
    if not isinstance(n, dict):
        return n
    out = {key: schema_openai(val) for key, val in n.items() if key != "nullable"}
    if n.get("nullable"):
        kind = out.get("type")
        if isinstance(kind, str):
            out["type"] = [kind, "null"]
    if n.get("type") == "object":
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties", {}).keys())
    return out


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def build_case(identifier):
    # No cargar .env ni overrides de ausencias al preparar el dataset sintético.
    settings = Settings(_env_file=None, missing_value_overrides={})
    rows = ["registro_id,medida_a,medida_b,grupo"]
    for i in range(30):
        a = 10 + i * 0.73 + (i % 4) * 0.17
        b = 18 + i * 0.91 + (i % 5) * 0.39
        rows.append(f"{i + 1},{a:.2f},{b:.2f},{'ABC'[i % 3]}")
    files = [
        {
            "id": FILE_ID,
            "original_name": "terra_sintetico.csv",
            "file_role": "dataset",
            "metadata": inspect_file("terra_sintetico.csv", "\n".join(rows).encode(), "dataset", settings),
        }
    ]
    question = QUESTIONS[identifier] + PENDING
    context = build_context(
        PROJECT,
        {"current_stage": "goal", "stage_data": {}},
        [{"role": "user", "content": question}],
        files,
        Turn(request_id="00000000-0000-0000-0000-000000000001", content=question),
        settings,
    )
    # Se conserva la detección real: I no contiene un pedido de alternativas múltiples.
    case = Case(identifier, SYSTEM, context, schema_openai(reply_schema(structured=False)), files)
    validate_case(case)
    return case


def validate_case(case):
    context = case.context
    expected = {"descriptive", "correlation", "group_comparison", "integral"}
    if (
        set(context["available_analyses"]) != expected
        or context["recommendations_requested"] != (case.identifier == "M")
        or context["independence_evidence"]
        or context["analysis_results"]
        or not context["canonical_objectives"]
    ):
        raise ValueError("scenario_context")
    file = context["files"][0]
    columns = {c["name"]: c for c in file["columns"]}
    if (
        "samples" in file
        or file["selected_sheet"] != case.files[0]["metadata"]["selected_sheet"]
        or set(columns) != {"registro_id", "medida_a", "medida_b", "grupo"}
        or not columns["registro_id"]["possible_identifier"]
        or any(columns[c]["statistical_type"] != "quantitative" for c in ("medida_a", "medida_b"))
        or columns["grupo"]["unique"] != 3
    ):
        raise ValueError("scenario_profile")
    for method in context["execution_methods"]:
        if method["code"] not in CATALOG:
            raise ValueError("scenario_catalog")
    validate_schema(case.schema)


def validate_schema(node):
    """Comprobar el subconjunto usado por D, sin afirmar aceptación remota del modelo."""
    if isinstance(node, list):
        for item in node:
            validate_schema(item)
    elif isinstance(node, dict):
        if "nullable" in node or "$ref" in node or "default" in node:
            raise ValueError("transport_schema")
        kinds = node.get("type", [])
        if kinds == "object" or isinstance(kinds, list) and "object" in kinds:
            if node.get("additionalProperties") is not False or set(node["required"]) != set(node["properties"]):
                raise ValueError("transport_object")
        for value in node.values():
            validate_schema(value)


def prose(value):
    """Textos libres, excluyendo IDs/referencias y códigos estructurados."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key not in {"file_id", "sheet", "column", "role", "procedure", "involved_file_ids", "depends_on"}:
                yield from prose(item)
    elif isinstance(value, list):
        for item in value:
            yield from prose(item)
    elif isinstance(value, str):
        yield value


def requires_independence(step, plan):
    """Resumir registros no exige independencia; los IC de media sí son inferencia."""
    if step.procedure not in {"descriptive", "exploratory"}:
        return True
    texts = [step.method]
    if step is plan:
        texts.extend([plan.objective, *plan.expected_outputs])
    for text in texts:
        text = normalize(text)
        negated_term = r"(?:pruebas? inferenciales?|inferencias?|intervalos?(?: de confianza)?|ic)\b"
        text = re.sub(
            r"\b(?:sin|no (?:incluir|calcular|estimar|realizar)|no se (?:incluiran|calcularan|estimaran))\s+"
            + negated_term
            + r"(?:\s+(?:ni|y)\s+"
            + negated_term
            + r")*",
            "",
            text,
        )
        if re.search(r"\binferenci\w*|\binferencial\w*|\bintervalos? (?:de )?confianza\b|\bic\b", text):
            return True
    return False


def validate_plan_independence(plan, context):
    """Advertencias locales o compartidas, sin convertirlas en evidencia del diseño.

    Las advertencias generales del plan cubren sus componentes inferenciales.
    Una advertencia restringida a una familia no cubre otras familias.
    No se heredan advertencias de otra propuesta ni de la prosa de la respuesta.
    """
    steps = plan.components if plan.procedure == "integral" else [plan]
    scopes = {
        "descriptive": r"descriptiv|exploratori",
        "correlation": r"correlaci|pearson|spearman",
        "group_comparison": r"comparaci|anova|welch|student|kruskal|mann",
    }
    shared = [*plan.requirements, *plan.limitations]
    for step in steps:
        if not requires_independence(step, plan):
            continue
        pending = False
        for text in [*shared, step.method]:
            for clause in re.split(r"[.;\n]", normalize(text)):
                if "independen" not in clause:
                    continue
                mentioned = {family for family, pattern in scopes.items() if re.search(pattern, clause)}
                family = "descriptive" if step.procedure == "exploratory" else step.procedure
                if mentioned and family not in mentioned:
                    continue
                # Reutilizar el control nativo de afirmaciones falsas, sin tratar
                # 'revisar tipos' en otra frase como advertencia de independencia.
                validate_independence(clause, context, require_pending=False)
                if re.search(
                    r"pendiente|verificar|comprobar|evaluar|revisar|desconocid|sin confirmar|"
                    r"no (?:se puede |esta |se ha )?(?:garantiz|confirm|verific)|no deducir",
                    clause,
                ):
                    pending = True
        if not pending:
            raise PlanningError(
                "scenario_assumptions",
                "Cada procedimiento inferencial debe reconocer independencia pendiente en sus requisitos, "
                "limitaciones o método, con alcance aplicable al componente.",
            )


def validate_plan_scenario(case, plan):
    """Controles adicionales por plan, compartidos por generación y revisión local."""
    column_for = reference_validator({f["id"]: f for f in case.files})
    if plan.methodology_confirmed or plan.joins or plan.filters or plan.comparison is not None:
        raise PlanningError("scenario_design", "No confirmar metodología ni alterar alcance en este escenario.")
    validate_plan_independence(plan, case.context)
    steps = plan.components if plan.procedure == "integral" else [plan]
    for step in steps:
        if step.procedure not in {"descriptive", "exploratory", "correlation", "group_comparison"}:
            raise PlanningError("scenario_catalog", "La familia no es viable con el contexto disponible.")
        methods = named_methods(step)
        if not methods or any(code not in CATALOG or step.procedure not in CATALOG[code].families for code in methods):
            raise PlanningError("scenario_catalog", "Método ausente o incompatible con la familia del catálogo.")
        if step.procedure == "group_comparison":
            outcomes = [v for v in step.variables if v.role == "outcome"]
            groups = [v for v in step.variables if v.role == "group"]
            if len(outcomes) != 1 or len(groups) != 1:
                raise PlanningError("scenario_catalog", "La comparación requiere una medida y una agrupación.")
            count_groups = column_for(groups[0])["unique"]
            if any(
                (CATALOG[code].groups == "2" and count_groups != 2)
                or (CATALOG[code].groups == "3–20" and not 3 <= count_groups <= 20)
                for code in methods
            ):
                raise PlanningError("scenario_catalog", "El método no admite todos los grupos observados.")
        for variable in step.variables:
            column = column_for(variable)
            if column["possible_identifier"] and variable.role not in {"pair_id", "description"}:
                raise PlanningError("scenario_identifier", "Un identificador no es una medida.")


def validate_scenario_prose(value, context):
    # Es una detección conservadora; la interpretación semántica exige revisión humana.
    for text in prose(value):
        validate_independence(text, context, require_pending=False)
        validate_numeric_claims(text, context)
        if re.search(
            r"(?i)\b(media|promedio|mediana|varianza|desviaci[oó]n est[aá]ndar|frecuencia|porcentaje|rho|F|IC)"
            r"\s*(?:es|fue|de|=|:)\s*[-+]?\d|\b(?:r|p|t|g|d)\s*[=<>]\s*[-+]?\d|"
            r"\b(?:se obtuvo|se observ[oó]|resultado)\s*[:=]\s*[-+]?\d",
            text,
        ):
            raise PlanningError("scenario_numeric_claim", "No presentar resultados numéricos en propuestas.")


def validate_scenario(case, reply, *, record=None):
    # Sin recuperación parcial, sin corrección por otro proveedor y sin omitir cobertura.
    validate_reply(reply, case.files, PROJECT, case.context, validate_plans=True, check_recommendations=True)
    if record is not None:
        record["statia_native_valid"] = True
    count = len(reply.proposals)
    if case.identifier == "M":
        if not 2 <= count <= 4:
            raise PlanningError("scenario_count", "M requiere entre dos y cuatro propuestas.")
        covered = {p.procedure for p in reply.proposals}
        covered.update(c.procedure for p in reply.proposals for c in p.components)
        if not {"descriptive", "correlation", "group_comparison", "integral"} <= covered:
            raise PlanningError("scenario_coverage", "Faltan familias solicitadas en M.")
    elif count != 1 or reply.proposals[0].procedure != "integral":
        raise PlanningError("scenario_count", "I requiere una única propuesta integral.")
    if case.identifier == "I" and len({code for c in reply.proposals[0].components for code in named_methods(c)}) < 2:
        raise PlanningError("scenario_catalog", "I requiere al menos dos métodos estadísticos distintos.")
    if not reply.confirmation_required or reply.goal_change or reply.suggested_stage != "proposal":
        raise PlanningError("scenario_state", "La propuesta debe esperar confirmación sin cambiar finalidad.")
    if record is not None:
        record["request_valid"] = True
    for plan in reply.proposals:
        validate_plan_scenario(case, plan)
    validate_scenario_prose(reply.model_dump(), case.context)
    return reply


def payload(case, model):
    return {
        "model": model,
        "instructions": case.system,
        "input": json.dumps(case.context, ensure_ascii=False),
        "reasoning": {"effort": "medium"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": f"statia_{case.identifier.lower()}",
                "strict": True,
                "schema": case.schema,
            }
        },
        "max_output_tokens": LIMITS[case.identifier],
        "store": False,
    }


def token_count(value):
    return value if type(value) is int and value >= 0 else None


def record_usage(data, record, args):
    usage = data.get("usage") or {}
    incoming = token_count(usage.get("input_tokens"))
    outgoing = token_count(usage.get("output_tokens"))
    cached = token_count((usage.get("input_tokens_details") or {}).get("cached_tokens"))
    reasoning = token_count((usage.get("output_tokens_details") or {}).get("reasoning_tokens"))
    record["tokens"] = {
        "input": incoming,
        "output": outgoing,
        "cached_input": cached,
        "reasoning": reasoning,
        "visible_output": outgoing - reasoning
        if outgoing is not None and reasoning is not None and reasoning <= outgoing
        else None,
    }
    if incoming is None or outgoing is None:
        return
    # Razonamiento ya está incluido en output_tokens: nunca se suma otra vez.
    discounted = args.cached_input_usd_per_m is not None and cached is not None and cached <= incoming
    cached_billable = cached if discounted else 0
    amount = (
        (incoming - cached_billable) * args.input_usd_per_m
        + outgoing * args.output_usd_per_m
        + cached_billable * (args.cached_input_usd_per_m or 0)
    ) / 1_000_000
    record.update(
        estimated_cost_usd=round(amount, 8),
        cost_basis="configured_rates" if discounted else "configured_rates_no_cache_discount",
    )


def parse_response(case, data, record):
    status = data.get("status")
    record["provider_status"] = (
        status if status in {"completed", "incomplete", "failed", "queued", "in_progress", "cancelled"} else "unknown"
    )
    if status != "completed" or data.get("error") or data.get("incomplete_details"):
        reason = (data.get("incomplete_details") or {}).get("reason")
        record["incomplete_reason"] = reason if reason in {"max_output_tokens", "content_filter"} else None
        record.update(result="failed", category="response_not_completed")
        return
    parts = []
    for block in data.get("output", []):
        if block.get("type") == "reasoning":
            continue
        if block.get("type") != "message" or block.get("status") != "completed" or block.get("role") != "assistant":
            record.update(result="failed", category="unexpected_output")
            return
        for part in block.get("content", []):
            if part.get("type") == "refusal":
                record.update(result="failed", category="refusal")
                return
            if part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                record.update(result="failed", category="unexpected_output")
                return
            parts.append(part["text"])
    output = "".join(parts)
    try:
        json.loads(output)
    except ValueError:
        record.update(result="failed", category="invalid_json", json_integrity_valid=False)
        return
    record["json_integrity_valid"] = True
    try:
        reply = AssistantReply.model_validate_json(output)
    except ValidationError:
        record.update(result="failed", category="invalid_contract", contract_valid=False)
        return
    record.update(
        contract_valid=True,
        proposal_count=len(reply.proposals),
        component_count=sum(len(p.components) for p in reply.proposals),
    )
    try:
        validate_scenario(case, reply, record=record)
    except PlanningError as exc:
        if record.get("statia_native_valid") is not True:
            record["statia_native_valid"] = False
        record.update(result="failed", category=exc.category, scenario_valid=False)
        return
    except ValueError:
        record.update(result="failed", category="planning_validation", scenario_valid=False)
        return
    record.update(result="success", scenario_valid=True, manual_review_required=True)


class EvidenceError(ValueError):
    pass


def protect_evidence_directory(directory):
    """Proteger el directorio nuevo antes de escribir contenido del proveedor."""
    if os.name == "nt":
        # Restablecer primero la DACL del directorio NUEVO y vacío: quitar solo
        # herencia no elimina otras entradas explícitas creadas por Windows.
        identity = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        match = re.search(r"S-\d+(?:-\d+)+", identity)
        if not match:
            raise EvidenceError("evidence_identity")
        subprocess.run(["icacls", str(directory), "/reset"], capture_output=True, check=True)
        subprocess.run(
            [
                "icacls",
                str(directory),
                "/inheritance:r",
                "/grant:r",
                f"*{match.group()}:(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F",
            ],
            capture_output=True,
            check=True,
        )
        script = """
$ErrorActionPreference = 'Stop'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$system = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$actual = Get-Acl -LiteralPath $env:STATIA_EVIDENCE_DIRECTORY
$rules = @($actual.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
if (-not $actual.AreAccessRulesProtected -or $rules.Count -ne 2 -or
    @($rules | Where-Object { $_.IdentityReference.Value -notin @($sid.Value, $system.Value) }).Count -ne 0) {
    throw 'evidence_acl'
}
"""
        subprocess.run(
            [shutil.which("pwsh") or "powershell", "-NoProfile", "-Command", script],
            env={**os.environ, "STATIA_EVIDENCE_DIRECTORY": str(directory)},
            capture_output=True,
            check=True,
        )
    else:
        directory.chmod(0o700)


class EvidenceStore:
    def __init__(self, identifier, api_key):
        if os.name == "nt":
            local = os.environ.get("LOCALAPPDATA")
            if not local:
                raise EvidenceError("evidence_location")
            base = Path(local) / "Statia" / "terra-evidence"
        else:
            base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "statia/terra-evidence"
        base = base.resolve()
        # Fuera del checkout: no se puede añadir a este repositorio, ni por accidente.
        if base.is_relative_to(ROOT.parent.resolve()):
            raise EvidenceError("evidence_inside_repository")
        name = identifier + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12]
        self.directory = base / name
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        protect_evidence_directory(self.directory)
        self.api_key = api_key

    def write(self, name, text):
        # Fallar sin guardar ni alterar la respuesta si aparecen posibles secretos
        # o direcciones personales. Los datos enviados son exclusivamente sintéticos.
        if (self.api_key and self.api_key in text) or re.search(
            r"sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]{20,}\."
            r"|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
            text,
        ):
            raise EvidenceError("evidence_sensitive_content")
        target = self.directory / name
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())


def execute_case(case, args, api_key, record, evidence=None):
    started = time.perf_counter()
    try:
        # Sin /models, SDK, redirects, herramientas ni reintentos de transporte.
        with httpx.Client(
            timeout=httpx.Timeout(110.0, connect=10.0), follow_redirects=False, transport=httpx.HTTPTransport(retries=0)
        ) as client:
            if evidence:
                evidence.write("attempt.json", json.dumps({"case": case.identifier, "max_requests": 1}))
            record["requests_attempted"] = 1
            response = client.post(URL, headers={"Authorization": f"Bearer {api_key}"}, json=payload(case, args.model))
        record["provider_http_status"] = response.status_code
        if response.status_code != 200:
            record.update(result="failed", category="provider_http_error")
            return
        data = response.json()
        record_usage(data, record, args)
        if evidence:
            output = "".join(
                part["text"]
                for block in data.get("output", [])
                if block.get("type") == "message"
                for part in block.get("content", [])
                if part.get("type") == "output_text"
            )
            if output:
                evidence.write("assistant_reply.json", output)
                record.update(
                    evidence_response_saved=True, assistant_reply_sha256=hashlib.sha256(output.encode()).hexdigest()
                )
        parse_response(case, data, record)
    except EvidenceError:
        record.update(result="failed", category="evidence_sensitive_or_unwritable")
    except httpx.TimeoutException:
        record.update(result="failed", category="timeout_remote_usage_unknown")
    except httpx.HTTPError:
        record.update(result="failed", category="connectivity_remote_usage_unknown")
    except (ValueError, TypeError, AttributeError):
        record.update(result="failed", category="invalid_provider_response")
    except Exception:
        # No imprimir excepciones: podrían contener payload, URL o credenciales.
        record.update(result="failed", category="diagnostic_internal")
    finally:
        record["duration_seconds"] = round(time.perf_counter() - started, 3)
        if evidence:
            try:
                evidence.write("metrics_and_validations.json", json.dumps(record, ensure_ascii=False, indent=2))
            except (OSError, EvidenceError):
                record.update(result="failed", category="evidence_metrics_write_failed")


def rate(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("La tarifa debe ser finita y no negativa.")
    return number


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("M", "I"), help="Un solo escenario; obligatorio con --live.")
    parser.add_argument("--live", action="store_true", help="Permite una única solicitud real, sin reintentos.")
    parser.add_argument("--model", default="gpt-6.1-terra")
    parser.add_argument("--input-usd-per-m", type=rate)
    parser.add_argument("--output-usd-per-m", type=rate)
    parser.add_argument("--cached-input-usd-per-m", type=rate)
    parser.add_argument("--pricing-source", help="Referencia y fecha de las tarifas configuradas/verificadas.")
    args = parser.parse_args(argv)
    if args.live and (
        not args.case
        or args.input_usd_per_m is None
        or args.output_usd_per_m is None
        or not (args.pricing_source or "").strip()
    ):
        parser.error("--live exige --case individual, ambas tarifas y --pricing-source; sin solicitudes.")
    return args


def main(argv=None):
    args = parse_args(argv)
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        cases = [build_case(key) for key in ([args.case] if args.case else ["M", "I"])]
        api_key = ""
        if args.live:
            # Solo leer credenciales tras la selección explícita. La terminal prevalece.
            api_key = os.environ.get("OPENAI_API_KEY") or dotenv_values(ROOT / ".env").get("OPENAI_API_KEY") or ""
            if not api_key.strip():
                print(json.dumps({"result": "failed", "category": "missing_api_key", "requests_attempted": 0}))
                return 2
        evidence = None
        if args.live:
            try:
                evidence = EvidenceStore(args.case, api_key)
                evidence.write(
                    "criteria.json",
                    json.dumps(
                        {
                            "case": args.case,
                            "model": args.model,
                            "reasoning": "medium",
                            "max_requests": 1,
                            "max_output_tokens": LIMITS[args.case],
                            "native_validation_required": True,
                            "scenario_validation_required": True,
                            "reject_incomplete_or_invalid": True,
                            "expected_proposal_count": 1 if args.case == "I" else "2-4",
                            "integral_required": True,
                            "minimum_distinct_component_procedures": 2,
                            "catalog_references_dependencies_required": True,
                            "pending_inferential_independence_required": True,
                            "invented_numeric_results_forbidden": True,
                            "response_policy": "Texto original sin reconstruir campos; validaciones separadas.",
                            "payload_sha256": digest(payload(cases[0], args.model)),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
            except Exception:
                print(json.dumps({"result": "failed", "category": "evidence_preparation", "requests_attempted": 0}))
                return 2
        failed = False
        for case in cases:
            record = {
                "case": case.identifier,
                "model": args.model,
                "reasoning_effort": "medium",
                "max_output_tokens": LIMITS[case.identifier],
                "result": "dry_run",
                "category": None,
                "context_valid": True,
                "schema_valid_locally": True,
                "requests_attempted": 0,
                "provider_http_status": None,
                "provider_status": None,
                "tokens": None,
                "estimated_cost_usd": None,
                "pricing": {
                    "input_usd_per_m": args.input_usd_per_m,
                    "output_usd_per_m": args.output_usd_per_m,
                    "cached_input_usd_per_m": args.cached_input_usd_per_m,
                    "source_sha256": digest(args.pricing_source) if args.pricing_source else None,
                },
                "cost_basis": None,
                "duration_seconds": 0,
                "contract_valid": None,
                "json_integrity_valid": None,
                "statia_native_valid": None,
                "request_valid": None,
                "scenario_valid": None,
                "proposal_count": None,
                "component_count": None,
                "evidence_dir": str(evidence.directory) if evidence else None,
                "evidence_response_saved": False,
                "manual_review_required": True,
                "context_sha256": digest(case.context),
                "schema_sha256": digest(case.schema),
                "system_sha256": digest(case.system),
                "payload_sha256": digest(payload(case, args.model)),
            }
            if args.live:
                execute_case(case, args, api_key, record, evidence)
            print(json.dumps(record, ensure_ascii=False), flush=True)
            failed |= record["result"] == "failed"
        return int(failed)
    except Exception:
        print(json.dumps({"result": "failed", "category": "local_preparation", "requests_attempted": 0}))
        return 2
    finally:
        logging.disable(previous_logging)


if __name__ == "__main__":
    raise SystemExit(main())
