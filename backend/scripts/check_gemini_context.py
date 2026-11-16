"""Prueba optativa con Gemini real y contexto sintético, sin Auth/REST/Storage remotos.

Desde backend: python scripts/check_gemini_context.py. Usa la clave local .env;
no imprime prompts, respuestas, claves ni información de participantes.
"""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.models.chat import Turn  # noqa: E402
from app.models.research_context import ResearchContext  # noqa: E402
from app.services.gemini import GeminiProvider, build_context  # noqa: E402


async def main():
    settings = Settings()
    if not settings.gemini_api_key.get_secret_value():
        raise SystemExit("Gemini no está configurado; no se ejecutó ninguna simulación.")
    provider = GeminiProvider(settings)
    for revision, design in enumerate(("exploratorio", "longitudinal"), 1):
        question = "Describe brevemente el diseño vigente de mi tesis con su nombre exacto. No propongas análisis ni inventes hipótesis o datos. Indica dónde debo revisar y confirmar cualquier actualización metodológica."
        turn = Turn(request_id=uuid4(), content=question)
        research = {
            "document": ResearchContext(
                research_title="Estudio sintético de demostración", methodological_design=design
            ).model_dump(mode="json"),
            "revision": revision,
            "updated_at": "2026-11-16T12:00:00Z",
        }
        context = build_context(
            {"project_type": "thesis"},
            {"current_stage": "clarification", "stage_data": {}},
            [{"role": "user", "content": question}],
            [],
            turn,
            settings,
            research_context=research,
        )
        try:
            reply = await provider.generate(context)
        except HTTPException as exc:
            print(
                json.dumps(
                    {
                        "provider": "real",
                        "revision": revision,
                        "status": exc.status_code,
                        "diagnostic": (exc.headers or {}).get("X-Statia-Error"),
                    }
                )
            )
            raise SystemExit("La consulta real falló; revisar configuración/cuota del proveedor.") from None
        correct = design in reply.response.lower() and not reply.proposals and not reply.goal_change
        print(
            json.dumps(
                {
                    "provider": "real",
                    "revision": revision,
                    "design_matches": correct,
                    "response_contract": "AssistantReply",
                    "remote_persistence": False,
                }
            )
        )
        if not correct:
            raise SystemExit("La respuesta real no cumplió el escenario; no se modifica información guardada.")


if __name__ == "__main__":
    asyncio.run(main())
