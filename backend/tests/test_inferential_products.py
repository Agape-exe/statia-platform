"""Productos del catálogo contrastados con componentes y resultados reales, sin proveedores."""

import base64
import copy

import pytest
from test_chat_api import api as api
from test_plan_capabilities import complete_integral, descriptive_job, files_for
from test_statistics import job_for

from app.models.chat import AssistantReply, Plan
from app.services.gemini import validate_reply
from app.services.plan_capabilities import validate_products
from app.services.planning_errors import PlanningError
from app.services.statistics.automatic import assess
from app.services.statistics.engine import calculate


def mixed_job(outputs):
    data = "cantidad,estrato,otra\n" + "".join(
        f"{i % 25 + 0.15},{'ABC'[i % 3]},{(i * 7) % 29 + 0.25}\n" for i in range(90)
    )
    job = job_for(data=data.encode())
    measure, group = job["plan"]["variables"]
    other = {**measure, "column": "otra", "role": "predictor"}
    job["plan"].update(
        procedure="integral",
        variables=[measure, other, group],
        objective="Describir y relacionar `cantidad` y `otra` y comparar `cantidad` por `estrato`",
        method="Descripción, correlación Pearson y comparación ANOVA de Welch",
        expected_outputs=outputs,
        components=[
            {"procedure": "descriptive", "method": "Describir `cantidad` y `otra`", "variables": [measure, other]},
            {"procedure": "correlation", "method": "Pearson de `cantidad` y `otra`", "variables": [measure, other]},
            {
                "procedure": "group_comparison",
                "method": "ANOVA de Welch de `cantidad` por `estrato`",
                "variables": [measure, group],
            },
        ],
    )
    job["specification"]["decisions"].append({"variable": other, "statistical_type": "continuous"})
    job["specification"]["components"] = [
        {"source_index": i, "method": method, "design": "independent", "descriptive_intervals": False}
        for i, method in enumerate(["descriptive", "pearson", "welch_anova"])
    ]
    job["independence_evidence"] = ["Muestreo de individuos independientes confirmado por el usuario."]
    return job


@pytest.mark.parametrize(
    "outputs", [[], ["Valores p"], ["Coeficientes de correlación"], ["Valores p", "Coeficientes de correlación"]]
)
def test_mixed_products_validate_prepare_and_are_actually_calculated(outputs):
    job = mixed_job(["Resúmenes globales", *outputs])
    original = copy.deepcopy(job)
    validate_reply(
        AssistantReply(response="Propuesta", suggested_stage="proposal", proposals=[job["plan"]]),
        files_for(job),
        {"project_type": "general"},
    )
    prepared = assess(job)
    if prepared["questions"]:
        job["answers"] = {q["id"]: "none" for q in prepared["questions"] if q["subject"] == "multiplicity"}
        prepared = assess(job)
    assert prepared["status"] == "READY", prepared
    output, _ = calculate(job)
    assert output["status"] == "completed"
    assert output["components"][1]["statistics"]["pairs"][0]["coefficient"] is not None
    assert output["components"][1]["statistics"]["pairs"][0]["p"] is not None
    assert output["components"][2]["statistics"]["p"] is not None
    assert job["plan"] == original["plan"]


@pytest.mark.parametrize("output", ["Valores p", "Coeficientes de correlación"])
def test_descriptive_cannot_generate_inference(output):
    job = descriptive_job([output])
    with pytest.raises(PlanningError) as exc:
        validate_products(Plan.model_validate(job["plan"]), files_for(job))
    assert exc.value.category == "output_capability"


def test_coefficients_require_executable_correlation_not_a_comparison():
    job = mixed_job(["Coeficientes de correlación"])
    job["plan"]["components"].pop(1)
    with pytest.raises(PlanningError):
        validate_products(Plan.model_validate(job["plan"]), files_for(job))
    job = mixed_job(["Coeficientes de correlación"])
    job["plan"]["components"][1]["method"] = "Regresión lineal no implementada"
    with pytest.raises(PlanningError):
        validate_products(Plan.model_validate(job["plan"]), files_for(job))


@pytest.mark.parametrize("output", ["Componente 1: Valores p", "Componente 3: Coeficientes de correlación"])
def test_component_bound_products_cannot_borrow_another_components_outputs(output):
    job = mixed_job([output])
    with pytest.raises(PlanningError):
        validate_products(Plan.model_validate(job["plan"]), files_for(job))


def test_component_bound_products_are_valid_for_their_own_component():
    job = mixed_job(["Componente 2: Coeficientes de correlación", "Componente 3: Valores p"])
    validate_products(Plan.model_validate(job["plan"]), files_for(job))


@pytest.mark.parametrize("output", ["Comparaciones post hoc", "Intervalo de confianza de la media"])
def test_disabled_execution_options_do_not_cover_products(output):
    job = mixed_job([output])
    from app.models.analysis import ExecutionSpec

    spec = ExecutionSpec.model_validate(job["specification"])
    with pytest.raises(PlanningError):
        validate_products(
            Plan.model_validate(job["plan"]), decisions=spec.decisions, execution_components=spec.components
        )


def test_pearson_interval_cannot_be_attributed_to_spearman_or_pending_method():
    job = mixed_job(["Intervalo de confianza para Pearson"])
    job["plan"]["components"][1]["method"] = "Pearson o Spearman, pendiente de decisión"
    with pytest.raises(PlanningError):
        validate_products(Plan.model_validate(job["plan"]), files_for(job))


def test_unknown_output_needs_scope_and_global_product_stays_structural():
    job = mixed_job(["Resultados mágicos completos"])
    with pytest.raises(PlanningError) as exc:
        validate_products(Plan.model_validate(job["plan"]), files_for(job))
    assert exc.value.category == "output_scope"
    job = mixed_job(["Resúmenes globales"])
    job["plan"]["components"][0]["variables"].append(job["plan"]["variables"][-1])
    with pytest.raises(PlanningError) as exc:
        validate_products(Plan.model_validate(job["plan"]), files_for(job))
    assert exc.value.category == "output_capability"


def test_separate_descriptive_products_remain_valid():
    job = complete_integral()
    validate_products(Plan.model_validate(job["plan"]), files_for(job))


def test_legacy_paired_promise_without_method_or_pair_id_is_not_proven_covered():
    job = job_for(procedure="paired_comparison")
    job["plan"].update(
        method="Prueba pareada condicionada a supuestos", expected_outputs=["Estimación del cambio con incertidumbre"]
    )
    with pytest.raises(PlanningError):
        validate_products(Plan.model_validate(job["plan"]), files_for(job))


@pytest.mark.parametrize("provider_id", ["gemini", "openai"])
def test_mixed_inferential_products_can_be_proposed_and_accepted_through_both_providers(api, provider_id):
    from test_chat_api import new, reply, turn
    from test_provider_selection import select, terra

    client, store, gemini = api
    path = new(client, store)
    turn(client, path, action="instrument_no")
    job = mixed_job(["Resúmenes globales", "Valores p", "Coeficientes de correlación"])
    uploaded = client.post(
        path + "/files", files={"file": ("datos.csv", base64.b64decode(job["files"][0]["data"]), "text/csv")}
    )
    assert uploaded.status_code == 201
    original_id = job["files"][0]["id"]
    import json

    proposed = json.loads(json.dumps(job["plan"]).replace(original_id, uploaded.json()["id"]))
    if provider_id == "openai":
        calls = terra(client, [reply(proposals=[proposed])])
        assert select(client, path, "openai").status_code == 200
    else:
        gemini.replies = [reply(proposals=[proposed])]
        calls = gemini.contexts
    response = turn(client, path, content="Solicito Resúmenes globales; Valores p; Coeficientes de correlación.")
    assert response.status_code == 200, response.text
    proposals = client.get(path).json()["proposals"]
    assert len(calls) == len(proposals) == 1
    assert proposals[0]["analysis_plan"]["expected_outputs"] == proposed["expected_outputs"]
    assert client.patch(path + "/proposals/" + proposals[0]["id"], json={"status": "accepted"}).status_code == 200


def test_enabled_posthoc_and_pearson_intervals_are_real_outputs():
    job = mixed_job(["Comparaciones post hoc", "Intervalo de confianza para Pearson"])
    job["specification"]["components"][2]["posthoc"] = "welch_holm"
    output, _ = calculate(job)
    assert output["status"] == "completed"
    assert len(output["components"][2]["statistics"]["posthoc"]) == 3
    assert output["components"][1]["statistics"]["pairs"][0]["ci"] is not None


def test_pending_design_cannot_cover_bound_p_values():
    from app.models.analysis import ExecutionSpec

    job = mixed_job(["Componente 2: Valores p"])
    job["specification"]["components"][1]["design"] = "not_applicable"
    spec = ExecutionSpec.model_validate(job["specification"])
    with pytest.raises(PlanningError):
        validate_products(
            Plan.model_validate(job["plan"]), decisions=spec.decisions, execution_components=spec.components
        )
