"""Preparación real sin proveedor, originales públicos/sintéticos e integración HTTP controlada."""

import base64
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_analysis_api import analysis_client as original_analysis_client
from test_statistics import fixture_job, job_for
from test_statistics_additional import association_job, paired_job, ranked_job

from app.models.analysis import ExecutionSpec
from app.models.chat import Plan
from app.services.execution_preparation import text_answer
from app.services.statistics.automatic import assess
from app.services.statistics.engine import calculate
from app.services.statistics.methods import named_methods
from app.services.statistics.preparation import AnalysisError, validate_spec


@pytest.fixture
def preparation_client():
    for client, store, endpoint, body in original_analysis_client.__wrapped__():
        store.data["conversations"][0]["primary_goal"] = "Comparar medidas"
        yield client, store, endpoint, body


def resolve(job, *, marker="missing"):
    """Simula respuestas explícitas; no sustituye evidencia del motor."""
    job.setdefault("answers", {})
    for _ in range(10):
        result = assess(job)
        if result["status"] != "NEEDS_CLARIFICATION":
            return result
        for q in result["questions"]:
            values = {c["value"] for c in q["choices"]}
            selected = next((v for v in ["continuous", marker, "yes", "holm", "spearman"] if v in values), None)
            assert selected, q
            job["answers"][q["id"]] = selected
    raise AssertionError("No concluyó la preparación")


def confirmed_job(job, preparation):
    return {
        **job,
        "specification": {**preparation["specification"], "decisions_confirmed": True},
        "preparation_fingerprint": preparation["fingerprint"],
        "preparation_context": {"answers": job.get("answers", {})},
    }


def test_ready_preserves_confirmation_and_does_not_calculate(monkeypatch):
    job = job_for(procedure="descriptive")
    monkeypatch.setattr(
        "app.services.statistics.engine.run_component", lambda *args: pytest.fail("Se calculó durante preparación")
    )
    result = assess(job)
    assert result["status"] == "READY"
    assert result["specification"]["decisions_confirmed"] is False
    assert all(e["origin"] != "user" for e in result["evidence"])
    with pytest.raises(AnalysisError, match="Confirma"):
        validate_spec(Plan.model_validate(job["plan"]), ExecutionSpec.model_validate(result["specification"]))


def penguins_job():
    job = fixture_job(
        "penguins.csv",
        [("body_mass_g", "outcome", "continuous"), ("sex", "group", "nominal"), ("species", "description", "nominal")],
        "group_comparison",
        "welch_t",
    )
    # El contrato aceptado se conserva; solo la preparación es nueva.
    job["plan"]["method"] = "t de Welch"
    selection = {"variable": job["plan"]["variables"][2], "values": ["Adelie"]}
    job["plan"]["comparison"] = {
        "design": "independent",
        "groups": ["female", "male"],
        "filters": [selection],
        "strata": None,
        "independence": "Pendiente del diseño",
        "valid_observations": "Casos completos",
        "missing_data": "Pendiente",
        "outliers": "Conservar",
        "normality": "Diagnosticar",
        "variance_assumption": "unequal_allowed",
        "effect_size": {
            "name": "hedges_g",
            "standardizer": "pooled_sd",
            "definition": "SD combinada con J exacto",
            "correction": "gl n1+n2-2",
            "confidence_interval": "IC diferencia",
        },
        "purpose": "exploratory",
        "multiplicity": "none",
        "multiplicity_reason": "Un contraste",
    }
    return job


def test_penguins_scope_ambiguity_effect_and_execution():
    job = penguins_job()
    first = assess(job)
    assert first["files"][0]["rows"] == 344
    marker_questions = [q for q in first["questions"] if "significa" in q["prompt"]]
    assert len(marker_questions) == 1 and marker_questions[0]["variable"]["column"] == "sex"
    assert first["specification"]["components"][0]["design"] == "not_applicable"
    assert not any("varianzas comparables" in q["prompt"] for q in first["questions"])
    ready = resolve(job)
    assert ready["status"] == "READY", ready
    assert ready["specification"]["filters"] == job["plan"]["comparison"]["filters"]
    assert ready["specification"]["components"][0]["group_values"] == ["female", "male"]
    result, _ = calculate(confirmed_job(job, ready))
    component = result["components"][0]
    assert component["sample"]["after_filters"] == 152
    assert component["sample"]["used"] == 146
    assert component["statistics"]["difference"] == pytest.approx(-674.6575342465753)
    assert component["statistics"]["hedges_df"] == 144


def test_titanic_three_classes_select_welch_anova_and_not_t():
    job = fixture_job(
        "titanic.csv",
        [("fare", "outcome", "continuous"), ("pclass", "group", "nominal")],
        "group_comparison",
        "welch_anova",
    )
    ready = resolve(job)
    assert ready["status"] == "READY", ready
    assert ready["files"][0]["rows"] == 891
    assert ready["specification"]["components"][0]["method"] == "welch_anova"
    assert ready["specification"]["decisions"][1]["statistical_type"] == "nominal"
    result, _ = calculate(confirmed_job(job, ready))
    assert result["status"] == "completed"
    assert [g["n"] for g in result["components"][0]["sample"]["groups"]] == [216, 184, 491]
    job["plan"]["method"] = "t de Welch"
    assert resolve(job)["status"] == "UNSUPPORTED"


@pytest.mark.parametrize("method", ["student_t", "welch_t", "anova", "welch_anova", "mann_whitney", "kruskal"])
def test_existing_group_methods_with_arbitrary_columns(method):
    groups = {"A": [1, 2, 3], "B": [4, 5, 6]}
    if method in {"anova", "welch_anova", "kruskal"}:
        groups["C"] = [7, 8, 9]
    job = ranked_job(method, groups)
    job["plan"]["method"] = method
    ready = resolve(job)
    assert ready["status"] == "READY", ready
    assert ready["specification"]["components"][0]["method"] == method


@pytest.mark.parametrize("method", ["pearson", "spearman"])
def test_correlations_require_design_and_respect_method(method):
    job = job_for(procedure="correlation", methods=[method])
    job["plan"]["method"] = method
    ready = resolve(job)
    assert ready["status"] == "READY", ready
    assert ready["specification"]["components"][0]["method"] == method


@pytest.mark.parametrize("method", ["paired_t", "wilcoxon"])
def test_paired_methods_require_pair_evidence(method):
    job = paired_job(method, list(range(1, 12)), [0] * 11)
    job["plan"]["method"] = method
    ready = resolve(job)
    assert ready["status"] == "READY", ready
    assert ready["specification"]["components"][0]["design"] == "paired"


@pytest.mark.parametrize("counts,expected", [([[1, 2], [3, 4]], "fisher_exact"), ([[10, 20], [30, 40]], "chi_square")])
def test_categorical_selection_uses_expected_counts_not_significance(counts, expected):
    job = association_job(expected, counts)
    ready = resolve(job)
    assert ready["status"] == "READY", ready
    assert ready["specification"]["components"][0]["method"] == expected


def test_explicit_chi_square_is_not_silently_replaced():
    job = association_job("chi_square", [[1, 2], [3, 4]])
    job["plan"]["method"] = "chi-cuadrado"
    result = resolve(job)
    assert result["status"] == "UNSUPPORTED"
    assert "Fisher" in " ".join(result["blockers"])


def test_unknown_and_related_design_never_become_confirmation():
    job = job_for()
    result = assess(job)
    for q in result["questions"]:
        job.setdefault("answers", {})[q["id"]] = "unknown"
    result = assess(job)
    assert result["status"] == "NEEDS_CLARIFICATION"
    assert result["warnings"]
    assert not any(e["origin"] == "user" for e in result["evidence"])
    for q in result["questions"]:
        if any(c["value"] == "yes" for c in q["choices"]):
            job["answers"][q["id"]] = "no"
    assert assess(job)["status"] == "UNSUPPORTED"


def test_documented_user_design_is_reused_without_question():
    job = fixture_job(
        "titanic.csv",
        [("fare", "outcome", "continuous"), ("pclass", "group", "nominal")],
        "group_comparison",
        "welch_anova",
    )
    job["independence_evidence"] = ["El usuario confirmó la recolección individual sin repeticiones ni conglomerados."]
    assert assess(job)["status"] == "READY"


def test_marker_retained_as_legitimate_category_and_scoped():
    job = job_for(b"cantidad,estrato\n1,A\n2,A\n3,NA\n4,NA\n5,B\n6,B\n")
    result = resolve(job, marker="retained")
    assert result["status"] == "READY", result
    decisions = result["specification"]["decisions"]
    assert decisions[1]["retained_markers"] == ["NA"]
    assert decisions[0]["retained_markers"] == []
    assert result["specification"]["components"][0]["method"] == "welch_anova"


def test_changed_original_invalidates_answers_and_fingerprint():
    job = job_for()
    ready = resolve(job)
    raw = base64.b64decode(job["files"][0]["data"]).replace(b"6,B", b"7,B")
    job["files"][0]["data"] = base64.b64encode(raw).decode()
    changed = assess(job)
    assert changed["status"] == "NEEDS_CLARIFICATION"
    assert changed["fingerprint"] != ready["fingerprint"]
    with pytest.raises(AnalysisError, match="cambiaron"):
        calculate(confirmed_job(job, ready))


def test_unsupported_and_ancient_integral_do_not_invent_components():
    job = job_for()
    job["plan"]["method"] = "Regresión logística"
    assert assess(job)["status"] == "UNSUPPORTED"
    job["plan"]["procedure"] = "integral"
    assert assess(job)["status"] == "UNSUPPORTED"


def test_advanced_cannot_replace_explicit_accepted_method():
    job = job_for()
    job["plan"]["method"] = "t de Welch"
    spec = ExecutionSpec.model_validate(job["specification"])
    spec.components[0].method = "student_t"
    spec.components[0].equal_variances_confirmed = True
    with pytest.raises(AnalysisError, match="expresamente aceptado"):
        validate_spec(Plan.model_validate(job["plan"]), spec)


def test_chat_preparation_answers_reload_execution_and_idempotency(preparation_client):
    client, store, endpoint, _ = preparation_client
    path = endpoint.rsplit("/proposals/", 1)[0]
    proposal = store.data["analysis_proposals"][0]
    goal = store.data["conversations"][0].get("primary_goal")
    body = {"request_id": str(uuid4()), "action": "prepare_execution", "proposal_id": proposal["id"]}
    response = client.post(path + "/turns", json=body)
    assert response.status_code == 200, response.text
    assert client.post(path + "/turns", json=body).json()["replayed"] is True
    assert len(store.data["messages"]) == 2
    for _ in range(8):
        detail = client.get(path).json()
        state = detail["conversation"]["stage_data"]["execution_preparation"]
        if state["result"]["status"] != "NEEDS_CLARIFICATION":
            break
        q = state["result"]["questions"][0]
        values = {c["value"] for c in q["choices"]}
        answer = "yes" if "yes" in values else "continuous"
        body = {
            "request_id": str(uuid4()),
            "action": "clarify_execution",
            "proposal_id": proposal["id"],
            "question_id": q["id"],
            "answer": answer,
        }
        response = client.post(path + "/turns", json=body)
        assert response.status_code == 200, response.text
    ready = state["result"]
    assert ready["status"] == "READY", ready
    assert len(store.data["analysis_runs"]) == 0
    assert detail["conversation"]["primary_goal"] == goal
    body = {
        "request_id": ready["request_id"],
        "specification": {**ready["specification"], "decisions_confirmed": True},
        "preparation_fingerprint": ready["fingerprint"],
    }
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert client.post(endpoint, json=body).json()["id"] == response.json()["id"]
    assert len(store.data["analysis_runs"]) == 1
    assert client.get(path).json()["conversation"]["stage_data"]["execution_preparation"] == state
    # Otra preparación idéntica, incluso desde otro dispositivo, conserva UUID.
    again = client.post(
        path + "/turns", json={"request_id": str(uuid4()), "action": "prepare_execution", "proposal_id": proposal["id"]}
    )
    assert again.status_code == 200
    assert (
        client.get(path).json()["conversation"]["stage_data"]["execution_preparation"]["result"]["request_id"]
        == body["request_id"]
    )
    assert client.post(endpoint, json=body).json()["id"] == response.json()["id"]
    assert len(store.data["analysis_runs"]) == 1


def test_preparation_rejects_unaccepted_or_unlinked_plan(preparation_client):
    client, store, endpoint, _ = preparation_client
    path = endpoint.rsplit("/proposals/", 1)[0]
    proposal = store.data["analysis_proposals"][0]
    proposal["status"] = "rejected"
    body = {"request_id": str(uuid4()), "action": "prepare_execution", "proposal_id": proposal["id"]}
    assert client.post(path + "/turns", json=body).status_code == 409
    proposal["status"] = "accepted"
    store.data["conversation_files"] = []
    body["request_id"] = str(uuid4())
    assert client.post(path + "/turns", json=body).status_code == 422


@pytest.mark.parametrize(
    "text",
    [
        "No sé qué método corresponde",
        "No conozco el significado de esos códigos",
        "Haz el análisis que consideres apropiado",
        "No entiendo qué significa independencia",
        "No sé si esos valores son datos faltantes",
    ],
)
def test_nonexpert_chat_never_invents_an_answer(preparation_client, text):
    client, store, endpoint, _ = preparation_client
    path = endpoint.rsplit("/proposals/", 1)[0]
    proposal = store.data["analysis_proposals"][0]
    assert (
        client.post(
            path + "/turns",
            json={"request_id": str(uuid4()), "action": "prepare_execution", "proposal_id": proposal["id"]},
        ).status_code
        == 200
    )
    response = client.post(path + "/turns", json={"request_id": str(uuid4()), "content": text})
    assert response.status_code == 200, response.text
    detail = client.get(path).json()
    assert detail["conversation"]["stage_data"]["execution_preparation"]["result"]["status"] == "NEEDS_CLARIFICATION"
    assert "descriptiva" in detail["messages"][-1]["content"]
    assert not store.data["analysis_runs"]


def test_simple_text_answers_are_limited_to_current_question():
    missing_question = {
        "choices": [
            {"value": "missing", "label": "Representa información faltante"},
            {"value": "retained", "label": "Es un valor válido"},
            {"value": "unknown", "label": "No lo sé"},
        ]
    }
    assert text_answer(missing_question, "Son datos faltantes") == "missing"
    assert text_answer(missing_question, "Es una categoría válida") == "retained"
    assert text_answer(missing_question, "Sí") is None
    assert text_answer(missing_question, "No sé si esos valores son datos faltantes") == "unknown"


@pytest.mark.parametrize(
    "method,a,b", [("paired_t", [1, 2], [0, 0]), ("paired_t", [1, 2, 3], [0, 1, 2]), ("wilcoxon", [1, 3, 5], [0, 0, 0])]
)
def test_preparation_checks_paired_sample_and_variation_before_ready(method, a, b):
    job = paired_job(method, a, b)
    job["plan"]["method"] = method
    assert resolve(job)["status"] == "UNSUPPORTED"


def test_integral_reuses_design_and_defaults_to_explicitly_explained_holm():
    job = job_for()
    variables = job["plan"]["variables"]
    job["plan"]["procedure"] = "integral"
    job["plan"]["components"] = [
        {"procedure": "descriptive", "method": "Descriptivos", "variables": variables},
        {"procedure": "group_comparison", "method": "t de Welch", "variables": variables},
    ]
    ready = resolve(job)
    assert ready["status"] == "READY", ready
    assert ready["specification"]["multiplicity"] == "holm"
    assert any(e["subject"] == "Comparaciones múltiples" and e["origin"] == "inferred" for e in ready["evidence"])


@pytest.mark.parametrize(
    "text,expected",
    [
        ("ANOVA de Welch", {"welch_anova"}),
        ("t de Welch o ANOVA de Welch", {"welch_t", "welch_anova"}),
        ("ANOVA clásico o de Welch", {"anova", "welch_anova"}),
    ],
)
def test_legacy_method_alternatives_remain_ambiguous(text, expected):
    assert named_methods(SimpleNamespace(method=text)) == expected
