"""Regresiones con sobres sintéticos capturados del proveedor y un plan exportado."""

import json
from pathlib import Path

import pytest
from test_statistics import job_for

from app.models.chat import Plan
from app.services.execution_preparation import result_discussion
from app.services.gemini_schema import reply_schema
from app.services.plan_capabilities import validate_products
from app.services.planning_errors import PlanningError
from app.services.statistics.automatic import assess
from app.services.statistics.catalog import CATALOG

FIXTURES = Path(__file__).parent / "fixtures" / "gemini_planning_v7"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_welch_diagnostic_identifies_product_and_method():
    plan = Plan.model_validate(fixture("02-05.json")["response"]["proposals"][0])
    with pytest.raises(PlanningError) as issue:
        validate_products(plan.model_copy(update={"expected_outputs": [plan.expected_outputs[1]]}))
    assert plan.expected_outputs[1] in str(issue.value) and "welch_t" in str(issue.value)


def test_significance_goal_keeps_planning_scope():
    assert not result_discussion("Determinar si existe una diferencia estadísticamente significativa entre las medias")


def test_filter_is_expressible_for_descriptive_plan():
    plan = fixture("09-08.json")["response"]["proposals"][0]
    assert plan["comparison"] is None and not plan.get("filters")
    props = reply_schema()["properties"]["proposals"]["items"]["properties"]
    assert "filters" in props


def test_score_requires_decision_before_frequencies():
    plan = fixture("accepted-07.json")
    job = job_for(b"puntaje_total\n40\n45\n48\n50\n52\n55\n58\n62\n65\n68\n70\n75\n")
    job["files"][0]["id"] = plan["variables"][0]["file_id"]
    job["plan"] = plan
    prepared = assess(job)
    assert any(q["subject"].endswith(":type") for q in prepared["questions"]), prepared["status"]


@pytest.mark.parametrize("code", CATALOG)
def test_provider_contract_can_name_each_catalogued_product(code):
    products = reply_schema()["properties"]["proposals"]["items"]["properties"]["expected_outputs"]["items"]
    assert set(CATALOG[code].output_products) <= set(products["properties"]["product"]["enum"])


@pytest.mark.parametrize(
    "name", ["01-05", "02-05", "03-06", "08-08", "09-08", "10-06", "11-06", "v8-02", "v8-12", "v8-16", "v8-17", "v8-21"]
)
def test_replay_observed_planning_assessment(name):
    from app.core.config import Settings
    from app.services.profiling import inspect_file
    from app.services.reply_contract import normalize_reply, parse_assistant_reply
    from app.services.planning_validation import assess_reply
    from app.services.variable_types import bind_confirmations

    captured = fixture(name + ".json")
    raw = captured["response"]
    plan = raw["proposals"][0]
    fid = plan["variables"][0]["file_id"]
    scale = any(v["column"] == "puntaje_total" for v in plan["variables"])
    csv = (
        b"puntaje_total\n" + b"".join(f"{40 + i}\n".encode() for i in range(12))
        if scale
        else b"grupo,medicion\n" + b"".join(f"{'A' if i < 8 else 'B'},{11 + i}\n".encode() for i in range(18))
    )
    files = [
        {
            "id": fid,
            "file_role": "dataset",
            "original_name": "sintetico.csv",
            "metadata": inspect_file("sintetico.csv", csv, "dataset", Settings(_env_file=None)),
        }
    ]
    mode = captured.get("interaction_mode", "planning")
    reply = normalize_reply(parse_assistant_reply(json.dumps(raw), mode), mode)
    if name in {"v8-17", "v8-21"}:
        reply = bind_confirmations(reply, [{"variable": plan["variables"][0], "statistical_type": "discrete"}], files)
    assessed = assess_reply(
        reply,
        files,
        {"project_type": "thesis" if name.endswith("-06") else "general"},
        {"interaction_mode": mode, "independence_evidence": ["Grupos independientes, sin pares ni repeticiones."]},
    )
    assert [i.category for i in assessed.issues] == [i["category"] for i in captured["observed_issues"]]
    if name == "v8-12":
        assert assessed.valid_plans[0].filters[0].values == ["A"]


@pytest.mark.parametrize(
    "literal, expected, ambiguous",
    [
        ("resumen filtrado a sede igual a norte.", ["Norte"], False),
        ("resumen filtrado a sede igual a norte y sur.", [], True),
        ("resumen filtrado a sede igual a oeste.", [], True),
        ("resumen filtrado a distrito igual a norte.", [], True),
    ],
)
def test_user_filter_requires_an_exact_observed_level(literal, expected, ambiguous):
    from app.services.requested_scope import explicit_filters

    column = {"name": "sede", "levels": [{"value": "Norte"}, {"value": "Sur"}]}
    files = [{"id": "uno", "metadata": {"selected_sheet": "tabla", "profile": {"columns": [column]}}}]
    selected, unresolved = explicit_filters(literal, files)
    assert unresolved is ambiguous
    assert [value for f in selected for value in f["values"]] == expected
