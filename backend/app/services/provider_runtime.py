"""Presupuestos locales y trazas por turno; nunca guardar prompts ni respuestas."""

import logging
import math
import re
import time
from collections import deque
from contextvars import ContextVar
from typing import Protocol

from fastapi import HTTPException

from app.models.chat import AssistantReply


class Provider(Protocol):
    async def generate(self, context: dict, correction: str | None = None) -> AssistantReply: ...


current_trace: ContextVar[dict | None] = ContextVar("provider_trace", default=None)


class RequestBudget:
    """Una instancia por proveedor/proceso. Reservar antes de cada solicitud, sin esperas."""

    def __init__(self, settings):
        self.settings = settings
        self.requests = deque()

    def reserve(self):
        now = time.monotonic()
        while self.requests and self.requests[0] <= now - 60:
            self.requests.popleft()
        trace = current_trace.get()
        if trace is not None and trace["requests"] >= self.settings.ai_max_requests_per_turn:
            raise HTTPException(
                429,
                "Se alcanzó el máximo local de solicitudes de este turno. Revisa la solicitud antes de reintentar.",
                headers={"X-Statia-Error": "provider_request_limit"},
            )
        if len(self.requests) >= self.settings.ai_requests_per_minute:
            retry_after = max(1, math.ceil(self.requests[0] + 60 - now))
            raise HTTPException(
                429,
                f"Se alcanzó el límite local de solicitudes del proveedor. Puedes reintentar en {retry_after} segundos.",
                headers={"X-Statia-Error": "provider_request_limit", "Retry-After": str(retry_after)},
            )
        self.requests.append(now)
        if trace is not None:
            trace["requests"] += 1


def safe_id(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) else None


def token_count(value):
    return value if type(value) is int and 0 <= value <= 10**9 else None


def record_generation(provider, model, *, category, usage=None, request_id=None, response_id=None, response_model=None):
    record = {
        "category": category,
        "request_id": safe_id(request_id),
        "response_id": safe_id(response_id),
        "response_model": response_model
        if isinstance(response_model, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", response_model)
        else None,
        "usage": {key: token_count(value) for key, value in (usage or {}).items()},
    }
    trace = current_trace.get()
    if trace is not None:
        trace["generations"].append(record)
    logging.getLogger(__name__).info("Provider generation provider=%s model=%s metrics=%s", provider, model, record)


class ProviderSession:
    """Estado exclusivo del turno: ninguna métrica mutable en clientes compartidos."""

    def __init__(self, provider: Provider, provider_id, model):
        self.provider = provider
        self.calls = 0
        self.trace = {"provider": provider_id, "model": model, "requests": 0, "generations": []}

    async def generate(self, context, correction=None):
        self.calls += 1
        token = current_trace.set(self.trace)
        try:
            return await self.provider.generate(context, correction)
        finally:
            current_trace.reset(token)
