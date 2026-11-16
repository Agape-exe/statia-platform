import asyncio
import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.analysis import AnalysisResult, RunView
from app.models.chat import Plan
from app.services.analysis_exports import build_exports
from app.services.analysis_worker import run_calculation
from app.services.execution_preparation import (
    LIMIT_NAMES,
    originals_for,
    preparation_context,
)
from app.services.statistics.catalog import CATALOG
from app.services.statistics.preparation import AnalysisError, validate_spec

BUCKET = "analysis-results"
logger = logging.getLogger(__name__)


async def public_run(store, run, *, detail=False):
    if run["status"] == "running" and datetime.fromisoformat(run["started_at"].replace("Z", "+00:00")) < datetime.now(
        timezone.utc
    ) - timedelta(seconds=180):
        await store.rpc(
            "fail_analysis_run",
            {
                "p_run": run["id"],
                "p_token": run["lease_token"],
                "p_error": "La ejecución se interrumpió o venció. Reintenta la misma solicitud.",
            },
        )
        run = await store.one("analysis_runs", {"id": run["id"], "project_id": run["project_id"]})
    values = {name: run[name] for name in RunView.model_fields if name in run and name != "result"}
    values["methods"] = [
        CATALOG[c["method"]].name
        for c in run.get("specification", {}).get("components", [])
        if c.get("method") in CATALOG
    ]
    if detail:
        values["result"] = run.get("result")
        values["artifacts"] = await store.rows(
            "analysis_artifacts",
            {"run_id": run["id"], "project_id": run["project_id"]},
            order="name.asc",
            select="id,run_id,project_id,name,mime_type,size_bytes,sha256",
        )
        values["artifacts"] = [
            {k: a[k] for k in ["id", "run_id", "project_id", "name", "mime_type", "size_bytes", "sha256"]}
            for a in values["artifacts"]
        ]
    return RunView.model_validate(values)


async def execute(store, identity, project, conversation, proposal, body, settings):
    try:
        plan = Plan.model_validate(proposal["analysis_plan"])
        if project.get("project_type") == "thesis" and not plan.methodology_confirmed:
            raise AnalysisError(
                "La metodología de tesis no está confirmada en el plan actual. Solicita una propuesta revisada."
            )
        validate_spec(plan, body.specification)
    except (ValidationError, AnalysisError) as exc:
        raise HTTPException(
            422,
            str(exc)
            if isinstance(exc, AnalysisError)
            else "El contrato del plan aceptado ya no es válido. Solicita una propuesta nueva.",
        ) from None
    if proposal["status"] != "accepted":
        raise HTTPException(409, "Solo se pueden ejecutar propuestas aceptadas.")
    preparation = conversation.get("stage_data", {}).get("execution_preparation") or {}
    if body.preparation_fingerprint:
        ready = preparation.get("result", {})
        expected = body.specification.model_dump(mode="json")
        expected["decisions_confirmed"] = False
        if (
            preparation.get("proposal_id") != proposal["id"]
            or ready.get("request_id") != str(body.request_id)
            or ready.get("status") != "READY"
            or ready.get("fingerprint") != body.preparation_fingerprint
            or ready.get("specification") != expected
        ):
            raise HTTPException(
                409, "La preparación cambió o todavía tiene preguntas pendientes. Vuelve a preparar el análisis."
            )
    state = await store.rpc(
        "begin_analysis_run",
        {
            "p_conversation": conversation["id"],
            "p_proposal": proposal["id"],
            "p_request": str(body.request_id),
            "p_specification": body.specification.model_dump(mode="json"),
            "p_plan": proposal["analysis_plan"],
        },
    )
    if state["status"] in ("busy", "mismatch"):
        raise HTTPException(
            409,
            "Hay una operación en curso en esta conversación."
            if state["status"] == "busy"
            else "Esta clave de solicitud corresponde a otras decisiones. Crea una ejecución nueva.",
        )
    run_id = state["run_id"]
    if state["status"] == "replayed":
        return await public_run(
            store, await store.one("analysis_runs", {"id": run_id, "project_id": project["id"]}), detail=True
        )
    uploaded = []
    try:
        async with asyncio.timeout(150):
            originals = await originals_for(store, project, conversation, plan, settings)
            job = {
                "run_id": run_id,
                "project_id": project["id"],
                "conversation_id": conversation["id"],
                "proposal_id": proposal["id"],
                "plan": proposal["analysis_plan"],
                "specification": body.specification.model_dump(mode="json"),
                "files": originals,
                "review_conditions": True,
                "limits": {name: getattr(settings, name) for name in LIMIT_NAMES},
            }
            if body.preparation_fingerprint:
                job["preparation_context"] = preparation_context(project, conversation, preparation.get("answers", {}))
                job["preparation_fingerprint"] = body.preparation_fingerprint
            output = await run_calculation(job)
            del job, originals
            result = AnalysisResult.model_validate(output["result"]).model_dump(mode="json")
            resources = await asyncio.to_thread(
                build_exports, result, {name: base64.b64decode(data) for name, data in output["charts"].items()}
            )
            if sum(len(data) for data, _ in resources.values()) > 24 * 1024 * 1024:
                raise HTTPException(413, "Los recursos exceden 24 MB por ejecución. Reduce los componentes del plan.")
            artifacts = []
            for name, (data, mime) in resources.items():
                path = f"{identity.user_id}/{project['id']}/{run_id}/{state['lease_token']}/{name}"
                await store.upload(path, data, mime, bucket=BUCKET)
                uploaded.append(path)
                artifacts.append(
                    {
                        "name": name,
                        "storage_path": path,
                        "mime_type": mime,
                        "size_bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
            await store.rpc(
                "finish_analysis_run",
                {"p_run": run_id, "p_token": state["lease_token"], "p_result": result, "p_artifacts": artifacts},
            )
    except BaseException as exc:
        try:
            current = await asyncio.shield(store.one("analysis_runs", {"id": run_id, "project_id": project["id"]}))
            if current["status"] in ("completed", "partial", "failed") and current.get("result") is not None:
                return await public_run(store, current, detail=True)
            error = (
                exc.detail
                if isinstance(exc, HTTPException)
                else "La ejecución no pudo finalizar. Reintenta la misma solicitud."
            )
            await asyncio.shield(
                store.rpc("fail_analysis_run", {"p_run": run_id, "p_token": state["lease_token"], "p_error": error})
            )
            for path in uploaded:
                await asyncio.shield(store.remove_object(path, bucket=BUCKET))
        except Exception:
            logger.warning("No se pudo reconciliar una ejecución; su concesión expira a los 180 segundos.")
        if isinstance(exc, TimeoutError):
            raise HTTPException(
                504, "La operación superó el tiempo total permitido. Consulta el estado antes de reintentar."
            ) from None
        if isinstance(exc, httpx.HTTPError):
            raise HTTPException(
                502, "Supabase no pudo completar la ejecución. Consulta el estado y reintenta con la misma solicitud."
            ) from None
        raise
    return await public_run(
        store, await store.one("analysis_runs", {"id": run_id, "project_id": project["id"]}), detail=True
    )
