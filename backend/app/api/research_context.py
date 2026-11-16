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
    await thesis_project(user, project_id)
    row = await user.store.rpc(
        "save_research_context",
        {
            "p_project": str(project_id),
            "p_document": body.document.model_dump(mode="json"),
            "p_expected_revision": body.expected_revision,
        },
    )
    return {"context": {key: row[key] for key in ("document", "revision", "updated_at")}}
