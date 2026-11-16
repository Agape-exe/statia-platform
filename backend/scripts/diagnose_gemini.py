"""Aislar HTTP/contrato con datos sintéticos. Seco por defecto; --live hace llamadas reales.

Desde backend: .venv/Scripts/python scripts/diagnose_gemini.py --cases A B C D E F
Añadir --live explícitamente. Máximo 12 solicitudes; sin reintentos ni persistencia.
Solo stdout JSONL con métricas permitidas. No imprimir excepciones, prompts o respuestas.
"""

import argparse
import ast
import asyncio
import importlib.metadata
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from google import genai  # noqa: E402
from google.genai import errors, types  # noqa: E402
from pydantic import BaseModel, ConfigDict, ValidationError  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.models.chat import AssistantReply, Turn  # noqa: E402
from app.services.gemini import SYSTEM, build_context, validate_reply  # noqa: E402
from app.services.gemini_errors import api_diagnostic  # noqa: E402
from app.services.gemini_schema import reply_schema  # noqa: E402
from app.services.planning_errors import PlanningError  # noqa: E402
from app.services.profiling import inspect_file  # noqa: E402

SESSION3 = "783ee8095849979baaf8b105151bf75d2092451f"
QUESTIONS = {
    "B": "No tengo dataset. Explica qué información necesitas para empezar. No generes propuestas.",
    "C": "Describe las variables disponibles sin cálculos nuevos. Devuelve proposals=[]; no propongas análisis.",
    "D": "Genera una única propuesta descriptiva de `medida_a`, `medida_b` y `grupo`, sin inferencia ni cálculos.",
    "F": (
        "No conozco estos datos. Recomienda varias alternativas descriptivas, comparativas, correlacionales "
        "e integrales viables para `medida_a`, `medida_b` y `grupo`. No calcules resultados. "
        "La independencia no está confirmada: déjala pendiente de verificar con el diseño."
    ),
}
QUESTIONS["E"] = QUESTIONS["D"]
PROJECT = {"project_type": "general"}


class MinimalReply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    estado: str
    metodo: str


@dataclass
class Case:
    identifier: str
    system: str
    context: dict
    schema: dict | None
    files: list


def synthetic_files(settings):
    # Sin participantes ni archivos remotos. Tres grupos para evitar una comparación
    # de dos grupos elegida artificialmente al construir el diagnóstico.
    rows = ["medida_a,medida_b,grupo"] + [f"{10 + i},{18 + 2 * i},{'ABC'[i % 3]}" for i in range(18)]
    return [
        {
            "id": "00000000-0000-0000-0000-000000000002",
            "original_name": "sintetico.csv",
            "file_role": "dataset",
            "metadata": inspect_file("sintetico.csv", "\n".join(rows).encode(), "dataset", settings),
        }
    ]


def system_for(version):
    if version == "current":
        return SYSTEM
    # Solo extrae el literal SYSTEM de un commit fijo. Nunca ejecuta código histórico.
    source = subprocess.check_output(
        ["git", "show", f"{SESSION3}:backend/app/services/gemini.py"],
        cwd=Path(__file__).resolve().parents[2],
        encoding="utf-8",
        stderr=subprocess.DEVNULL,
    )
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SYSTEM" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("system_missing")


def build_case(identifier, settings, system):
    if identifier == "A":
        return Case(
            identifier,
            "",
            {"solicitud": "Responde JSON con estado=ok y metodo=ninguno. No hagas cálculos."},
            {
                "type": "object",
                "properties": {"estado": {"type": "string"}, "metodo": {"type": "string"}},
                "required": ["estado", "metodo"],
            },
            [],
        )
    question = QUESTIONS[identifier]
    files = [] if identifier == "B" else synthetic_files(settings)
    context = build_context(
        PROJECT,
        {"current_stage": "goal", "stage_data": {}},
        [{"role": "user", "content": question}],
        files,
        Turn(request_id="00000000-0000-0000-0000-000000000001", content=question),
        settings,
    )
    # Los escenarios B–E piden explícitamente cero/una propuesta. La detección
    # lexical no interpreta negaciones; evitar convertir «no propongas» en cuota.
    context["recommendations_requested"] = identifier == "F"
    return Case(identifier, system, context, None if identifier == "E" else reply_schema(), files)


def config_for(case):
    return types.GenerateContentConfig(
        system_instruction=case.system or None,
        response_mime_type="application/json",
        response_schema=case.schema,
        max_output_tokens=7000,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def metadata(case, settings, system_version):
    prompt = json.dumps(case.context, ensure_ascii=False)
    schema_chars = len(json.dumps(case.schema, ensure_ascii=False)) if case.schema else 0
    return {
        "case": case.identifier,
        "model": settings.gemini_model,
        "sdk_version": importlib.metadata.version("google-genai"),
        "system_chars": len(case.system),
        "context_chars": len(prompt),
        "schema_chars": schema_chars,
        "parameters": {
            "system_version": system_version,
            "response_mime_type": "application/json",
            "response_schema": case.schema is not None,
            "max_output_tokens": 7000,
            "timeout_seconds": settings.gemini_timeout_seconds,
            "sdk_attempts": 1,
            "statia_attempts": 1,
            "automatic_function_calling": False,
            # Aproximación orientativa; no es tokenización ni consumo medido.
            "estimated_input_tokens_chars_div4": round((len(case.system) + len(prompt) + schema_chars) / 4),
        },
        "duration_seconds": 0,
        "result": "dry_run",
        "category": None,
        "provider_http_status": None,
        "tokens": None,
        "contract_valid": None,
        "methodology_valid": None,
        "proposal_count": None,
    }


def validate_response(case, response, record):
    usage = response.usage_metadata
    if usage:
        record["tokens"] = {
            field: getattr(usage, field, None)
            for field in ("prompt_token_count", "candidates_token_count", "thoughts_token_count", "total_token_count")
        }
    try:
        model = MinimalReply if case.identifier == "A" else AssistantReply
        reply = model.model_validate_json(response.text or "")
    except ValidationError:
        record.update(result="failed", category="gemini_invalid_response", contract_valid=False)
        return
    record.update(contract_valid=True, proposal_count=0 if case.identifier == "A" else len(reply.proposals))
    if case.identifier != "A":
        try:
            validate_reply(reply, case.files, PROJECT, case.context)
        except PlanningError as exc:
            record.update(result="failed", category=f"planning_{exc.category}", methodology_valid=False)
            return
        except ValueError:
            record.update(result="failed", category="planning_validation", methodology_valid=False)
            return
        record["methodology_valid"] = True
        count = len(reply.proposals)
        expected = (
            (case.identifier in ("B", "C") and count == 0)
            or (case.identifier in ("D", "E") and count == 1 and reply.proposals[0].procedure == "descriptive")
            or (case.identifier == "F" and count >= 2)
        )
        if not expected:
            record.update(result="failed", category="scenario_proposal_count")
            return
    record["result"] = "success"


async def execute_case(case, settings, record):
    started = time.perf_counter()
    try:
        async with asyncio.timeout(settings.gemini_timeout_seconds):
            async with genai.Client(
                api_key=settings.gemini_api_key.get_secret_value(),
                http_options=types.HttpOptions(
                    timeout=settings.gemini_timeout_seconds * 1000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            ).aio as client:
                response = await client.models.generate_content(
                    model=settings.gemini_model,
                    contents=json.dumps(case.context, ensure_ascii=False),
                    config=config_for(case),
                )
        # Hubo respuesta válida HTTP aunque falle posteriormente el contrato local.
        record["provider_http_status"] = 200
        validate_response(case, response, record)
    except errors.APIError as exc:
        safe = api_diagnostic(exc)
        record.update(result="failed", category=safe.headers["X-Statia-Error"], provider_http_status=int(exc.code))
    except (TimeoutError, httpx.TimeoutException):
        record.update(result="failed", category="gemini_timeout")
    except httpx.HTTPError:
        record.update(result="failed", category="gemini_connectivity")
    except ValueError:
        record.update(result="failed", category="gemini_sdk_contract")
    except Exception:
        # No exponer tracebacks del SDK con payloads o URLs que contengan claves.
        record.update(result="failed", category="diagnostic_internal")
    finally:
        record["duration_seconds"] = round(time.perf_counter() - started, 3)
    return record


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", choices=list("ABCDEF"), default=list("ABCDEF"))
    parser.add_argument("--live", action="store_true", help="Autoriza solicitudes reales, sin reintentos.")
    parser.add_argument("--repeat", type=int, choices=(1, 2), default=1)
    parser.add_argument("--system-version", choices=("current", "session3"), default="current")
    args = parser.parse_args(argv)
    if len(args.cases) != len(set(args.cases)):
        parser.error("No repetir casos en --cases; usar --repeat (máximo 2).")
    return args


async def main(argv=None):
    args = parse_args(argv)
    # Silenciar también logs internos del SDK/httpx: solo salen nuestros registros permitidos.
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        return await run_cases(args)
    finally:
        logging.disable(previous_logging)


async def run_cases(args):
    try:
        settings = Settings()
        system = system_for(args.system_version)
        cases = [build_case(identifier, settings, system) for identifier in args.cases]
    except Exception:
        print("Configuración o referencia histórica inválida. No se enviaron solicitudes.", file=sys.stderr)
        return 2
    if args.live and not settings.gemini_api_key.get_secret_value():
        print("Gemini no está configurado. No se enviaron solicitudes ni se simularon éxitos.", file=sys.stderr)
        return 2
    failed = False
    for _ in range(args.repeat):
        for case in cases:
            record = metadata(case, settings, args.system_version)
            if args.live:
                record = await execute_case(case, settings, record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
            failed |= record["result"] == "failed"
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
