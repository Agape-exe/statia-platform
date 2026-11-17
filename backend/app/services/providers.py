"""Selección cerrada de proveedores. Un fallo nunca cambia el destinatario."""

from fastapi import HTTPException

from app.services.gemini_errors import diagnostic
from app.services.openai_provider import MODEL
from app.services.provider_runtime import ProviderSession


def provider_model(provider_id, settings):
    if provider_id == "gemini":
        return settings.gemini_model
    if provider_id == "openai":
        return MODEL
    raise HTTPException(422, "Proveedor desconocido. Selecciona gemini u openai.")


def check_available(provider_id, state):
    provider_model(provider_id, state.settings)
    if provider_id == "openai":
        state.openai_provider.check_available()
    elif not state.settings.gemini_api_key.get_secret_value():
        raise diagnostic("not_configured", 503)


def session_for(provider_id, state):
    model = provider_model(provider_id, state.settings)
    provider = state.provider if provider_id == "gemini" else state.openai_provider
    return ProviderSession(provider, provider_id, model)


def catalog(state):
    settings = state.settings
    return {
        "default": "gemini",
        "providers": [
            {
                "id": "gemini",
                "name": "Gemini",
                "model": settings.gemini_model,
                "experimental": False,
                "enabled": True,
                "configured": bool(settings.gemini_api_key.get_secret_value()),
            },
            {
                "id": "openai",
                "name": "Terra (OpenAI)",
                "model": MODEL,
                "experimental": True,
                "enabled": settings.openai_terra_enabled,
                "configured": bool(settings.openai_api_key.get_secret_value()),
            },
        ],
    }
