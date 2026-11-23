from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.services.requested_scope import SCOPE_RECOGNIZER_VERSION

router = APIRouter()


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "statia-platform-api"


@router.get("/health", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    response.headers["X-Statia-Planning-Version"] = str(SCOPE_RECOGNIZER_VERSION)
    return HealthResponse()
