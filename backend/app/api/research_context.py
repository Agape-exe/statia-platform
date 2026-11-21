"""Contexto exclusivo de tesis; no duplica el CRUD de proyectos."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.core.auth import CurrentUser
from app.models.research_context import ContextSave
from app.services.research_context import current_context

router = APIRouter(prefix="/projects/{project_id}/research-context", tags=["Contexto de tesis"])


async def thesis_project(user, project_id):
    project = await user.store.one("projects", {"id": str(project_id), "user_id": user.user_id})
    if project["project_type"] != "thesis":
        raise HTTPException(404, "Contexto solo está disponible en proyectos de tesis.")
    return project


@router.get("")
async def get_context(project_id: UUID, user: CurrentUser):
    project = await thesis_project(user, project_id)
    return {"context": await current_context(user.store, project)}


@router.put("")
async def save_context(project_id: UUID, body: ContextSave, user: CurrentUser):
    project = await thesis_project(user, project_id)
    current = await current_context(user.store, project)
    if (
        current
        and current["revision"] == body.expected_revision
        and current["document"] == body.document.model_dump(mode="json")
    ):
        return {"context": current}
    try:
        row = await user.store.rpc(
            "save_research_context",
            {
                "p_project": str(project_id),
                "p_document": body.document.model_dump(mode="json"),
                "p_expected_revision": body.expected_revision,
            },
        )
    except HTTPException as exc:
        if exc.status_code == 409:
            raise HTTPException(
                409,
                "La versión guardada del Contexto cambió. Revisa esa versión antes de volver a guardar; tu borrador se conserva.",
            ) from None
        raise
    return {"context": {key: row[key] for key in ("document", "revision", "updated_at")}}
