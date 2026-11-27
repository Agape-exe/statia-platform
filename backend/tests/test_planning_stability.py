"""Regresiones de planificación por HTTP con proveedores controlados."""

import copy
import io
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from openpyxl import Workbook
from scipy import stats
from test_chat_api import new, reply, turn
from test_planning import welch_plan
from test_provider_selection import select, terra
from test_session6 import local as local
from test_session6 import upload
from test_thesis_stability import thesis_context

REQUEST = (
    "Genera una propuesta para una prueba t de Welch bilateral que compare la media de medicion "
    "entre los grupos A y B de grupo. Son dos grupos independientes, sin pares ni repeticiones. "
    "Cada fila es una observación independiente, medicion es cuantitativa continua y las varianzas "
    "pueden ser distintas. Usa todos los casos completos y realiza un único contraste."
)
CONFIRMATION = (
    "Confirmo alcance: genera una propuesta de t de Welch bilateral para medicion por grupo A y B, "
    "con valor p y medias por grupo. Diseño de grupos independientes sin pares ni repeticiones. "
    "Medicion cuantitativa continua. Casos completos, varianzas distintas y un único contraste."
)
ANNOUNCEMENT = (
    "He estructurado formalmente la propuesta solicitada para realizar una prueba t de Welch bilateral. "
    "Por favor, revísala y confírmala en tu tarjeta correspondiente."
)
VALUES = {"A": [11.5, 13, 14, 15, 16, 18, 19, 21.5], "B": [12, 18, 21, 24, 27, 29, 33, 37, 39, 52]}
CSV = ("grupo,medicion\n" + "".join(f"{g},{value}\n" for g, values in VALUES.items() for value in values)).encode()


def upload_welch(local, csv=CSV, name="contraste.csv"):
    client, store, _ = local
    path = new(client, store)
    assert turn(client, path, action="instrument_no").status_code == 200
    return path, upload(client, path, name, csv)


def welch_proposal(file, outcome="medicion", group="grupo", groups=("A", "B")):
    plan = welch_plan()
    measure = {"file_id": file["id"], "sheet": file["metadata"]["selected_sheet"], "column": outcome, "role": "outcome"}
    plan.update(
        title="Comparación de medias",
        objective=f"Comparar `{outcome}` entre las categorías de `{group}`",
        method="t de Welch bilateral",
        variables=[measure, {**measure, "column": group, "role": "group"}],
        expected_outputs=["Valores p", "Medias por grupo"],
        methodology_confirmed=True,
    )
    plan["comparison"].update(
        groups=list(groups),
        filters=[],
        independence="Verificar la independencia según el diseño informado.",
        multiplicity_reason="Un único contraste bilateral preespecificado.",
    )
    return plan


def test_original_welch_request_reaches_provider_and_persists_card(local):
    client, _, provider = local
    path, file = upload_welch(local)
    provider.replies.append(reply(proposals=[welch_proposal(file)], suggested_stage="proposal"))
    response = turn(client, path, content=REQUEST)
    assert response.status_code == 200, response.text
    detail = client.get(path).json()
    assert len(provider.contexts) == 1, detail["messages"][-1]["content"]
    assert detail["conversation"]["current_stage"] == "proposal"
    assert detail["proposals"][0]["source_message_id"] == detail["messages"][-1]["id"]


def test_follow_up_explains_pending_question_without_inventing_card(local):
    client, _, provider = local
    path, _ = upload_welch(local)
    provider.replies.append(reply(clarification_required=True, questions=["¿Las mediciones están pareadas?"]))
    assert turn(client, path, content="Genera un plan para comparar los grupos").status_code == 200
    provider.replies.append(reply(response=ANNOUNCEMENT))
    response = turn(client, path, content="Que necesitas, no entiendo?")
    assert response.status_code == 200, response.text
    detail = client.get(path).json()
    assert not detail["proposals"] and detail["conversation"]["current_stage"] == "clarification"
    assert detail["messages"][-1]["metadata"]["questions"] == ["¿Las mediciones están pareadas?"]
    assert len(provider.contexts) == 1


def test_redundant_component_with_reordered_variables_is_equivalent(local):
    client, _, provider = local
    path, file = upload_welch(local)
    plan = welch_proposal(file)
    plan["components"] = [
        {"procedure": plan["procedure"], "method": plan["method"], "variables": plan["variables"][::-1]}
    ]
    provider.replies.extend([reply(proposals=[plan])] * 2)
    response = turn(client, path, content=CONFIRMATION.replace("Casos completos, ", ""))
    assert response.status_code == 200, (response.text, dict(response.headers))
    assert len(provider.contexts) == 1
    assert not client.get(path).json()["proposals"][0]["analysis_plan"]["components"]


@pytest.mark.parametrize("problem", ["role", "column", "method"])
def test_non_equivalent_component_returns_structural_diagnostic_without_persisting(local, problem):
    client, store, provider = local
    path, file = upload_welch(local)
    plan = welch_proposal(file)
    component = {"procedure": plan["procedure"], "method": plan["method"], "variables": plan["variables"][:]}
    if problem == "role":
        component["variables"][0] = {**component["variables"][0], "role": "predictor"}
    elif problem == "column":
        component["variables"][0] = {**component["variables"][0], "column": "desconocida"}
    else:
        component["method"] = "t de Student"
    plan["components"] = [component]
    provider.replies.extend([reply(proposals=[plan])] * 2)
    response = turn(client, path, content=REQUEST)
    assert response.status_code == 502 and response.headers["X-Statia-Error"] == "planning_validation"
    assert response.headers["X-Statia-Validation"] == "component_variables"
    assert len(provider.contexts) == 2 and not store.data["analysis_proposals"]
    assert client.get(path).json()["retry_turn"]


@pytest.mark.parametrize(
    "bogus",
    [
        reply(response=ANNOUNCEMENT),
        reply(response="Ya tienes disponible el plan de análisis."),
        reply(response="Para continuar, acéptala desde su tarjeta."),
        reply(response="Procede con la revisión.", suggested_stage="proposal"),
        reply(response="Puedes continuar.", confirmation_required=True),
    ],
)
def test_unbacked_card_announcements_get_one_correction_and_never_persist(local, bogus):
    client, store, provider = local
    path, _ = upload_welch(local)
    provider.replies.extend([bogus, bogus])
    response = turn(client, path, content="¿Qué es una prueba de Welch?")
    assert response.status_code == 502 and response.headers["X-Statia-Error"] == "response_validation"
    assert response.headers["X-Statia-Validation"] == "proposal_missing"
    assert len(provider.contexts) == 2 and not store.data["analysis_proposals"]
    assert all(m["content"] != bogus["response"] for m in client.get(path).json()["messages"])


def test_methodology_question_preserves_pending_scope_and_accepts_corrected_explanation(local):
    client, _, provider = local
    path, _ = upload_welch(local)
    provider.replies.append(reply(clarification_required=True, questions=["¿Cuáles son los dos grupos?"]))
    assert turn(client, path, content="Genera un plan con t de Welch.").status_code == 200
    scope = client.get(path).json()["conversation"]["stage_data"]["requested_scope"]
    explanation = "Welch compara medias de grupos independientes y permite varianzas distintas."
    provider.replies.extend([reply(response=ANNOUNCEMENT), reply(response=explanation)])
    assert turn(client, path, content="¿Cómo funciona la prueba de Welch?").status_code == 200
    detail = client.get(path).json()
    assert detail["conversation"]["current_stage"] == "clarification"
    assert detail["conversation"]["stage_data"]["requested_scope"] == scope
    assert "requested_scope" not in provider.contexts[-1][0]
    assert detail["messages"][-1]["content"] == explanation and not detail["proposals"]


def test_old_false_scope_is_recovered_from_saved_user_turn_without_rewriting_history(local):
    client, store, provider = local
    path, file = upload_welch(local)
    conversation = store.data["conversations"][0]
    request_id = str(uuid4())
    message = {
        "id": str(uuid4()),
        "conversation_id": conversation["id"],
        "role": "user",
        "content": REQUEST,
        "message_type": "text",
        "metadata": {"request_id": request_id},
        "position": len(store.data["messages"]),
    }
    store.data["messages"].append(message)
    store.data["messages"].append(
        {
            "id": str(uuid4()),
            "conversation_id": conversation["id"],
            "role": "assistant",
            "content": "Siguen pendientes los productos solicitados: Media.",
            "message_type": "question",
            "metadata": {"clarification_required": True, "questions": ["¿Qué otros productos necesitas?"]},
            "position": message["position"] + 1,
        }
    )
    conversation["current_stage"] = "clarification"
    conversation["stage_data"]["requested_scope"] = {
        "version": 1,
        "recognizer_version": 6,
        "products": ["mean"],
        "unresolved": True,
        "mode": "analysis",
        "source_requests": [request_id],
        "through_position": message["position"],
    }
    assert turn(client, path, content="¿Qué debo aclarar?").status_code == 200
    last = client.get(path).json()["messages"][-1]
    assert last["metadata"]["questions"] == ["Puedes volver a pedir la propuesta con el alcance que ya indicaste."]
    assert not provider.contexts
    provider.replies.append(reply(proposals=[welch_proposal(file)]))
    assert turn(client, path, content=CONFIRMATION).status_code == 200
    detail = client.get(path).json()
    assert len(provider.contexts) == 1 and len(detail["proposals"]) == 1
    scope = detail["conversation"]["stage_data"]["requested_scope"]
    assert scope["products"] == ["group_means", "p_value"] and not scope["unresolved"]
    assert scope["required_methods"] == ["welch_t"]
    assert next(m for m in detail["messages"] if m["id"] == message["id"]) == message


@pytest.mark.parametrize("grouped", [False, True])
def test_descriptive_means_stay_bound_to_the_requested_grouping(local, grouped):
    client, _, provider = local
    path, file = upload_welch(local)
    plan = welch_proposal(file)
    plan.update(procedure="descriptive", method="Descriptivos", comparison=None, expected_outputs=["Tabla descriptiva"])
    if not grouped:
        plan.update(objective="Describir `medicion`", variables=plan["variables"][:1], expected_outputs=["Media"])
    user_request = (
        "Quiero un plan con la media de medicion por `grupo`."
        if grouped
        else "Quiero un plan con la media global de medicion."
    )
    provider.replies.append(reply(proposals=[plan]))
    response = turn(client, path, content=user_request)
    assert response.status_code == 200, response.text
    assert len(client.get(path).json()["proposals"]) == 1
    scope = provider.contexts[0][0]["requested_scope"]
    assert scope["products"] == (["group_means"] if grouped else ["mean"])
    assert not scope.get("required_methods")


def test_reformulation_preserves_method_exclusion_and_required_products(local):
    client, _, provider = local
    path, file = upload_welch(local)
    welch = welch_proposal(file)
    student = copy.deepcopy(welch)
    student["method"] = "t de Student"
    student["comparison"]["variance_assumption"] = "equal_required"
    original_request = "Quiero un plan para comparar las medias con t de Welch en lugar de t de Student, con valor p y medias por grupo."
    provider.replies.append(reply(proposals=[welch]))
    assert turn(client, path, content=original_request).status_code == 200
    before = client.get(path).json()["proposals"][0]
    assert client.patch(f"{path}/proposals/{before['id']}", json={"status": "rejected"}).status_code == 200
    incomplete = {**welch, "expected_outputs": ["Medias por grupo"]}
    provider.replies.extend([reply(proposals=[student]), reply(proposals=[incomplete])])
    assert turn(client, path, content="Reformula el plan conservando el alcance.").status_code == 200
    detail = client.get(path).json()
    assert [p["status"] for p in detail["proposals"]] == ["rejected"]
    assert "método excluido" in provider.contexts[-1][1]
    assert (
        detail["messages"][-1]["metadata"]["planning_validation"]["attempts"][1]["issues"][0]["category"]
        == "requested_scope"
    )
    provider.replies.append(reply(proposals=[welch]))
    assert turn(client, path, content="Continúa con el mismo análisis.").status_code == 200
    assert {p["status"] for p in client.get(path).json()["proposals"]} == {"rejected", "proposed"}


def test_other_inferential_method_is_not_replaced_by_matching_outputs(local):
    client, _, provider = local
    path, file = upload_welch(local)
    rank = {
        **welch_proposal(file),
        "method": "U de Mann–Whitney",
        "comparison": None,
        "expected_outputs": ["Valores p"],
    }
    provider.replies.extend([reply(proposals=[welch_proposal(file)]), reply(proposals=[rank])])
    response = turn(
        client, path, content="Genera un plan con Mann–Whitney para comparar medicion según grupo y reporta el valor p."
    )
    assert response.status_code == 200, response.text
    assert "mann_whitney" in provider.contexts[0][0]["requested_scope"]["required_methods"]
    assert "Mann–Whitney" in provider.contexts[1][1]
    assert client.get(path).json()["proposals"][0]["analysis_plan"]["method"] == "U de Mann–Whitney"


def test_welch_rejects_groups_that_do_not_exist_in_the_profile(local):
    client, store, provider = local
    path, file = upload_welch(local)
    invalid = welch_proposal(file, groups=("A", "C"))
    provider.replies.extend([reply(proposals=[invalid])] * 2)
    response = turn(client, path, content=REQUEST)
    assert response.status_code == 502 and response.headers["X-Statia-Validation"] == "comparison_scope"
    assert not store.data["analysis_proposals"]


def finish_welch(client, store, path, expected_request):
    detail = client.get(path).json()
    assert detail["conversation"]["current_stage"] == "proposal"
    proposal = next(p for p in detail["proposals"] if p["status"] == "proposed")
    message = next(m for m in detail["messages"] if m["id"] == proposal["source_message_id"])
    assert message["message_type"] == "proposal"
    assert message["metadata"]["requested_scope"]["required_methods"] == ["welch_t"]
    assert any(m["content"] == expected_request for m in detail["messages"])
    endpoint = f"{path}/proposals/{proposal['id']}"
    assert not store.data["analysis_runs"]
    assert client.patch(endpoint, json={"status": "accepted"}).status_code == 200
    assert client.get(path).json()["conversation"]["current_stage"] == "ready"
    response = turn(client, path, action="prepare_execution", proposal_id=proposal["id"])
    assert response.status_code == 200, response.text
    for _ in range(4):
        prep = client.get(path).json()["conversation"]["stage_data"]["execution_preparation"]["result"]
        if prep["status"] == "READY":
            break
        question = prep["questions"][0]
        values = {option["value"] for option in question["choices"]}
        answer = "yes" if "yes" in values else "none"
        assert (
            turn(client, path, action="clarify_execution", question_id=question["id"], answer=answer).status_code == 200
        )
    assert prep["status"] == "READY", prep
    assert prep["specification"]["components"][0]["method"] == "welch_t"
    payload = {
        "request_id": prep["request_id"],
        "preparation_fingerprint": prep["fingerprint"],
        "specification": prep["specification"],
    }
    assert client.post(endpoint + "/runs", json=payload).status_code in (409, 422)
    assert not store.data["analysis_runs"]
    payload["specification"]["decisions_confirmed"] = True
    response = client.post(endpoint + "/runs", json=payload)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "completed" and run["artifacts"]
    assert client.post(endpoint + "/runs", json=payload).json()["id"] == run["id"]
    return run["result"]["components"][0]


def test_original_csv_full_welch_flow(local):
    original_path = os.environ.get("STATIA_WELCH_CSV")
    if not original_path:
        pytest.skip("La evidencia privada de E2E-05 se proporciona con STATIA_WELCH_CSV.")
    client, store, provider = local
    original_path = Path(original_path)
    original = original_path.read_bytes()
    path, file = upload_welch(local, original, original_path.name)
    provider.replies.append(reply(proposals=[welch_proposal(file)]))
    response = turn(client, path, content=REQUEST)
    assert response.status_code == 200, response.text
    assert len(provider.contexts) == 1
    component = finish_welch(client, store, path, REQUEST)
    assert [g["n"] for g in component["sample"]["groups"]] == [8, 10]
    summary = next(table for table in component["tables"] if table["title"].startswith("Resumen por grupos"))
    assert [row["Media"] for row in summary["rows"]] == pytest.approx([16, 31.5])
    expected = {"difference": -15.5, "t": -2.9866219081519167, "df": 10.362546464549375, "p": 0.013153584070293232}
    assert {key: component["statistics"][key] for key in expected} == pytest.approx(expected, rel=1e-12)
    assert store.objects[file["storage_path"]] == original


def test_welch_allows_explicit_degrees_of_freedom_and_available_cases(local):
    client, _, provider = local
    path, file = upload_welch(local)
    plan = welch_proposal(file)
    plan["expected_outputs"].append("Grados de libertad del contraste")
    provider.replies.append(reply(proposals=[plan]))
    response = turn(
        client,
        path,
        content="Prepara un plan para una t de Welch que contraste el promedio de `medicion` según `grupo`. "
        "Usa los casos disponibles sin imputar. Reporta valor p y grados de libertad.",
    )
    assert response.status_code == 200, response.text
    assert len(client.get(path).json()["proposals"]) == 1
    assert provider.contexts[0][0]["requested_scope"]["products"] == ["degrees_of_freedom", "p_value"]


@pytest.mark.parametrize("extension,provider_id", [("json", "gemini"), ("xlsx", "openai")])
def test_thesis_reuse_and_multiturn_welch_with_other_names(local, extension, provider_id):
    client, store, provider = local
    thesis_context(store, 1)
    original_context = copy.deepcopy(store.data["research_contexts"])
    rows = [(label, value) for label, values in zip(("Norte", "Sur"), VALUES.values()) for value in values]
    if extension == "json":
        original = json.dumps([{"zona": group, "temperatura": value} for group, value in rows]).encode()
    else:
        book = Workbook()
        book.active.title = "Observaciones"
        book.active.append(["zona", "temperatura"])
        for row in rows:
            book.active.append(row)
        stream = io.BytesIO()
        book.save(stream)
        original = stream.getvalue()
    initial = new(client, store)
    turn(client, initial, action="instrument_no")
    file = upload(client, initial, f"datos.{extension}", original)
    path = new(client, store)
    assert turn(client, path, action="reuse", file_ids=[file["id"]]).status_code == 200
    assert turn(client, path, content="No").status_code == 200
    request = "Prepara un plan para contrastar el promedio de temperatura entre Norte y Sur según zona mediante Welch bilateral."
    confirmation = "Cada fila corresponde a una unidad independiente, sin parejas. Usa filas completas y reporta valor p y medias por grupo."
    responses = [
        reply(clarification_required=True, questions=["¿Qué diseño y política de ausencias usaste?"]),
        reply(proposals=[welch_proposal(file, "temperatura", "zona", ("Norte", "Sur"))]),
    ]
    if provider_id == "openai":
        calls = terra(client, responses)
        assert select(client, path, provider_id).status_code == 200
    else:
        provider.replies.extend(responses)
        calls = provider.contexts
    assert turn(client, path, content=request).status_code == 200
    assert client.get(path).json()["conversation"]["current_stage"] == "clarification"
    assert turn(client, path, content=confirmation).status_code == 200
    component = finish_welch(client, store, path, confirmation)
    expected = stats.ttest_ind(*VALUES.values(), equal_var=False)
    assert component["statistics"]["t"] == pytest.approx(expected.statistic)
    assert component["statistics"]["df"] == pytest.approx(expected.df)
    assert component["statistics"]["p"] == pytest.approx(expected.pvalue)
    assert len(calls) == 2 and store.objects[file["storage_path"]] == original
    contexts = [json.loads(call["input"]) if provider_id == "openai" else call[0] for call in calls]
    assert all(context["research_context"]["revision"] == 1 for context in contexts)
    assert store.data["research_contexts"] == original_context
