import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api.chat import conversation_for, project_for
from app.core.auth import CurrentUser
from app.models.analysis import ExecuteRequest, ProcedureInfo, RunView
from app.services.analysis import BUCKET, execute, public_run
from app.services.profiling import safe_name
from app.services.statistics.catalog import CATALOG

router = APIRouter(prefix="/projects/{project_id}", tags=["Resultados"])


@router.get("/analysis-procedures", response_model=list[ProcedureInfo])
async def procedures(project_id: UUID, user: CurrentUser):
    await project_for(user, project_id)
    return list(CATALOG.values())


@router.post("/conversations/{conversation_id}/proposals/{proposal_id}/runs", response_model=RunView)
async def execute_proposal(
    project_id: UUID,
    conversation_id: UUID,
    proposal_id: UUID,
    body: ExecuteRequest,
    user: CurrentUser,
    request: Request,
):
    project = await project_for(user, project_id)
    conversation = await conversation_for(user, project_id, conversation_id)
    proposal = await user.store.one(
        "analysis_proposals", {"id": str(proposal_id), "conversation_id": str(conversation_id)}
    )
    if request.app.state.analysis_lock.locked():
        raise HTTPException(409, "El motor está ocupado. Espera un momento y reintenta la misma solicitud.")
    async with request.app.state.analysis_lock:
        return await execute(user.store, user, project, conversation, proposal, body, request.app.state.settings)


@router.get("/analysis-runs", response_model=list[RunView])
async def list_runs(
    project_id: UUID,
    user: CurrentUser,
    conversation_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    await project_for(user, project_id)
    filters = {"project_id": str(project_id)}
    if conversation_id:
        await conversation_for(user, project_id, conversation_id)
        filters["conversation_id"] = str(conversation_id)
    rows = await user.store.rows(
        "analysis_runs",
        filters,
        order="created_at.desc,id.desc",
        limit=limit,
        offset=offset,
        select="id,project_id,conversation_id,proposal_id,request_id,title,status,created_at,started_at,finished_at,error,artifact_count,lease_token,specification",
    )
    return [await public_run(user.store, row) for row in rows]


@router.get("/analysis-runs/{run_id}", response_model=RunView)
async def get_run(project_id: UUID, run_id: UUID, user: CurrentUser):
    await project_for(user, project_id)
    run = await user.store.one("analysis_runs", {"id": str(run_id), "project_id": str(project_id)})
    return await public_run(user.store, run, detail=True)


async def artifact_content(user, project_id, run_id, filters):
    await project_for(user, project_id)
    run = await user.store.one("analysis_runs", {"id": str(run_id), "project_id": str(project_id)})
    if run["status"] == "running" or not run.get("result"):
        raise HTTPException(409, "Los recursos de esta ejecución todavía no están disponibles.")
    artifact = await user.store.one(
        "analysis_artifacts", {"run_id": str(run_id), "project_id": str(project_id), **filters}
    )
    data = await user.store.download(artifact["storage_path"], bucket=BUCKET, max_bytes=24 * 1024 * 1024)
    if len(data) != artifact["size_bytes"] or hashlib.sha256(data).hexdigest() != artifact["sha256"]:
        raise HTTPException(
            409, "El recurso almacenado no coincide con su manifiesto; no se descargó contenido inconsistente."
        )
    name = safe_name(artifact["name"])
    return Response(
        data,
        media_type=artifact["mime_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/analysis-runs/{run_id}/artifacts/{artifact_id}")
async def download_artifact(project_id: UUID, run_id: UUID, artifact_id: UUID, user: CurrentUser):
    return await artifact_content(user, project_id, run_id, {"id": str(artifact_id)})


@router.get("/analysis-runs/{run_id}/download")
async def download_zip(project_id: UUID, run_id: UUID, user: CurrentUser):
    return await artifact_content(user, project_id, run_id, {"name": "resultados_analisis.zip"})
