"""Proveedores adversariales: el usuario conserva el control del alcance y del UUID."""

import copy
from uuid import uuid4

import pytest
import test_chat_api
from test_chat_api import attach_dataset, new, plan, reply, turn
from test_provider_selection import select, terra

api = test_chat_api.api
REQUEST = (
    "Solicito en un mismo análisis: Resúmenes globales; Resúmenes por grupo; Frecuencias de la variable de agrupación."
)


def proposals(fid):
    invalid = plan(fid)
    measure = invalid["variables"][0]
    group = {**measure, "column": "grupo", "role": "group"}
    invalid["variables"].append(group)
    invalid["objective"] = "Describir `nota` por `grupo`"
    invalid["expected_outputs"] = [
        "Resúmenes globales",
        "Resúmenes por grupo",
        "Frecuencias de la variable de agrupación",
    ]
    reduced = copy.deepcopy(invalid)
    reduced["expected_outputs"] = ["Resúmenes por grupo"]
    complete = copy.deepcopy(invalid)
    complete.update(
        procedure="integral",
        method="Describir `nota` globalmente y por `grupo`, y frecuencias de `grupo`",
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
    return invalid, reduced, complete


def setup(api, provider_id, responses):
    client, store, gemini = api
    path = new(client, store)
    turn(client, path, action="instrument_no")
    fid = attach_dataset(client, path)
    generated = responses(fid)
    if provider_id == "openai":
        calls = terra(client, generated)
        assert select(client, path, "openai").status_code == 200
    else:
        gemini.replies = generated
        calls = gemini.contexts
    return client, store, path, fid, calls


@pytest.mark.parametrize("provider_id", ["gemini", "openai"])
@pytest.mark.parametrize("second", ["reduced", "substituted", "no_plan", "split"])
def test_explicit_products_cannot_disappear_even_in_a_valid_second_reply(api, provider_id, second):
    def answers(fid):
        invalid, reduced, complete = proposals(fid)
        final = reply(response="Todo resuelto", proposals=[reduced])
        if second == "substituted":
            final["proposals"][0]["expected_outputs"] = ["Tabla descriptiva"]
        elif second == "no_plan":
            final = reply(response="Todo resuelto", suggested_stage="proposal")
        elif second == "split":
            final["proposals"] = []
            for component, output in zip(complete["components"], complete["expected_outputs"]):
                item = {
                    **plan(fid),
                    "variables": component["variables"],
                    "method": component["method"],
                    "objective": component["method"],
                    "expected_outputs": [output],
                }
                final["proposals"].append(item)
        return [reply(proposals=[invalid]), final]

    client, store, path, _, calls = setup(api, provider_id, answers)
    request_id = str(uuid4())
    response = turn(client, path, content=REQUEST, request_id=request_id)
    assert response.status_code == 200, response.text
    detail = client.get(path).json()
    assert not detail["proposals"]
    assert detail["conversation"]["current_stage"] == "clarification"
    assert detail["messages"][-1]["metadata"]["clarification_required"]
    assert detail["messages"][-1]["metadata"]["questions"]
    assert len(calls) == 2
    before = copy.deepcopy(store.data)
    replay = turn(client, path, content=REQUEST, request_id=request_id)
    assert replay.status_code == 200 and replay.json()["replayed"]
    assert store.data == before and len(calls) == 2


@pytest.mark.parametrize("provider_id", ["gemini", "openai"])
def test_valid_correction_conserves_all_products_and_existing_history(api, provider_id):
    client, store, path, fid, calls = setup(
        api, provider_id, lambda fid: [reply(proposals=[proposals(fid)[0]]), reply(proposals=[proposals(fid)[2]])]
    )
    history = copy.deepcopy(store.data["messages"])
    assert turn(client, path, content=REQUEST).status_code == 200
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 1 and len(calls) == 2
    assert detail["proposals"][0]["analysis_plan"]["expected_outputs"] == proposals(fid)[2]["expected_outputs"]
    assert store.data["messages"][: len(history)] == history


@pytest.mark.parametrize("provider_id", ["gemini", "openai"])
def test_ambiguous_user_product_requires_explicit_scope_decision(api, provider_id):
    client, _, path, _, calls = setup(api, provider_id, lambda fid: [reply(proposals=[proposals(fid)[1]])])
    assert turn(client, path, content="Quiero resúmenes completos de las notas.").status_code == 200
    detail = client.get(path).json()
    assert not detail["proposals"] and detail["conversation"]["current_stage"] == "clarification"
    # Una respuesta breve no es consentimiento para recortar productos.
    assert turn(client, path, content="Sí").status_code == 200
    assert not client.get(path).json()["proposals"]
    assert turn(client, path, content="Confirmo alcance: Resúmenes por grupo.").status_code == 200
    assert len(client.get(path).json()["proposals"]) == 1 and len(calls) == 1


def test_provider_suggestions_are_not_automatically_user_requirements(api):
    client, _, path, _, calls = setup(
        api, "gemini", lambda fid: [reply(proposals=[proposals(fid)[0]]), reply(proposals=[proposals(fid)[1]])]
    )
    assert turn(client, path, content="Describe las notas por grupo").status_code == 200
    assert len(client.get(path).json()["proposals"]) == 1 and len(calls) == 2


def test_scope_survives_turns_and_essential_questions_cannot_be_salvaged(api):
    client, _, path, _, calls = setup(
        api,
        "gemini",
        lambda fid: [
            reply(proposals=[proposals(fid)[0]]),
            reply(proposals=[proposals(fid)[1]]),
            reply(proposals=[proposals(fid)[1]]),
            reply(proposals=[proposals(fid)[1]]),
        ],
    )
    assert turn(client, path, content=REQUEST).status_code == 200
    assert turn(client, path, content="Continúa").status_code == 200
    assert not client.get(path).json()["proposals"] and len(calls) == 4


def test_retain_valid_plans_cannot_hide_incomplete_single_analysis():
    from app.core.config import Settings
    from app.models.chat import AssistantReply
    from app.services.planning_validation import assess_reply, retain_valid_plans
    from app.services.profiling import inspect_file

    fid = str(uuid4())
    files = [
        {
            "id": fid,
            "file_role": "dataset",
            "metadata": inspect_file("datos.csv", b"nota,grupo\n1,A\n2,B\n", "dataset", Settings(_env_file=None)),
        }
    ]
    response = AssistantReply.model_validate(reply(proposals=[proposals(fid)[1]]))
    context = {
        "requested_scope": {
            "version": 1,
            "products": ["global", "grouped", "group_frequencies"],
            "unresolved": False,
            "mode": "analysis",
        }
    }
    assessed = assess_reply(response, files, {"project_type": "general"}, context)
    assert (
        assessed.issues and retain_valid_plans(response, assessed, files, {"project_type": "general"}, context) is None
    )


@pytest.mark.parametrize("provider_id", ["gemini", "openai"])
def test_four_independent_alternatives_can_retain_two_valid_without_erasing_questions(api, provider_id):
    def answers(fid):
        valid = plan(fid)
        valid["expected_outputs"] = ["Resúmenes globales"]
        invalid = copy.deepcopy(valid)
        invalid["variables"][0]["column"] = "columna_inexistente"
        return [
            reply(
                proposals=[valid, invalid, copy.deepcopy(valid), copy.deepcopy(invalid)],
                questions=["¿Quieres solicitar más alternativas después?"],
            )
            for _ in range(2)
        ]

    client, _, path, _, calls = setup(api, provider_id, answers)
    assert (
        turn(client, path, content="Solicito cuatro alternativas independientes: Resúmenes globales.").status_code
        == 200
    )
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 2 and len(calls) == 2
    message = detail["messages"][-1]
    assert "no completó todas las alternativas" in message["content"]
    assert message["metadata"]["questions"] == ["¿Quieres solicitar más alternativas después?"]
    assert message["metadata"]["planning_validation"]["partial"]


def test_essential_questions_are_never_removed_from_independent_alternatives(api):
    def answers(fid):
        proposed = {**plan(fid), "expected_outputs": ["Resúmenes globales"]}
        return [
            reply(proposals=[proposed], questions=["¿Qué productos deben conservarse?"], clarification_required=True)
            for _ in range(2)
        ]

    client, _, path, _, calls = setup(api, "gemini", answers)
    response = turn(client, path, content="Solicito cuatro alternativas independientes: Resúmenes globales.")
    assert response.status_code == 502
    assert not client.get(path).json()["proposals"] and len(calls) == 2


@pytest.mark.parametrize(
    "text",
    [
        "Quiero resúmenes globales avanzados.",
        "Solicito productos: Resúmenes globales; Predicciones de ventas.",
        "Quiero valores p del componente 1 y coeficientes de correlación del componente 2.",
    ],
)
def test_qualifiers_unknown_products_negations_and_free_bindings_require_decision(text):
    from app.services.requested_scope import user_products

    _, uncertain, mentioned = user_products(text)
    assert mentioned and uncertain


def test_reply_result_revalidates_scope_before_persistence():
    from app.models.chat import AssistantReply
    from app.services.conversation import reply_result
    from app.services.planning_errors import PlanningError

    scope = {
        "version": 1,
        "products": ["global", "grouped", "group_frequencies"],
        "unresolved": False,
        "mode": "analysis",
    }
    with pytest.raises(PlanningError) as exc:
        reply_result(
            AssistantReply.model_validate(reply(proposals=[proposals(str(uuid4()))[1]])),
            {"stage_data": {"requested_scope": scope}},
        )
    assert exc.value.category == "requested_scope"


def test_existing_narrow_proposal_cannot_be_newly_accepted_against_current_scope(api):
    client, store, path, fid, calls = setup(
        api, "gemini", lambda fid: [reply(proposals=[proposals(fid)[0]]), reply(proposals=[proposals(fid)[1]])]
    )
    cid = path.rsplit("/", 1)[1]
    proposal = {
        "id": str(uuid4()),
        "conversation_id": cid,
        "analysis_plan": proposals(fid)[1],
        "status": "proposed",
        "created_at": 0,
    }
    store.data["analysis_proposals"].append(proposal)
    assert turn(client, path, content=REQUEST).status_code == 200
    before = copy.deepcopy(store.data)
    result = client.patch(path + "/proposals/" + proposal["id"], json={"status": "accepted"})
    assert result.status_code == 422 and result.headers["X-Statia-Error"] == "requested_scope"
    assert store.data == before and len(calls) == 2


@pytest.mark.parametrize("provider_id", ["gemini", "openai"])
def test_provider_unknown_output_gets_one_semantic_correction_without_inventing_user_requirements(api, provider_id):
    def answers(fid):
        ambiguous = plan(fid)
        ambiguous["expected_outputs"] = ["Balance detallado de las mediciones"]
        return [reply(proposals=[ambiguous]), reply(proposals=[plan(fid)])]

    client, _, path, _, calls = setup(api, provider_id, answers)
    assert turn(client, path, content="Quiero un balance detallado de las notas").status_code == 200
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 1
    assert "requested_scope" not in detail["conversation"]["stage_data"]
    assert len(calls) == 2
    assert detail["messages"][-1]["metadata"]["planning_validation"]["attempts"][0]["issues"]


def test_truncated_historical_scope_is_not_assumed_complete_and_model_text_is_not_evidence():
    from app.models.chat import Turn
    from app.services.requested_scope import requested_scope

    turn = Turn(request_id=uuid4(), content="Continúa")
    conversation = {"primary_goal": "Resúmenes globales", "stage_data": {"context_summary": "Frecuencias categóricas"}}
    assert requested_scope(conversation, [{"role": "assistant", "content": REQUEST}], turn) is None
    history = [{"role": "user", "content": "Continúa", "metadata": {"turn_action": "message"}} for _ in range(30)]
    assert requested_scope(conversation, history, turn)["unresolved"]
    decision = Turn(request_id=uuid4(), content="Confirmo alcance: Resúmenes por grupo.")
    scope = requested_scope(conversation, history, decision)
    assert not scope["unresolved"] and scope["products"] == ["grouped"]


@pytest.mark.parametrize("provider_id", ["gemini", "openai"])
def test_new_requirement_in_failed_turn_is_recovered_before_a_later_continue(api, provider_id):
    import httpx
    from fastapi import HTTPException

    def answers(fid):
        global_plan = {**plan(fid), "expected_outputs": ["Resúmenes globales"]}
        failure = (
            HTTPException(503, "Fallo sintético")
            if provider_id == "gemini"
            else httpx.Response(400, json={"error": {"code": "invalid_request_error", "message": "Fallo sintético"}})
        )
        return [reply(proposals=[global_plan]), failure, reply(proposals=[global_plan]), reply(proposals=[global_plan])]

    client, _, path, _, calls = setup(api, provider_id, answers)
    assert turn(client, path, content="Solicito Resúmenes globales.").status_code == 200
    original = copy.deepcopy(client.get(path).json()["proposals"])
    assert turn(client, path, content="Solicito Resúmenes por grupo.").status_code >= 500
    assert client.get(path).json()["conversation"]["stage_data"]["requested_scope"]["products"] == ["global"]
    assert turn(client, path, content="Continúa").status_code == 200
    detail = client.get(path).json()
    assert detail["proposals"] == original
    assert detail["conversation"]["current_stage"] == "clarification"
    assert detail["conversation"]["stage_data"]["requested_scope"]["products"] == ["global", "grouped"]
    assert len(calls) == 4
