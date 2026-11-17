import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.analysis import router as analysis_router
from app.api.chat import router as chat_router
from app.api.health import router
from app.api.research_context import router as context_router
from app.core.config import Settings
from app.services.gemini import GeminiProvider
from app.services.openai_provider import OpenAIProvider


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Statia Platform API", version="0.3.0")
    app.state.settings = settings
    app.state.provider = GeminiProvider(settings)
    app.state.openai_provider = OpenAIProvider(settings)
    app.state.analysis_lock = asyncio.Semaphore(1)
    app.state.profile_lock = app.state.analysis_lock
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=[
            "Content-Disposition",
            "X-Statia-Error",
            "X-Gemini-Status",
            "X-OpenAI-Status",
            "X-Statia-Validation",
        ],
    )
    app.include_router(router)
    app.include_router(chat_router)
    app.include_router(analysis_router)
    app.include_router(context_router)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).exception("Error inesperado en %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Ocurrió un error interno."})

    return app


app = create_app()
