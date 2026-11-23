"""Generalización de Excel y contratos descriptivos; sin servicios remotos."""

import copy
import io
import json
from statistics import mean, stdev
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from test_chat_api import new, reply, turn
from test_session6 import local as local
from test_session6 import upload

from app.core.config import Settings
from app.models.chat import Plan, Turn
from app.services.gemini import build_context, validate_plan
from app.services.plan_capabilities import SUMMARY_STATISTICS
from app.services.profiling import inspect_file
from app.services.provider_runtime import RequestBudget
from app.services.requested_scope import (
    product_request,
    requested_scope,
    validate_plan_scope,
)

# Extracto de sepal.length del conjunto público iris (R datasets), sin las otras
# mediciones. Es una fixture de referencia, no una regla de la aplicación.
IRIS_LENGTHS = {
    "Setosa": [
        5.1,
        4.9,
        4.7,
        4.6,
        5,
        5.4,
        4.6,
        5,
        4.4,
        4.9,
        5.4,
        4.8,
        4.8,
        4.3,
        5.8,
        5.7,
        5.4,
        5.1,
        5.7,
        5.1,
        5.4,
        5.1,
        4.6,
        5.1,
        4.8,
        5,
        5,
        5.2,
        5.2,
        4.7,
        4.8,
        5.4,
        5.2,
        5.5,
        4.9,
        5,
        5.5,
        4.9,
        4.4,
        5.1,
        5,
        4.5,
        4.4,
        5,
        5.1,
        4.8,
        5.1,
        4.6,
        5.3,
        5,
    ],
    "Versicolor": [
        7,
        6.4,
        6.9,
        5.5,
        6.5,
        5.7,
        6.3,
        4.9,
        6.6,
        5.2,
        5,
        5.9,
        6,
        6.1,
        5.6,
        6.7,
        5.6,
        5.8,
        6.2,
        5.6,
        5.9,
        6.1,
        6.3,
        6.1,
        6.4,
        6.6,
        6.8,
        6.7,
        6,
        5.7,
        5.5,
        5.5,
        5.8,
        6,
        5.4,
        6,
        6.7,
        6.3,
        5.6,
        5.5,
        5.5,
        6.1,
        5.8,
        5,
        5.6,
        5.7,
        5.7,
        6.2,
        5.1,
        5.7,
    ],
    "Virginica": [
        6.3,
        5.8,
        7.1,
        6.3,
        6.5,
        7.6,
        4.9,
        7.3,
        6.7,
        7.2,
        6.5,
        6.4,
        6.8,
        5.7,
        5.8,
        6.4,
        6.5,
        7.7,
        7.7,
        6,
        6.9,
        5.6,
        7.7,
        6.3,
        6.7,
        7.2,
        6.2,
        6.1,
        6.4,
        7.2,
        7.4,
        7.9,
        6.4,
        6.3,
        6.1,
        7.7,
        6.3,
        6.4,
        6,
        6.9,
        6.7,
        6.9,
        5.8,
        6.8,
        6.7,
        6.7,
        6.3,
        6.5,
        6.2,
        5.9,
    ],
}


def workbook(tables):
    book, out = Workbook(), io.BytesIO()
    book.remove(book.active)
    for name, rows in tables.items():
        tab = book.create_sheet(name)
        for row in rows:
            tab.append(row)
    book.save(out)
    book.close()
    return out.getvalue()


def heterogeneous():
    return workbook(
        {
            "Medición física": [["presión kPa", "registro_id"], *[[100 + i * 0.73, f"r-{i}"] for i in range(123)]],
            "Economía 日本": [
                ["sector", "importe", "fecha"],
                ["NA", 12, "2024-01-01"],
                ["Sur", None, "2024-01-02"],
                ["Sur", "ambiguo", "2024-01-03"],
            ],
            "Vacía": [],
            "Notas": [["título", "título"], ["texto", "no tabular"]],
        }
    )


def descriptive(fid, sheet, column, outputs=None):
    return {
        "title": "Descripción univariada",
        "objective": f"Describir {column}",
        "variables": [{"file_id": fid, "sheet": sheet, "column": column, "role": "outcome"}],
        "procedure": "descriptive",
        "method": f"Estadística descriptiva de {column}",
        "justification": "Objetivo descriptivo del investigador",
        "requirements": ["Revisar unidades"],
        "limitations": ["Sin inferencia ni comparaciones"],
        "methodology_confirmed": True,
        "expected_outputs": outputs or list(SUMMARY_STATISTICS.values()),
    }


def test_global_profiles_are_independent_heterogeneous_and_open_book_once():
    from app.services.workbook import load_workbook

    with patch("app.services.workbook.load_workbook", wraps=load_workbook) as opening:
        meta = inspect_file("arbitrario.xlsx", heterogeneous(), "dataset", Settings(_env_file=None))
    assert opening.call_count == 1 and meta["needs_sheet_selection"] and "profile" not in meta
    measure, economy, empty, notes = meta["sheet_profiles"]
    assert measure["profile"]["row_count"] == 123 and measure["profile"]["column_count"] == 2
    assert economy["profile"]["row_count"] == 3 and economy["profile"]["column_count"] == 3
    assert economy["profile"]["columns"][0]["ambiguous_missing"] == {"NA": 1}
    assert economy["profile"]["columns"][1]["inferred_type"] == "mixed"
    assert empty["status"] == notes["status"] == "unavailable"
    assert empty["warnings"] and notes["warnings"]


@pytest.mark.parametrize("mode", ["general", "thesis"])
def test_understanding_before_selection_and_context_privacy(local, mode):
    client, store, provider = local
    store.data["projects"][0]["project_type"] = mode
    path = new(client, store)
    turn(client, path, action="instrument_no")
    file = upload(client, path, "arbitrario.xlsx", heterogeneous())
    provider.replies = [
        reply(
            response="El libro contiene Medición física (123 registros), Economía 日本 (3), Vacía y Notas no examinables. Las hojas son independientes."
        )
    ]
    assert turn(client, path, action="files_ready").status_code == 200
    context = provider.contexts[0][0]
    summaries = context["files"][0]["workbook_sheets"]
    assert len(summaries) == 4 and context["project_mode"] == mode
    assert summaries[0]["columns"][1]["statistical_type"] == "identifier"
    encoded = json.dumps(context)
    assert '"samples"' not in encoded and '"levels"' not in encoded and '"distribution"' not in encoded
    assert "r-122" not in encoded and len(encoded) < 45000
    assert client.get(path).json()["files"][0]["id"] == file["id"]


def test_global_context_reports_column_omissions_without_dropping_sheets():
    data = workbook({f"Tabla {i}": [[f"columna {j}" for j in range(25)], list(range(25))] for i in range(6)})
    settings = Settings(_env_file=None, gemini_context_chars=14000)
    file = {"id": str(uuid4()), "file_role": "dataset", "metadata": inspect_file("a.xlsx", data, "dataset", settings)}
    context = build_context(
        {"project_type": "general"}, {"current_stage": "understanding"}, [], [file], Turn(request_id=uuid4()), settings
    )
    summaries = context["files"][0]["workbook_sheets"]
    assert len(summaries) == 6 and sum(s.get("columns_omitted", 0) for s in summaries) > 0
    assert all(len(s["columns"]) + s.get("columns_omitted", 0) == 25 for s in summaries)
    assert len(json.dumps(context, ensure_ascii=False)) <= 14000


def test_omitted_workbook_column_remains_available_for_rows_profile_and_later_plan(local):
    client, store, provider = local
    path = new(client, store)
    turn(client, path, action="instrument_no")
    sheet = "Measurements"
    columns = [f"Measurement {j:02d} in standard units" for j in range(1, 47)]
    data = workbook({sheet: [columns, *[[i * 2 + j for j in range(46)] for i in range(32)]]})
    file = upload(client, path, "wide.xlsx", data)
    settings = client.app.state.settings
    settings.gemini_context_chars = 31000
    provider.replies = [reply(response="La hoja contiene mediciones.")]
    result = turn(client, path, action="files_ready")
    assert result.status_code == 200, result.text
    context = provider.contexts[-1][0]
    active = context["files"][0]
    summary = active["workbook_sheets"][0]
    assert summary["columns_omitted"] == 34 and summary["column_count"] == 46
    assert columns[-1] not in [column["name"] for column in summary["columns"]]
    assert [column["name"] for column in active["columns"]] == columns
    base = f"/projects/{store.project_id}/files/{file['id']}"
    assert [column["name"] for column in client.get(base + "/profile").json()["profile"]["columns"]] == columns
    assert client.get(base + "/rows?limit=1").json()["columns"] == columns
    provider.replies = [reply(proposals=[descriptive(file["id"], sheet, columns[-1])])]
    result = turn(client, path, content=f"Prepara una propuesta descriptiva de `{columns[-1]}`. No ejecutes cálculos.")
    assert result.status_code == 200, result.text
    proposal = client.get(path).json()["proposals"][0]
    assert proposal["analysis_plan"]["variables"][0]["column"] == columns[-1]
    assert client.patch(path + "/proposals/" + proposal["id"], json={"status": "accepted"}).status_code == 200


@pytest.mark.parametrize("legacy", [False, True])
def test_visual_navigation_profile_permissions_and_historical_selection(local, legacy):
    client, store, provider = local
    path = new(client, store)
    turn(client, path, action="instrument_no")
    original = heterogeneous()
    file = upload(client, path, "arbitrario.xlsx", original)
    base = f"/projects/{store.project_id}/files/{file['id']}"
    assert client.put(base + "/sheet", json={"title": "Medición física"}).status_code == 200
    provider.replies = [reply(proposals=[descriptive(file["id"], "Medición física", "presión kPa")])]
    assert turn(client, path, content="Quiero una descriptiva de `presión kPa`.").status_code == 200
    pid = client.get(path).json()["proposals"][0]["id"]
    assert client.patch(path + "/proposals/" + pid, json={"status": "accepted"}).status_code == 200
    stored = next(f for f in store.data["project_files"] if f["id"] == file["id"])
    stored["metadata"]["historical_extra"] = {"keep": True}
    if legacy:
        stored["metadata"].pop("sheet_profiles")
        stored["metadata"].pop("workbook_profile_version")
    snapshot = copy.deepcopy(store.data)
    pages = [client.get(base + "/rows", params={"sheet": "Medición física", "offset": n}).json() for n in (0, 50, 100)]
    assert sum(len(p["rows"]) for p in pages) == 123 and not pages[-1]["has_more"]
    other = client.get(base + "/rows", params={"sheet": "Economía 日本"})
    assert other.status_code == 200 and other.json()["total_rows"] == 3
    assert other.json()["columns"] == ["sector", "importe", "fecha"]
    assert other.json()["rows"][1][1] is None
    assert client.get(base + "/rows").json()["sheet"] == "Medición física"
    downloads = store.download_count
    meta = client.get(base + "/profile", params={"sheet": "Economía 日本"})
    assert meta.status_code == 200 and meta.json()["profile"]["column_count"] == 3
    assert meta.headers["cache-control"] == "no-store"
    assert store.download_count == downloads + int(legacy)
    assert client.get(base + "/profile").json()["profile"] == stored["metadata"]["profile"]
    assert client.put(base + "/sheet", json={"title": "Economía 日本"}).status_code == 409
    for endpoint in ("/rows", "/profile"):
        assert client.get(base + endpoint, params={"sheet": "No existe"}).status_code == 422
    assert client.get(base + "/profile", params={"sheet": "Vacía"}).status_code == 422
    assert client.get(base + "/download").content == original
    assert store.data == snapshot and len(provider.contexts) == 1
    assert client.get(base.replace(store.project_id, str(uuid4())) + "/profile").status_code == 404
    store.data["projects"][0]["user_id"] = str(uuid4())
    downloads = store.download_count
    for endpoint in ("/rows", "/profile", "/download"):
        assert client.get(base + endpoint, params={"sheet": "Economía 日本"}).status_code == 404
    assert store.download_count == downloads


def test_unselected_book_can_be_explored_without_changing_analysis_reference(local):
    client, store, _ = local
    file = upload(client, new(client, store), "arbitrario.xlsx", heterogeneous())
    base = f"/projects/{store.project_id}/files/{file['id']}"
    assert client.get(base + "/rows", params={"sheet": "Economía 日本"}).status_code == 200
    assert client.get(base + "/profile").json()["selected_sheet"] is None
    plan = Plan.model_validate(descriptive(file["id"], "Economía 日本", "importe"))
    with pytest.raises(ValueError, match="no seleccionada"):
        validate_plan(plan, [file], {"project_type": "general"})


@pytest.mark.parametrize("structure", ["rows", "columns", "sheets", "cell", "aggregate", "expanded", "bytes"])
def test_limits_reject_or_report_without_blocking_valid_sheets(structure):
    settings = Settings(_env_file=None, max_rows=3, max_columns=2)
    tables = {"Válida": [["x"], [1]], "Exceso": [["x"], [1], [2], [3], [4]]}
    if structure == "columns":
        tables["Exceso"] = [["a", "b", "c"], [1, 2, 3]]
    elif structure == "cell":
        tables["Exceso"] = [["x"], ["a" * 2001]]
    elif structure == "sheets":
        tables = {str(i): [["x"], [1]] for i in range(31)}
    elif structure == "aggregate":
        tables = {str(i): [["x", "y"], [1, 2], [3, 4], [5, 6]] for i in range(3)}
    elif structure == "expanded":
        settings = settings.model_copy(update={"max_expanded_bytes": 1024})
    elif structure == "bytes":
        settings = settings.model_copy(update={"max_file_bytes": 1024})
    data = workbook(tables)
    if structure in {"sheets", "expanded", "bytes"}:
        with pytest.raises(HTTPException):
            inspect_file("l.xlsx", data, "dataset", settings)
    else:
        meta = inspect_file("l.xlsx", data, "dataset", settings)
        assert meta["sheet_profiles"][0]["status"] == "available"
        assert meta["sheet_profiles"][1]["status"] == "unavailable"
        assert meta["sheet_profiles"][1]["warnings"]


@pytest.mark.parametrize("extension", ["xlsx", "csv", "json"])
@pytest.mark.parametrize("column", ["sepal_length_cm", "presión kPa α"])
def test_six_products_generate_and_accept_without_correction_at_one_request_budget(local, extension, column):
    client, store, provider = local
    path = new(client, store)
    turn(client, path, action="instrument_no")
    values = IRIS_LENGTHS["Setosa"]
    data = (
        workbook({name: [[column], *[[v] for v in rows]] for name, rows in IRIS_LENGTHS.items()})
        if extension == "xlsx"
        else (column + "\n" + "\n".join(map(str, values))).encode()
        if extension == "csv"
        else json.dumps([{column: v} for v in values]).encode()
    )
    file = upload(client, path, f"referencia.{extension}", data)
    sheet = "Setosa" if extension == "xlsx" else "tabla"
    if extension == "xlsx":
        file = client.put(f"/projects/{store.project_id}/files/{file['id']}/sheet", json={"title": sheet}).json()
    request = f"Quiero estadística descriptiva univariada de `{column}` en la hoja {sheet}: N válido, media, mediana, DE muestral, mínimo y máximo. Sin comparaciones entre grupos, inferencia ni correlaciones."
    scope = requested_scope({}, [], Turn(request_id=uuid4(), content=request))
    assert not scope["unresolved"]
    proposed = descriptive(file["id"], sheet, column)
    validate_plan_scope(Plan.model_validate(proposed), scope, [file])
    budget = RequestBudget(Settings(_env_file=None, ai_max_requests_per_turn=1))
    original_generate = provider.generate

    async def bounded(context, correction=None):
        budget.reserve()
        return await original_generate(context, correction)

    provider.generate = bounded
    provider.replies = [reply(proposals=[proposed], suggested_stage="proposal")]
    response = turn(client, path, content=request)
    assert response.status_code == 200, response.text
    detail = client.get(path).json()
    assert len(provider.contexts) == 1 and provider.contexts[0][1] is None
    assert detail["messages"][-1]["metadata"]["generation"]["requests"] == 1
    assert len(detail["proposals"]) == 1
    pid = detail["proposals"][0]["id"]
    assert client.patch(path + "/proposals/" + pid, json={"status": "accepted"}).status_code == 200
    assert detail["proposals"][0]["analysis_plan"]["expected_outputs"] == list(SUMMARY_STATISTICS.values())
    assert file["metadata"]["profile"]["row_count"] == 50
    assert file["metadata"]["profile"]["columns"][0]["mean"] == pytest.approx(5.006)
    assert stdev(values) == pytest.approx(0.3524896872)
    if extension == "xlsx" and column == "sepal_length_cm":
        assert turn(client, path, action="prepare_execution", proposal_id=pid).status_code == 200
        preparation = client.get(path).json()["conversation"]["stage_data"]["execution_preparation"]["result"]
        assert preparation["status"] == "READY", preparation
        result = client.post(
            path + "/proposals/" + pid + "/runs",
            json={
                "request_id": preparation["request_id"],
                "specification": {**preparation["specification"], "decisions_confirmed": True},
                "preparation_fingerprint": preparation["fingerprint"],
            },
        )
        assert result.status_code == 200 and result.json()["status"] == "completed", result.text
        calculated = result.json()["result"]["components"][0]["tables"][0]["rows"][0]
        assert calculated["N válido"] == 50
        assert calculated["Media"] == pytest.approx(5.006)
        assert calculated["DE muestral"] == pytest.approx(0.3524896872)
        historical = copy.deepcopy(store.data["analysis_runs"])
        base = f"/projects/{store.project_id}/files/{file['id']}"
        for name, expected in [("Versicolor", 5.936), ("Virginica", 6.588)]:
            assert client.get(base + "/rows", params={"sheet": name}).json()["total_rows"] == 50
            profile = client.get(base + "/profile", params={"sheet": name}).json()["profile"]
            assert profile["columns"][0]["mean"] == pytest.approx(expected)
        assert store.data["analysis_runs"] == historical
        assert client.get(base + "/profile").json()["selected_sheet"] == "Setosa"
        assert len(provider.contexts) == 1


def test_iris_three_reference_sheets_counts_and_means():
    data = workbook({name: [["sepal_length_cm"], *[[v] for v in values]] for name, values in IRIS_LENGTHS.items()})
    meta = inspect_file("referencia.xlsx", data, "dataset", Settings(_env_file=None))
    for entry, expected in zip(meta["sheet_profiles"], [5.006, 5.936, 6.588]):
        assert entry["profile"]["row_count"] == 50
        assert entry["profile"]["columns"][0]["mean"] == pytest.approx(expected)
        assert mean(IRIS_LENGTHS[entry["sheet"]]) == pytest.approx(expected)


def test_named_statistics_do_not_turn_prepositions_into_products_or_allow_categorical_means():
    assert product_request("Quiero conocer las características de los datos")[0] == set()
    assert "sample_sd" in product_request("Media, mediana, DE, mínimo y máximo")[0]
    file = {
        "id": str(uuid4()),
        "file_role": "dataset",
        "metadata": inspect_file("x.csv", b"region\nA\nB", "dataset", Settings(_env_file=None)),
    }
    with pytest.raises(ValueError, match="cuantitativo"):
        validate_plan(
            Plan.model_validate(descriptive(file["id"], "tabla", "region")), [file], {"project_type": "general"}
        )
