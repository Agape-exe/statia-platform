"""Excel y ejecutabilidad descriptiva antes de aceptación. Sin proveedores reales."""

import copy
import io
from statistics import mean
from uuid import uuid4

import pytest
from openpyxl import Workbook
from test_chat_api import new, reply, turn
from test_session6 import local as local
from test_session6 import upload

from app.core.config import Settings
from app.models.chat import Plan
from app.services.gemini import validate_plan
from app.services.profiling import inspect_file


def workbook(multi=False):
    book, out = Workbook(), io.BytesIO()
    book.active.title = "Notas"
    book.active.append(["puntaje"])
    for i in range(45):
        book.active.append([50 + i * 0.73])
    if multi:
        other = book.create_sheet("Otra")
        other.append(["otra"])
        other.append([123])
    book.save(out)
    return out.getvalue()


@pytest.mark.parametrize("mode", ["general", "thesis"])
@pytest.mark.parametrize("kind", ["csv", "xlsx", "multi"])
def test_profile_selection_and_one_understanding_turn(local, mode, kind):
    client, store, provider = local
    store.data["projects"][0]["project_type"] = mode
    path = new(client, store)
    turn(client, path, action="instrument_no")
    original = b"puntaje\n50\n51\n" if kind == "csv" else workbook(kind == "multi")
    file = upload(client, path, "Notas.csv" if kind == "csv" else "Notas.xlsx", original)
    fid = file["id"]
    if kind == "multi":
        assert file["metadata"]["sheets"] == ["Notas", "Otra"]
        assert file["metadata"]["needs_sheet_selection"] and "profile" not in file["metadata"]
        provider.replies = [reply(response="El libro contiene Notas y Otra, con perfiles independientes.")]
        assert turn(client, path, action="files_ready").status_code == 200
        assert len(provider.contexts[0][0]["files"][0]["workbook_sheets"]) == 2
        selected = client.put(f"/projects/{store.project_id}/files/{fid}/sheet", json={"title": "Notas"})
        assert selected.status_code == 200
        file = selected.json()
        assert client.put(f"/projects/{store.project_id}/files/{fid}/sheet", json={"title": "Otra"}).status_code == 409
    assert file["metadata"]["profile"]["row_count"] == (2 if kind == "csv" else 45)
    assert file["metadata"]["profile"]["column_count"] == 1
    assert not file["metadata"]["needs_sheet_selection"]
    provider.replies = [
        reply(response="Comprendí la hoja seleccionada. ¿Qué deseas analizar?", questions=["¿Qué deseas analizar?"])
    ]
    request_id = str(uuid4())
    assert turn(client, path, action="files_ready", request_id=request_id).status_code == 200
    assert turn(client, path, action="files_ready", request_id=request_id).json()["replayed"]
    assert len(provider.contexts) == (2 if kind == "multi" else 1)
    assert provider.contexts[-1][0]["files"][0]["selected_sheet"] == ("tabla" if kind == "csv" else "Notas")
    assert len(client.get(path).json()["files"]) == 1 and original in store.objects.values()


def sales():
    header = "Units_Sold,Price_per_Unit,Revenue,Year,Month,Product,Customer,Customer_Name\n"
    return (
        header
        + "".join(
            f"{i % 45 + 1},{1.15 + i % 35 * 0.7:.2f},{(i % 45 + 1) * (1.15 + i % 35 * 0.7):.2f},{2020 + i % 4},{i % 12 + 1},P{i % 3},C{i % 121},Cliente sintético {i % 121}\n"
            for i in range(4980)
        )
    ).encode()


def descriptive(fid, columns):
    return {
        "title": "Descripción de ventas",
        "objective": "Describir " + ", ".join(columns),
        "variables": [{"file_id": fid, "sheet": "tabla", "column": name, "role": "description"} for name in columns],
        "procedure": "descriptive",
        "method": "Descriptivos de " + ", ".join(columns),
        "justification": "Conocer las ventas",
        "requirements": ["Revisar unidades"],
        "limitations": ["Solo registros observados"],
        "expected_outputs": ["Resúmenes globales"],
        "methodology_confirmed": True,
    }


@pytest.mark.parametrize("columns,reason", [(["Year"], "temporal"), (["Customer"], "100"), (["Customer_Name"], "100")])
def test_known_blockers_rejected_on_generation_and_acceptance(local, columns, reason):
    client, store, provider = local
    path = new(client, store)
    turn(client, path, action="instrument_no")
    file = upload(client, path, "ventas.csv", sales())
    proposed = descriptive(file["id"], columns)
    with pytest.raises(ValueError, match=reason):
        validate_plan(Plan.model_validate(proposed), [file], {"project_type": "general"})
    provider.replies = [reply(proposals=[proposed]), reply(proposals=[proposed])]
    generation = turn(
        client, path, content="Quiero una descripción general estadística para comprender mejor los datos"
    )
    assert generation.status_code == 502 and reason in generation.json()["detail"]
    assert not client.get(path).json()["proposals"]
    # Incluso una propuesta antigua todavía no aceptada se revalida con el perfil.
    pid = str(uuid4())
    stored = {"id": pid, "conversation_id": path.rsplit("/", 1)[1], "status": "proposed", "analysis_plan": proposed}
    store.data["analysis_proposals"].append(stored)
    original = copy.deepcopy(stored)
    response = client.patch(path + "/proposals/" + pid, json={"status": "accepted"})
    assert response.status_code == 422 and reason in response.json()["detail"]
    assert stored == original


def test_explicit_identifier_and_cardinality_boundary():
    settings = Settings(_env_file=None)
    for name, count, rejected in [("categoria", 100, False), ("categoria", 101, True), ("registro_id", 45, True)]:
        fid = str(uuid4())
        data = (name + "\n" + "\n".join(f"Código-{i}" for i in range(count))).encode()
        file = {"id": fid, "file_role": "dataset", "metadata": inspect_file("s.csv", data, "dataset", settings)}
        plan = Plan.model_validate(descriptive(fid, [name]))
        if rejected:
            with pytest.raises(ValueError):
                validate_plan(plan, [file], {"project_type": "general"})
        else:
            validate_plan(plan, [file], {"project_type": "general"})


def test_limited_sales_plan_accepts_prepares_executes_and_discloses_unavailable_scope(local):
    client, store, provider = local
    path = new(client, store)
    turn(client, path, action="instrument_no")
    file = upload(client, path, "ventas.csv", sales())
    invalid = descriptive(
        file["id"], ["Units_Sold", "Price_per_Unit", "Revenue", "Year", "Month", "Product", "Customer", "Customer_Name"]
    )
    provider.replies = [
        reply(proposals=[invalid]),
        reply(
            response="Year es temporal y Customer/Customer_Name superan las 100 categorías. No puedo describirlos con este motor; ¿quieres limitar el plan a las tres medidas de ventas?",
            questions=["¿Deseas limitarlo a Units_Sold, Price_per_Unit y Revenue?"],
            clarification_required=True,
        ),
    ]
    assert (
        turn(
            client, path, content="Quiero una descripción general estadística para comprender mejor los datos"
        ).status_code
        == 200
    )
    assert not client.get(path).json()["proposals"]
    provider.replies = [reply(proposals=[descriptive(file["id"], ["Units_Sold", "Price_per_Unit", "Revenue"])])]
    assert (
        turn(client, path, content="Quiero describir únicamente Units_Sold, Price_per_Unit y Revenue").status_code
        == 200
    )
    pid = client.get(path).json()["proposals"][0]["id"]
    assert client.patch(path + "/proposals/" + pid, json={"status": "accepted"}).status_code == 200
    assert turn(client, path, action="prepare_execution", proposal_id=pid).status_code == 200
    prep = client.get(path).json()["conversation"]["stage_data"]["execution_preparation"]["result"]
    assert prep["status"] == "READY", prep
    response = client.post(
        path + "/proposals/" + pid + "/runs",
        json={
            "request_id": prep["request_id"],
            "specification": {**prep["specification"], "decisions_confirmed": True},
            "preparation_fingerprint": prep["fingerprint"],
        },
    )
    assert response.status_code == 200 and response.json()["status"] == "completed", response.text
    rows = response.json()["result"]["components"][0]["tables"][0]["rows"]
    assert all(row["N válido"] == 4980 for row in rows)
    assert rows[0]["Media"] == pytest.approx(mean(i % 45 + 1 for i in range(4980)))


def test_general_navigation_gets_one_correction_and_never_writes_context(local):
    client, store, provider = local
    path = new(client, store)
    turn(client, path, action="instrument_no")
    upload(client, path, "ventas.csv", sales())
    provider.replies = [
        reply(response="Revisa la propuesta y confírmala en el módulo Contexto."),
        reply(response="Revisa y acepta la propuesta desde esta conversación."),
    ]
    assert turn(client, path, content="¿Dónde confirmo una propuesta?").status_code == 200
    assert len(provider.contexts) == 2 and not store.data["research_contexts"]
    assert "desde esta conversación" in client.get(path).json()["messages"][-1]["content"]
