"""Responses API experimental, sin herramientas, fallback, redirecciones ni reintentos."""

import asyncio
import json

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.gemini import SYSTEM
from app.services.gemini_schema import reply_schema
from app.services.plan_capabilities import PRODUCT_INSTRUCTIONS
from app.services.provider_runtime import RequestBudget, record_generation

MODEL = "gpt-6.1-terra"
URL = "https://api.openai.com/v1/responses"


def reply_schema_openai(node):
    """Conversión nullable/objetos cerrados utilizada en las pruebas aisladas A/D/M/I."""
    if isinstance(node, list):
        return [reply_schema_openai(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {key: reply_schema_openai(value) for key, value in node.items() if key != "nullable"}
    if node.get("nullable") and isinstance(out.get("type"), str):
        out["type"] = [out["type"], "null"]
    if node.get("type") == "object":
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties", {}))
    return out


MESSAGES = {
    "disabled": "El acceso experimental a Terra está deshabilitado en el servidor.",
    "not_configured": "Falta configurar OPENAI_API_KEY exclusivamente en el backend.",
    "credentials": "OpenAI rechazó la credencial del backend.",
    "permissions": "OpenAI denegó el acceso al modelo o a esta operación.",
    "model": "El modelo Terra no está disponible para esta cuenta.",
    "schema": "OpenAI rechazó el esquema de respuesta estructurada.",
    "invalid_request": "OpenAI rechazó los parámetros de la solicitud.",
    "quota": "OpenAI informó un límite de cuota o solicitudes.",
    "unavailable": "OpenAI está temporalmente no disponible.",
    "timeout": "OpenAI tardó demasiado. Tu mensaje se conservó; el consumo remoto puede ser desconocido.",
    "connectivity": "No se pudo completar la conexión con OpenAI. El consumo remoto puede ser desconocido.",
    "incomplete": "OpenAI devolvió una generación incompleta. No se guardó una propuesta.",
    "refusal": "OpenAI rechazó generar esta respuesta. No se guardó una propuesta.",
    "invalid_response": "OpenAI devolvió una respuesta que no cumple el contrato de Statia.",
    "provider": "OpenAI no pudo completar la consulta.",
}


def diagnostic(category, status=502, upstream=None):
    headers = {"X-Statia-Error": "openai_" + category}
    if upstream is not None:
        headers["X-OpenAI-Status"] = str(upstream)
    return HTTPException(status, MESSAGES[category], headers=headers)


def http_diagnostic(response):
    status = response.status_code
    category, local = {
        401: ("credentials", 502),
        403: ("permissions", 502),
        404: ("model", 502),
        429: ("quota", 429),
        408: ("timeout", 504),
        504: ("timeout", 504),
        500: ("unavailable", 503),
        502: ("unavailable", 503),
        503: ("unavailable", 503),
    }.get(status, ("provider", 502))
    if status in (400, 422):
        category = "invalid_request"
        try:
            error = response.json().get("error", {})
            # Solo clasificar campos conocidos; nunca exponer el cuerpo ni su mensaje.
            if (
                error.get("param") in ("text.format", "text.format.schema")
                or error.get("code") == "invalid_json_schema"
            ):
                category = "schema"
            elif error.get("param") == "model":
                category = "model"
        except (ValueError, AttributeError):
            pass
    return diagnostic(category, local, status)


def parse_reply(data, interaction_mode=None, *, validate_plans_separately=False):
    if not isinstance(data, dict):
        raise diagnostic("invalid_response")
    if data.get("status") != "completed" or data.get("incomplete_details") or data.get("error"):
        raise diagnostic("incomplete")
    parts = []
    for block in data.get("output", []):
        if block.get("type") == "reasoning":
            continue
        if block.get("type") != "message" or block.get("status") != "completed" or block.get("role") != "assistant":
            raise diagnostic("invalid_response")
        for part in block.get("content", []):
            if part.get("type") == "refusal":
                raise diagnostic("refusal")
            if part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                raise diagnostic("invalid_response")
            parts.append(part["text"])
    from app.services.reply_contract import parse_assistant_reply

    return parse_assistant_reply("".join(parts), interaction_mode, validate_plans_separately=validate_plans_separately)


class OpenAIProvider:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.budget = RequestBudget(settings)
        self.transport = transport

    def check_available(self):
        if not self.settings.openai_terra_enabled:
            raise diagnostic("disabled", 503)
        if not self.settings.openai_api_key.get_secret_value():
            raise diagnostic("not_configured", 503)

    async def generate(self, context, correction=None):
        self.check_available()
        prompt = json.dumps(context, ensure_ascii=False)
        if correction:
            budget = max(0, self.settings.gemini_context_chars - len(prompt) - 80)
            prompt += "\nCorrige la respuesta anterior: " + correction[:budget]
        payload = {
            "model": MODEL,
            "instructions": SYSTEM + PRODUCT_INSTRUCTIONS,
            "input": prompt,
            "reasoning": {"effort": "medium"},
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "statia_reply",
                    "strict": True,
                    "schema": reply_schema_openai(reply_schema(structured=False)),
                }
            },
            "max_output_tokens": self.settings.openai_max_output_tokens,
        }
        self.budget.reserve()
        usage, request_id, response_id, response_model = {}, None, None, None
        category = "cancelled"
        try:
            async with asyncio.timeout(self.settings.openai_timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=self.settings.openai_timeout_seconds, follow_redirects=False, transport=self.transport
                ) as client:
                    response = await client.post(
                        URL,
                        headers={"Authorization": "Bearer " + self.settings.openai_api_key.get_secret_value()},
                        json=payload,
                    )
                request_id = response.headers.get("x-request-id")
                if response.status_code != 200:
                    raise http_diagnostic(response)
                data = response.json()
                if isinstance(data, dict):
                    response_id = data.get("id")
                    response_model = data.get("model")
                    raw = data.get("usage") or {}
                    usage = {
                        "input_tokens": raw.get("input_tokens"),
                        "output_tokens": raw.get("output_tokens"),
                        "cached_input_tokens": (raw.get("input_tokens_details") or {}).get("cached_tokens"),
                        "reasoning_tokens": (raw.get("output_tokens_details") or {}).get("reasoning_tokens"),
                    }
                reply = parse_reply(
                    data, context.get("interaction_mode"), validate_plans_separately="proposal_limit" in context
                )
            category = "completed"
            return reply
        except (TimeoutError, httpx.TimeoutException):
            category = "timeout"
            raise diagnostic(category, 504) from None
        except httpx.HTTPError:
            category = "connectivity"
            raise diagnostic(category) from None
        except (ValueError, ValidationError, TypeError, AttributeError):
            category = "invalid_response"
            raise diagnostic(category) from None
        except HTTPException as exc:
            category = exc.headers["X-Statia-Error"].removeprefix("openai_")
            raise
        finally:
            record_generation(
                "openai",
                MODEL,
                category=category,
                usage=usage,
                request_id=request_id,
                response_id=response_id,
                response_model=response_model,
            )
