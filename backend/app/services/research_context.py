"""Lectura con JWT/RLS y validación del documento antes de compartirlo con el proveedor."""

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.research_context import ResearchContext


async def current_context(store, project):
    if project["project_type"] != "thesis":
        return None
    rows = await store.rows("research_contexts", {"project_id": project["id"]}, limit=1)
    if not rows:
        return None
    row = rows[0]
    try:
        document = ResearchContext.model_validate(row["document"]).model_dump(mode="json")
        revision = row["revision"]
        if type(revision) is not int or revision < 1:
            raise ValueError("revision")
    except (ValidationError, ValueError, KeyError):
        raise HTTPException(
            422, "El contexto guardado no cumple el contrato. Revísalo en el módulo Contexto."
        ) from None
    return {"document": document, "revision": revision, "updated_at": row.get("updated_at")}
