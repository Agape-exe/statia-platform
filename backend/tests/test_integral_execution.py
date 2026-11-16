"""Planes integrales: motor real, fixtures públicos/sintéticos, sin servicios remotos."""

import copy
import io
import json
import zipfile
from uuid import uuid4

import pytest
from test_analysis_api import analysis_client as original_analysis_client
from test_statistics import fixture_job, job_for

from app.models.analysis import ExecutionSpec
from app.models.chat import Plan
from app.services.analysis_exports import build_exports
from app.services.methodology import validate_methodology
from app.services.planning_errors import PlanningError
from app.services.statistics.automatic import assess
from app.services.statistics.engine import calculate
from app.services.statistics.preparation import AnalysisError, validate_spec


def integral_job():
    job = fixture_job(
        "titanic.csv",
        [
            ("age", "outcome", "continuous"),
            ("fare", "predictor", "continuous"),
            ("class", "description", "nominal"),
            ("survived", "description", "nominal"),
        ],
        "integral",
        "descriptive",
    )
    age, fare, group, _ = job["plan"]["variables"]
    job["plan"]["components"] = [
        {"procedure": "descriptive", "method": "Descriptivos", "variables": job["plan"]["variables"]},
        {"procedure": "correlation", "method": "Pearson", "variables": [age, fare]},
        {
            "procedure": "group_comparison",
            "method": "Welch ANOVA",
            "variables": [{**fare, "role": "outcome"}, {**group, "role": "group"}],
        },
    ]
    return job


def answer_all(job, design="unknown"):
    for _ in range(8):
        preparation = assess(job)
        if not preparation["questions"]:
            return preparation
        for q in preparation["questions"]:
            options = {c["value"] for c in q["choices"]}
            answer = (
                design
                if q["subject"].startswith("design:")
                else "nominal"
                if (q.get("variable") or {}).get("column") == "survived"
                else "continuous"
                if "continuous" in options
                else "missing"
                if "missing" in options
                else "yes"
            )
            job.setdefault("answers", {})[q["id"]] = answer
    pytest.fail("Bucle de preguntas")


def execute(job, preparation):
    return calculate(
        {
            **job,
            "specification": {**preparation["specification"], "decisions_confirmed": True},
            "preparation_fingerprint": preparation["fingerprint"],
            "preparation_context": {k: job[k] for k in ("answers", "completed_components") if k in job},
        }
    )


def test_titanic_selective_uncertainty_exports_and_continuation():
    job = integral_job()
    original = copy.deepcopy(job["plan"])
    partial = answer_all(job)
    assert partial["status"] == "PARTIALLY_READY"
    assert [s["status"] for s in partial["components"]] == ["READY", "BLOCKED_UNCERTAINTY", "BLOCKED_UNCERTAINTY"]
    assert partial["questions"] == []
    assert partial["specification"]["partial_execution"] is True
    assert [c["source_index"] for c in partial["specification"]["components"]] == [0]
    assert partial["files"][0]["rows"] == 891
    result, charts = execute(job, partial)
    assert result["status"] == "partial"
    assert [c["source_index"] for c in result["components"]] == [0]
    assert "IC media" not in json.dumps(result["components"][0]["tables"])
    assert not result["components"][0]["statistics"].get("p")
    assert job["plan"] == original == result["plan_snapshot"]
    with zipfile.ZipFile(io.BytesIO(build_exports(result, charts)["resultados_analisis.zip"][0])) as archive:
        manifest = json.loads(archive.read("manifiesto.json"))
        assert manifest["status"] == "partial"
        assert len(manifest["component_states"]) == 3
        assert manifest["procedures"] == ["descriptive"]
        assert archive.testzip() is None
    job["completed_components"] = result["component_states"]
    waiting = assess(job)
    assert waiting["components"][0]["status"] == "COMPLETED"
    assert waiting["status"] == "BLOCKED_UNCERTAINTY"
    for qid in job["answers"]:
        if job["answers"][qid] == "unknown":
            job["answers"][qid] = "yes"
    ready = assess(job)
    assert ready["status"] == "READY"
    assert [c["source_index"] for c in ready["specification"]["components"]] == [1, 2]
    job["run_id"] = str(uuid4())
    resumed, _ = execute(job, ready)
    assert resumed["status"] == "completed"
    assert [c["source_index"] for c in resumed["components"]] == [1, 2]
    assert resumed["component_states"][0]["completed_run_id"] == result["run_id"]
    job["completed_components"] += resumed["component_states"]
    assert assess(job)["status"] == "COMPLETED"


def test_all_ready_full_execution_and_nothing_executable():
    job = integral_job()
    ready = answer_all(job, "yes")
    assert ready["status"] == "READY"
    assert ready["specification"]["partial_execution"] is False
    result, _ = execute(job, ready)
    assert result["status"] == "completed"
    job["plan"]["components"] = job["plan"]["components"][1:]
    job["plan"]["variables"] = job["plan"]["variables"][:3]
    job["answers"] = {}
    blocked = answer_all(job)
    assert blocked["status"] == "BLOCKED_UNCERTAINTY"
    assert not any(c["status"] == "READY" for c in blocked["components"])


def test_hashes_changed_original_and_selective_bypass():
    job = integral_job()
    partial = answer_all(job)
    result, _ = execute(job, partial)
    job["completed_components"] = result["component_states"]
    job["files"][0]["original_name"] = "nuevo.csv"
    assert assess(job)["components"][0]["status"] != "COMPLETED"
    spec = ExecutionSpec.model_validate({**partial["specification"], "decisions_confirmed": True})
    with pytest.raises(AnalysisError, match="sin omisiones"):
        validate_spec(Plan.model_validate(job["plan"]), spec.model_copy(update={"partial_execution": False}))
    with pytest.raises(AnalysisError, match="preparación vigente"):
        calculate({**job, "specification": spec.model_dump(mode="json")})


def test_advanced_descriptive_cannot_present_intervals_without_independence():
    job = job_for(procedure="descriptive", methods=["descriptive"])
    job["specification"]["components"][0]["design"] = "not_applicable"
    with pytest.raises(AnalysisError, match="intervalos de media"):
        calculate(job)
    job["specification"]["components"][0]["descriptive_intervals"] = False
    result, _ = calculate(job)
    assert "IC media inferior" not in json.dumps(result["components"][0]["tables"])


def test_dependencies_and_holm_do_not_split_inference():
    job = integral_job()
    job["plan"]["components"][0]["depends_on"] = [1]
    blocked = answer_all(job)
    assert blocked["status"] == "BLOCKED_UNCERTAINTY"
    assert "Requiere completar" in " ".join(blocked["components"][0]["blockers"])
    job["plan"]["components"][1]["depends_on"] = [0]
    assert all(c["status"] == "UNSUPPORTED" for c in assess(job)["components"])
    job = integral_job()
    preparation = assess(job)
    for q in preparation["questions"]:
        job.setdefault("answers", {})[q["id"]] = "nominal" if q.get("variable") else "unknown"
    # La familia permanece pendiente; ninguna prueba individual se confirma a escondidas.
    assert all(c["status"] != "READY" for c in assess(job)["components"][1:])


def test_planning_rejects_dependency_cycles_before_acceptance():
    job = integral_job()
    job["plan"]["components"][0]["depends_on"] = [1]
    job["plan"]["components"][1]["depends_on"] = [0]
    with pytest.raises(PlanningError, match="cíclicas"):
        validate_methodology(Plan.model_validate(job["plan"]), lambda _: pytest.fail("Dependencias no validadas"))


def test_synthetic_names_and_independent_components():
    job = job_for(procedure="correlation")
    variables = job["plan"]["variables"]
    job["plan"].update(
        procedure="integral",
        components=[
            {"procedure": "descriptive", "method": "Descriptivos", "variables": variables},
            {"procedure": "correlation", "method": "Pearson", "variables": variables},
        ],
    )
    ready = answer_all(job, "yes")
    assert ready["status"] == "READY"
    assert execute(job, ready)[0]["status"] == "completed"


def test_multiple_files_keep_completed_scope_and_dependency_order():
    job = job_for(procedure="descriptive")
    other = job_for(procedure="correlation")
    first = job["plan"]["variables"]
    job["files"] += other["files"]
    job["plan"]["variables"] += other["plan"]["variables"]
    job["plan"].update(
        procedure="integral",
        components=[
            {"procedure": "descriptive", "method": "Descriptivos", "variables": first[:2]},
            {"procedure": "correlation", "method": "Pearson", "variables": other["plan"]["variables"]},
        ],
    )
    partial = answer_all(job)
    assert partial["status"] == "PARTIALLY_READY"
    result, _ = execute(job, partial)
    job["completed_components"] = result["component_states"]
    other_file = job["files"][1]
    other_file["original_name"] = "medidas_revisadas.csv"
    assert assess(job)["components"][0]["status"] == "COMPLETED"
    dependent = integral_job()
    dependent["plan"]["components"][0]["depends_on"] = [2]
    ready = answer_all(dependent, "yes")
    result, _ = execute(dependent, ready)
    assert [c["source_index"] for c in result["components"]].index(2) < [
        c["source_index"] for c in result["components"]
    ].index(0)


@pytest.fixture
def integral_client():
    for client, store, endpoint, _ in original_analysis_client.__wrapped__():
        import base64

        job = integral_job()
        store.data["conversations"][0]["primary_goal"] = job["plan"]["objective"]
        previous = store.objects["original"]
        store.objects["original"] = base64.b64decode(job["files"][0]["data"])
        store.data["analysis_proposals"][0]["analysis_plan"] = job["plan"]
        store.data["project_files"][0].update({k: v for k, v in job["files"][0].items() if k != "data"})
        store.data["conversation_files"][0]["file_id"] = job["files"][0]["id"]
        try:
            yield client, store, endpoint
        finally:
            store.objects["original"] = previous


def test_http_persistence_resume_idempotency_and_private_zip(integral_client):
    client, store, endpoint = integral_client
    path = endpoint.rsplit("/proposals/", 1)[0]
    pid = store.data["analysis_proposals"][0]["id"]

    def turn(action, **values):
        response = client.post(
            path + "/turns", json={"request_id": str(uuid4()), "action": action, "proposal_id": pid, **values}
        )
        assert response.status_code == 200, response.text
        return client.get(path).json()["conversation"]["stage_data"]["execution_preparation"]["result"]

    preparation = turn("prepare_execution")
    for _ in range(8):
        if not preparation["questions"]:
            break
        q = preparation["questions"][0]
        preparation = turn(
            "clarify_execution",
            question_id=q["id"],
            answer="unknown" if q["subject"].startswith("design:") else "nominal",
        )
    assert preparation["status"] == "PARTIALLY_READY"
    assert not store.data["analysis_runs"]
    assert turn("message", content="No lo sé") == preparation
    body = {
        "request_id": preparation["request_id"],
        "preparation_fingerprint": preparation["fingerprint"],
        "specification": {**preparation["specification"], "decisions_confirmed": True},
    }
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["status"] == "partial"
    assert client.post(endpoint, json=body).json()["id"] == first["id"]
    history = client.get(path).json()
    event = next(m for m in history["messages"] if m["metadata"].get("analysis_run_id"))
    assert event["metadata"]["execution_request_id"] == body["request_id"]
    assert event["metadata"]["proposal_id"] == pid
    waiting = turn("prepare_execution")
    assert waiting["components"][0]["completed_run_id"] == first["id"]
    question = next(q for q in waiting["clarifications"] if q["status"] == "unknown")
    turn("review_execution", question_id=question["id"])
    resumed = turn("clarify_execution", question_id=question["id"], answer="yes")
    assert [c["source_index"] for c in resumed["specification"]["components"]] == [1, 2]
    response = client.post(
        endpoint,
        json={
            "request_id": resumed["request_id"],
            "preparation_fingerprint": resumed["fingerprint"],
            "specification": {**resumed["specification"], "decisions_confirmed": True},
        },
    )
    assert response.status_code == 200, response.text
    second = response.json()
    assert second["status"] == "completed"
    assert len(store.data["analysis_runs"]) == 2
    base = f"/projects/{store.project_id}/analysis-runs"
    assert client.get(f"{base}/{first['id']}").json()["result"] == first["result"]
    archive = client.get(f"{base}/{second['id']}/download")
    assert archive.status_code == 200
    assert archive.headers["cache-control"] == "private, no-store"
    with zipfile.ZipFile(io.BytesIO(archive.content)) as contents:
        states = json.loads(contents.read("manifiesto.json"))["component_states"]
        assert states[0]["completed_run_id"] == first["id"]
    assert turn("prepare_execution")["status"] == "COMPLETED"


def test_historical_result_replay_does_not_apply_new_execution_requirements():
    for client, store, endpoint, body in original_analysis_client.__wrapped__():
        store.data["analysis_proposals"][0]["analysis_plan"]["procedure"] = "descriptive"
        body["specification"]["components"][0]["method"] = "descriptive"
        first = client.post(endpoint, json=body)
        assert first.status_code == 200, first.text
        # Representación descriptiva anterior: el diseño no estaba confirmado.
        historic = store.data["analysis_runs"][0]
        historic["specification"]["components"][0]["design"] = "not_applicable"
        historic["result"]["specification"] = copy.deepcopy(historic["specification"])
        body["specification"]["components"][0]["design"] = "not_applicable"
        count = store.download_count
        replay = client.post(endpoint, json=body)
        assert replay.status_code == 200, replay.text
        assert replay.json()["id"] == first.json()["id"]
        assert store.download_count == count
