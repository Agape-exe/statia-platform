"""Reproducción descriptiva: productos verificables en los cuatro puntos de control."""

import copy
from uuid import uuid4

import pytest
import test_chat_api
from test_analysis_api import analysis_client as analysis_client
from test_chat_api import attach_dataset, new, plan, reply, turn
from test_provider_selection import select, terra
from test_statistics import job_for

from app.core.config import Settings
from app.models.chat import AssistantReply, Plan
from app.services.gemini import validate_reply
from app.services.plan_capabilities import validate_products
from app.services.planning_errors import PlanningError
from app.services.profiling import inspect_file
from app.services.statistics.automatic import assess
from app.services.statistics.engine import calculate
from app.services.statistics.preparation import AnalysisError

api = test_chat_api.api


def descriptive_job(outputs, *, grouped=True):
    job = job_for(procedure="descriptive", methods=["descriptive"])
    measure, group = job_for()["plan"]["variables"][:2]
    measure = {**measure, "file_id": job["files"][0]["id"]}
    group = {**group, "file_id": job["files"][0]["id"]}
    job["plan"].update(
        variables=[measure, group] if grouped else [measure],
        objective="Describir `cantidad` y `estrato`" if grouped else "Describir `cantidad`",
        method="Descriptivos",
        expected_outputs=outputs,
    )
    job["specification"]["decisions"] = [
        {"variable": v, "statistical_type": "nominal" if v["role"] == "group" else "continuous"}
        for v in job["plan"]["variables"]
    ]
    job["specification"]["components"][0].update(method="descriptive", descriptive_intervals=False)
    return job


def complete_integral():
    job = descriptive_job(["Resúmenes globales", "Resúmenes por grupo", "Frecuencias de la variable de agrupación"])
    measure, group = job["plan"]["variables"]
    job["plan"].update(
        procedure="integral",
        components=[
            {"procedure": "descriptive", "method": "Descriptivos globales de `cantidad`", "variables": [measure]},
            {
                "procedure": "descriptive",
                "method": "Descriptivos de `cantidad` por `estrato`",
                "variables": [measure, group],
            },
            {
                "procedure": "descriptive",
                "method": "Frecuencias de `estrato`",
                "variables": [{**group, "role": "description"}],
            },
        ],
    )
    job["specification"]["components"] = [
        {"source_index": i, "method": "descriptive", "descriptive_intervals": False} for i in range(3)
    ]
    return job


def files_for(job):
    import base64

    file = job["files"][0]
    return [
        {
            **file,
            "file_role": "dataset",
            "metadata": inspect_file(
                "arbitrario.csv", base64.b64decode(file["data"]), "dataset", Settings(_env_file=None)
            ),
        }
    ]


@pytest.mark.parametrize("kind", ["global", "grouped", "frequencies", "integral"])
def test_supported_products_pass_validation_preparation_and_execution(kind):
    job = (
        complete_integral()
        if kind == "integral"
        else descriptive_job(
            ["Resúmenes por grupo"]
            if kind == "grouped"
            else ["Frecuencias categóricas"]
            if kind == "frequencies"
            else ["Resúmenes globales"],
            grouped=kind == "grouped",
        )
    )
    if kind == "frequencies":
        group = {**job["plan"]["variables"][0], "column": "estrato", "role": "description"}
        job["plan"]["variables"] = [group]
        job["plan"]["objective"] = "Describir `estrato`"
        job["specification"]["decisions"] = [{"variable": group, "statistical_type": "nominal"}]
    before = copy.deepcopy(job["plan"])
    validate_reply(
        AssistantReply(response="Propuesta", suggested_stage="proposal", proposals=[job["plan"]]),
        files_for(job),
        {"project_type": "general"},
    )
    result = assess(job)
    assert result["status"] == "READY", result
    output, _ = calculate(job)
    assert output["status"] == "completed"
    if kind == "integral":
        assert len(output["components"]) == 3
        assert len(output["components"][0]["tables"][0]["rows"]) == 1
        assert len(output["components"][1]["tables"][0]["rows"]) == 2
        frequency_table = next(t for t in output["components"][2]["tables"] if t["title"].startswith("Frecuencias"))
        assert {r["Categoría"] for r in frequency_table["rows"]} == {"A", "B"}
    assert job["plan"] == before


@pytest.mark.parametrize(
    "outputs",
    [
        ["Resúmenes globales", "Resúmenes por grupo", "Frecuencias de la variable de agrupación"],
        ["Resumen global, agrupado y frecuencias de grupo"],
        ["Resultados magníficos de todos los modos que convengan"],
    ],
)
def test_exact_audit_and_unknown_outputs_cannot_prepare_or_complete(outputs):
    job = descriptive_job(outputs)
    original = copy.deepcopy(job)
    with pytest.raises(PlanningError):
        validate_products(Plan.model_validate(job["plan"]), files_for(job))
    preparation = assess(job)
    assert preparation["status"] == "UNSUPPORTED" and preparation["specification"] is None
    assert preparation["blockers"] and "alcance" in " ".join(preparation["blockers"])
    with pytest.raises(AnalysisError):
        calculate(job)
    assert job == original


def test_missing_integral_product_and_grouping_column_are_rejected():
    job = complete_integral()
    job["plan"]["components"].pop()
    with pytest.raises(PlanningError, match="no está cubierto"):
        validate_products(Plan.model_validate(job["plan"]), files_for(job))
    assert assess(job)["status"] == "UNSUPPORTED"
    with pytest.raises(AnalysisError):
        calculate(job)


@pytest.mark.parametrize("provider_id", ["gemini", "openai"])
def test_generation_repairs_once_before_persistence_with_shared_validator(api, provider_id):
    client, store, gemini = api
    path = new(client, store)
    turn(client, path, action="instrument_no")
    fid = attach_dataset(client, path)
    invalid = plan(fid)
    invalid["variables"].append({"file_id": fid, "sheet": "tabla", "column": "grupo", "role": "group"})
    invalid["expected_outputs"] = [
        "Resúmenes globales",
        "Resúmenes por grupo",
        "Frecuencias de la variable de agrupación",
    ]
    corrected = copy.deepcopy(invalid)
    measure, group = invalid["variables"]
    corrected.update(
        procedure="integral",
        objective="Describir `nota` y `grupo`",
        method="Descriptivos globales y por `grupo` de `nota` y frecuencias de `grupo`",
        components=[
            {"procedure": "descriptive", "method": "Describir `nota`", "variables": [measure]},
            {"procedure": "descriptive", "method": "Describir `nota` por `grupo`", "variables": [measure, group]},
            {
                "procedure": "descriptive",
                "method": "Frecuencias de `grupo`",
                "variables": [{**group, "role": "description"}],
            },
        ],
    )
    if provider_id == "openai":
        calls = terra(client, [reply(proposals=[invalid]), reply(proposals=[corrected])])
        assert select(client, path, "openai").status_code == 200
    else:
        gemini.replies = [reply(proposals=[invalid]), reply(proposals=[corrected])]
        calls = gemini.contexts
    response = turn(client, path, content="Describe todas las notas globales y por grupo, y frecuencias del grupo")
    assert response.status_code == 200, response.text
    assert len(calls) == 2
    stored = client.get(path).json()["proposals"]
    assert len(stored) == 1 and stored[0]["analysis_plan"]["expected_outputs"] == invalid["expected_outputs"]


def test_acceptance_blocks_historical_bad_plan_and_preserves_prior_state(api):
    client, store, _ = api
    path = new(client, store)
    cid = path.rsplit("/", 1)[1]
    fid = attach_dataset(client, path)
    invalid = plan(fid)
    invalid["variables"].append({"file_id": fid, "sheet": "tabla", "column": "grupo", "role": "group"})
    invalid["expected_outputs"] = [
        "Resúmenes globales",
        "Resúmenes por grupo",
        "Frecuencias de la variable de agrupación",
    ]
    proposal = {
        "id": str(uuid4()),
        "conversation_id": cid,
        "status": "proposed",
        "analysis_plan": invalid,
        "created_at": 0,
    }
    store.data["analysis_proposals"].append(proposal)
    before = copy.deepcopy(store.data)
    response = client.patch(path + "/proposals/" + proposal["id"], json={"status": "accepted"})
    assert response.status_code == 422 and response.headers["X-Statia-Error"] == "output_capability"
    assert "componentes separados" in response.json()["detail"]
    assert store.data == before


def test_historical_incompatible_plan_blocked_in_http_preparation_and_execution(analysis_client):
    client, store, endpoint, body = analysis_client
    store.data["conversations"][0]["primary_goal"] = None
    proposal = store.data["analysis_proposals"][0]
    proposal["analysis_plan"].update(
        procedure="descriptive",
        method="Descriptivos",
        expected_outputs=["Resúmenes globales", "Resúmenes por grupo", "Frecuencias de la variable de agrupación"],
    )
    plan_before = copy.deepcopy(proposal)
    path = endpoint.rsplit("/proposals/", 1)[0]
    prepared = client.post(
        path + "/turns", json={"request_id": str(uuid4()), "action": "prepare_execution", "proposal_id": proposal["id"]}
    )
    assert prepared.status_code == 200, prepared.text
    state = client.get(path).json()["conversation"]["stage_data"]["execution_preparation"]["result"]
    assert state["status"] == "UNSUPPORTED" and state["specification"] is None
    execution = client.post(endpoint, json=body)
    assert execution.status_code == 422 and "no está cubierto" in execution.json()["detail"]
    assert not store.data["analysis_runs"] and not store.data["analysis_artifacts"]
    assert proposal == plan_before


def test_grouped_supported_plan_can_be_accepted(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action="instrument_no")
    fid = attach_dataset(client, path)
    supported = plan(fid)
    supported["variables"].append({"file_id": fid, "sheet": "tabla", "column": "grupo", "role": "group"})
    supported["expected_outputs"] = ["Resúmenes por grupo"]
    provider.replies = [reply(proposals=[supported])]
    assert turn(client, path, content="Describe las notas por grupo").status_code == 200
    proposal = client.get(path).json()["proposals"][0]
    result = client.patch(path + "/proposals/" + proposal["id"], json={"status": "accepted"})
    assert result.status_code == 200
    assert client.get(path).json()["conversation"]["current_stage"] == "ready"
