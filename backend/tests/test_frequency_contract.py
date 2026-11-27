"""Solicitud literal reportada; API y motor reales, proveedor/Auth/Storage simulados."""

import copy
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from test_chat_api import new, reply, turn
from test_conversation_scope import prepare_chat
from test_instruments import pdf
from test_session6 import local as local
from test_session6 import upload
from test_thesis_stability import frequency_plan

from app.models.research_context import ResearchContext
from app.services.reply_contract import parse_assistant_reply
from app.services.requested_scope import (
    SCOPE_RECOGNIZER_VERSION,
    product_request,
    request_clauses,
)

REQUEST = "Ahora sí, prepara una única propuesta estadística descriptiva para la variable sun_reaction del archivo nhanes_dermatology.csv.\n\nUtiliza el Contexto de tesis confirmado y las definiciones verificables del instrumento DEQ_J.pdf.\n\nAlcance: describir todos los registros disponibles, sin filtros, comparaciones ni agrupaciones.\n\nProcedimiento: distribución de frecuencias categóricas.\n\nProducto solicitado: exclusivamente una tabla de frecuencias absolutas y porcentajes por categoría, indicando el denominador utilizado y los valores ausentes.\n\nNo incluir resúmenes globales adicionales, gráficos, otras variables ni pruebas inferenciales.\n\nPresenta la propuesta para revisarla y aceptarla. No ejecutes cálculos todavía y no modifiques el Contexto de tesis."


def reported_workspace(local, mode):
    client, store, _ = local
    if mode == "thesis":
        store.data["projects"][0]["project_type"] = mode
        original_rpc = store.rpc

        async def rpc(name, data):
            if name != "save_research_context":
                return await original_rpc(name, data)
            assert data["p_expected_revision"] == 0
            saved = {
                "project_id": store.project_id,
                "document": data["p_document"],
                "revision": 1,
                "updated_at": "2026-11-23T12:00:00Z",
            }
            store.data["research_contexts"] = [saved]
            return saved

        store.rpc = rpc
        context = ResearchContext(
            general_objective="Describir la exposición solar.", methodological_design="Descriptivo transversal."
        ).model_dump()
        saved = client.put(
            f"/projects/{store.project_id}/research-context",
            json={"document": context, "expected_revision": 0, "confirmed": True},
        )
        assert saved.status_code == 200 and saved.json()["context"]["revision"] == 1
    path = new(client, store)
    assert turn(client, path, action="instrument_yes").status_code == 200
    directory = os.environ.get("STATIA_TEST_INPUT_DIR")
    instrument = (
        (Path(directory) / "DEQ_J.pdf").read_bytes()
        if directory
        else pdf(
            [
                "How does your skin react to sunlight? Categories: Sensitive; Mild.",
            ]
        )
    )
    upload(client, path, "DEQ_J.pdf", instrument, "instrument")
    assert turn(client, path, action="instruments_done").status_code == 200
    data = (
        (Path(directory) / "nhanes_dermatology.csv").read_bytes()
        if directory
        else (
            b"sun_reaction,grupo,a,b,c,d,e,f\n"
            + b"Sensible,A,x,x,x,x,x,x\nLeve,B,x,x,x,x,x,x\n,A,x,x,x,x,x,x\n" * 1139
            + b"Sensible,A,x,x,x,x,x,x\nLeve,B,x,x,x,x,x,x\n"
        )
    )
    file = upload(client, path, "nhanes_dermatology.csv", data)
    assert file["metadata"]["profile"]["row_count"] == 3419
    assert len(file["metadata"]["profile"]["columns"]) == 8
    return path, file


@pytest.mark.parametrize("mode", ["thesis", "general"])
def test_reported_request_reaches_provider_and_creates_one_plan(local, mode):
    client, store, provider = local
    path, file = reported_workspace(local, mode)
    fid = file["id"]
    research = copy.deepcopy(store.data["research_contexts"])
    provider.replies.extend([reply(), reply(), reply(proposals=[frequency_plan(fid, "sun_reaction")])])
    assert turn(client, path, action="files_ready", share_instrument_text=True).status_code == 200
    assert turn(client, path, content="¿Qué contiene mi dataset?", share_instrument_text=True).status_code == 200
    request_id = str(uuid4())
    assert turn(client, path, content=REQUEST, request_id=request_id, share_instrument_text=True).status_code == 200
    detail = client.get(path).json()
    assert len(provider.contexts) == 3, detail["messages"][-1]
    assert len(detail["proposals"]) == 1
    assert not store.data["analysis_runs"]
    context = provider.contexts[-1][0]
    assert (context["research_context"] or {}).get("revision") == (1 if mode == "thesis" else None)
    scope = context["requested_scope"]
    assert scope["products"] == ["frequencies"] and not scope["unresolved"]
    assert set(scope["constraints"]) == {
        "no_filters",
        "no_groups",
        "no_charts",
        "only_selected_variables",
        "only_requested_outputs",
    }
    assert scope["product_sources"] == {"frequencies": [request_id]}
    assert not detail["messages"][-1]["metadata"]["questions"]
    proposal = detail["proposals"][0]
    assert proposal["source_message_id"] == detail["messages"][-1]["id"]
    endpoint = f"{path}/proposals/{proposal['id']}"
    variable = proposal["analysis_plan"]["variables"][0]
    assert variable["column"] == "sun_reaction"
    body = {
        "request_id": str(uuid4()),
        "specification": {
            "decisions_confirmed": True,
            "components": [{"source_index": 0, "method": "descriptive", "descriptive_intervals": False}],
            "decisions": [{"variable": variable, "statistical_type": "nominal"}],
        },
    }
    assert client.post(endpoint + "/runs", json=body).status_code == 409
    assert client.patch(endpoint, json={"status": "accepted"}).status_code == 200
    assert not store.data["analysis_runs"]
    result = client.post(endpoint + "/runs", json=body)
    assert result.status_code == 200, result.text
    run = result.json()
    assert run["status"] == "completed"
    component = run["result"]["components"][0]
    assert not component["charts"] and len(component["tables"]) == 1
    rows = component["tables"][0]["rows"]
    assert {"Categoría", "Frecuencia", "Porcentaje válido", "N válido", "Ausentes"} <= set(
        component["tables"][0]["columns"]
    )
    valid = sum(row["Frecuencia"] for row in rows)
    assert valid + rows[0]["Ausentes"] == 3419
    assert all(row["N válido"] == valid for row in rows)
    assert not any(artifact["mime_type"] == "image/png" for artifact in run["artifacts"])
    assert client.post(endpoint + "/runs", json=body).json()["id"] == run["id"]
    reloaded = client.get(path).json()
    assert reloaded["proposals"][0]["id"] == proposal["id"]
    assert reloaded["proposals"][0]["status"] == "accepted"
    assert len(store.data["analysis_runs"]) == 1 and store.data["research_contexts"] == research
    assert turn(client, path, content=REQUEST, request_id=request_id, share_instrument_text=True).json()["replayed"]
    assert len(provider.contexts) == 3


@pytest.mark.parametrize(
    "case,category",
    [
        ("equivalent", None),
        ("optional_absent", None),
        ("redundant_component", None),
        ("incomplete", "internal_contract"),
        ("wrong_method", "variable_type"),
        ("extra", "requested_scope"),
        ("no_frequency", "requested_scope"),
        ("no_plan", "proposal_missing"),
        ("missing_column", "column_reference"),
        ("unsupported_equivalent", "output_scope"),
    ],
)
def test_nonideal_provider_contracts_are_validated_not_replaced(local, monkeypatch, case, category):
    client, store, provider = local
    path, fid = prepare_chat(local, "thesis")
    plan = frequency_plan(fid, "sun_reaction")
    if case == "equivalent":
        plan["expected_outputs"] = ["Tabla de frecuencias absolutas y porcentajes por categoría"]
    elif case == "optional_absent":
        for key in ("components", "filters", "joins", "comparison", "schema_version"):
            plan.pop(key, None)
    elif case == "redundant_component":
        plan["components"] = [{key: copy.deepcopy(plan[key]) for key in ("procedure", "method", "variables")}]
    elif case == "incomplete":
        del plan["variables"]
    elif case == "wrong_method":
        plan.update(procedure="correlation", method="Pearson de sun_reaction")
    elif case == "extra":
        plan["expected_outputs"].append("Resúmenes globales")
    elif case == "no_frequency":
        plan["expected_outputs"] = ["Resúmenes globales"]
    elif case == "missing_column":
        plan["variables"][0]["column"] = "inexistente"
    elif case == "unsupported_equivalent":
        plan["expected_outputs"] = ["Tabla de frecuencias absolutas y porcentajes por categoría y predicciones"]
    raw = reply(proposals=[] if case == "no_plan" else [plan])

    async def generate(context, correction=None):
        provider.contexts.append((copy.deepcopy(context), correction))
        return parse_assistant_reply(json.dumps(raw), context["interaction_mode"], validate_plans_separately=True)

    monkeypatch.setattr(provider, "generate", generate)
    response = turn(client, path, content=REQUEST)
    detail = client.get(path).json()
    if category is None:
        assert response.status_code == 200, response.text
        assert len(detail["proposals"]) == 1
        assert "Hay una propuesta" in detail["messages"][-1]["content"]
    else:
        assert response.status_code == 502, response.text
        assert category in response.headers["X-Statia-Validation"]
        assert not detail["proposals"] and detail["retry_turn"]
        assert len(provider.contexts) == 2
    assert not store.data["analysis_runs"]


def test_exclusion_lists_preserve_polarity_without_hiding_positive_products():
    yes, no = request_clauses(
        "no incluir resumenes globales, graficos, otras variables ni inferencia. frecuencias categoricas"
    )
    assert "graficos" in " ".join(no) and "frecuencias categoricas" in " ".join(yes)
    products, excluded, unresolved, _ = product_request(REQUEST)
    assert products == {"frequencies"} and "global" in excluded and not unresolved
    assert product_request("Quiero frecuencias categóricas y predicciones completas")[2]
    products, excluded, _, _ = product_request("Sin resúmenes globales, pero quiero frecuencias categóricas")
    assert products == {"frequencies"} and excluded == {"global"}


def test_existing_conversation_replaces_old_unresolved_scope_and_preserves_retry(local):
    client, store, provider = local
    path, fid = prepare_chat(local, "thesis")
    store.data["conversations"][0]["stage_data"]["requested_scope"] = {
        "version": 1,
        "recognizer_version": 5,
        "products": ["global", "frequencies"],
        "unresolved": True,
        "source_requests": [str(uuid4())],
        "through_position": -1,
    }
    invalid = frequency_plan(fid, "sun_reaction")
    invalid["expected_outputs"] = ["Resúmenes globales"]
    provider.replies.extend([reply(proposals=[invalid]), reply(proposals=[invalid])])
    request_id = str(uuid4())
    assert turn(client, path, content=REQUEST, request_id=request_id).status_code == 502
    assert client.get(path).json()["retry_turn"]["request_id"] == request_id
    provider.replies.append(reply(proposals=[frequency_plan(fid, "sun_reaction")]))
    assert turn(client, path, content=REQUEST, request_id=request_id).status_code == 200
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 1
    scope = detail["messages"][-1]["metadata"]["requested_scope"]
    assert scope["source_requests"] == [request_id] and scope["products"] == ["frequencies"]
    assert scope["recognizer_version"] == SCOPE_RECOGNIZER_VERSION and not scope["unresolved"]
    assert len([m for m in detail["messages"] if m["content"] == REQUEST]) == 1


def test_missing_decision_and_denied_document_permission_remain_explicit(local):
    client, store, provider = local
    path, _ = prepare_chat(local, "thesis")
    provider.replies.append(reply(clarification_required=True, questions=["¿Qué variable deseas describir?"]))
    response = turn(client, path, content=REQUEST.replace("sun_reaction", "por indicar"), share_instrument_text=False)
    assert response.status_code == 200
    assert all(not f.get("instrument", {}).get("fragments_shared") for f in provider.contexts[-1][0]["files"])
    assert not client.get(path).json()["proposals"] and not store.data["analysis_runs"]
    count = len(provider.contexts)
    store.data["projects"][0]["user_id"] = str(uuid4())
    assert turn(client, path, content=REQUEST).status_code == 404
    assert len(provider.contexts) == count


def test_redundant_provider_clarification_is_not_a_user_ambiguity(local):
    client, store, provider = local
    path, _ = prepare_chat(local, "thesis")
    wrong = reply(clarification_required=True, questions=["¿Qué producto específico falta definir?"])
    provider.replies.extend([wrong, wrong])
    result = turn(client, path, content=REQUEST)
    assert result.status_code == 502 and "requested_scope" in result.headers["X-Statia-Validation"]
    assert not store.data["analysis_proposals"] and not store.data["analysis_runs"]


def test_persistence_failure_does_not_publish_a_card_and_can_retry(local, monkeypatch):
    from fastapi import HTTPException

    client, store, provider = local
    path, fid = prepare_chat(local, "thesis")
    original = store.rpc
    fail = True

    async def rpc(name, data):
        if fail and name == "finish_chat_turn":
            raise HTTPException(503, "No se pudo guardar la propuesta. Puedes reintentar.")
        return await original(name, data)

    monkeypatch.setattr(store, "rpc", rpc)
    provider.replies.extend([reply(proposals=[frequency_plan(fid, "sun_reaction")]) for _ in range(2)])
    request_id = str(uuid4())
    assert turn(client, path, content=REQUEST, request_id=request_id).status_code == 503
    assert not client.get(path).json()["proposals"]
    fail = False
    assert turn(client, path, content=REQUEST, request_id=request_id).status_code == 200
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 1
    assert len([m for m in detail["messages"] if m["content"] == REQUEST]) == 1


@pytest.mark.parametrize("partial", [False, True])
def test_general_student_dataset_only_advertises_available_card(local, partial):
    client, store, provider = local
    path = new(client, store)
    assert turn(client, path, action="instrument_no").status_code == 200
    directory = os.environ.get("STATIA_TEST_INPUT_DIR")
    data = (
        (Path(directory) / "Student_Depression_Dataset.csv").read_bytes()
        if directory
        else b"Gender,Depression\nFemale,No\nMale,Yes\n"
    )
    file = upload(client, path, "Student_Depression_Dataset.csv", data)
    plans = [frequency_plan(file["id"], "Gender")]
    if partial:
        plans += [frequency_plan(file["id"], "columna_ausente") for _ in range(2)]
    response = reply(
        response="Puedes elegir entre tres alternativas.",
        questions=["¿Cuál de las tres alternativas prefieres?"],
        proposals=plans,
    )
    provider.replies.extend([reply(), response, copy.deepcopy(response)])
    assert turn(client, path, action="files_ready").status_code == 200
    assert (
        turn(
            client,
            path,
            content=("Genera tres alternativas estadísticas" if partial else "Prepara una única propuesta")
            + " de frecuencias categóricas de Gender. No ejecutes.",
        ).status_code
        == 200
    )
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 1 and not store.data["analysis_runs"]
    assert "tres" not in str(detail["messages"][-1]["metadata"]["questions"])
    if partial:
        assert detail["messages"][-1]["metadata"]["planning_validation"]["partial"]
        assert "Se validó una alternativa" in detail["messages"][-1]["content"]
    else:
        assert (
            detail["messages"][-1]["content"]
            == "Hay una propuesta lista para revisar. Puedes aceptar o rechazar cada propuesta en su tarjeta."
        )
        assert not detail["messages"][-1]["metadata"]["questions"]
