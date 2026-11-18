"""Regresiones del fallo manual: IA/Auth/Storage simulados, motor y HTTP reales."""

import copy
import io
from uuid import uuid4

import pytest
from openpyxl import Workbook
from test_chat_api import new, reply, turn
from test_provider_selection import select, terra
from test_session6 import CSV, proposal, upload
from test_session6 import local as local
from test_session6 import (
    test_natural_request_accept_prepare_execute_and_saved_interpretation as execute_flow,
)

from app.core.config import Settings
from app.models.chat import Plan, Turn
from app.services.data_preview import preview_rows
from app.services.interpretation_guards import validate_explanation
from app.services.profiling import inspect_file
from app.services.requested_scope import (
    product_request,
    requested_scope,
    validate_plan_scope,
)

WELCH = (
    "Quiero comparar el promedio de `puntaje` entre las categorías A, B y C de la variable `grupo` "
    "mediante un ANOVA de Welch. Confirmo que las observaciones de los tres grupos son independientes "
    "y que `puntaje` es cuantitativa. Necesito N, media y desviación estándar por grupo, F de Welch, "
    "grados de libertad y p global. Sin post hoc ni causalidad. Presenta una única propuesta"
)


def welch(fid, case="welch"):
    plan = proposal(fid, case)
    if case == "welch":
        plan["expected_outputs"] = [
            "N, media y desviación estándar por grupo",
            "F de Welch",
            "Grados de libertad",
            "p global",
        ]
    return plan


def test_exact_request_separates_group_summary_from_global_test_and_conserves_method():
    products, excluded, uncertain, mentioned = product_request(WELCH)
    assert products == {"grouped", "global_test", "degrees_of_freedom", "p_value"}
    assert excluded == {"posthoc"} and not uncertain and mentioned
    scope = requested_scope({"stage_data": {}}, [], Turn(request_id=uuid4(), content=WELCH))
    assert scope["required_methods"] == ["welch_anova"]
    fid = str(uuid4())
    files = [
        {"id": fid, "file_role": "dataset", "metadata": inspect_file("s.csv", CSV, "dataset", Settings(_env_file=None))}
    ]
    validate_plan_scope(Plan.model_validate(welch(fid)), scope, files)
    classic = welch(fid)
    classic["method"] = "ANOVA clásico de puntaje según grupo"
    with pytest.raises(ValueError, match="Welch"):
        validate_plan_scope(Plan.model_validate(classic), scope, files)
    # Resumen agrupado no acredita además un resumen global no producido.
    with pytest.raises(ValueError):
        validate_plan_scope(
            Plan.model_validate(welch(fid)), {**scope, "products": [*scope["products"], "global"]}, files
        )


@pytest.mark.parametrize("provider_id", ["gemini", "openai"])
def test_exact_welch_accept_prepare_execute_and_interpret(local, provider_id, monkeypatch):
    monkeypatch.setattr("test_session6.proposal", welch)
    execute_flow(local, provider_id, "welch", WELCH)


@pytest.mark.parametrize("provider_id", ["gemini", "openai"])
@pytest.mark.parametrize("failed_correction", [False, True])
def test_semantic_correction_and_manual_retry_never_ask_to_redefine_clear_scope(local, provider_id, failed_correction):
    client, store, provider = local
    path = new(client, store)
    turn(client, path, action="instrument_no")
    file = upload(client, path, "s.csv", CSV)
    invalid = welch(file["id"])
    invalid["variables"][0]["column"] = "inexistente"
    wrong_scope = proposal(file["id"], "welch")
    wrong_scope["expected_outputs"] = ["Resúmenes globales", "Estadístico de prueba global"]
    valid = reply(proposals=[welch(file["id"])], suggested_stage="proposal")
    answers = [reply(proposals=[invalid]), reply(proposals=[wrong_scope]) if failed_correction else valid]
    if failed_correction:
        answers.append(valid)
    if provider_id == "openai":
        calls = terra(client, answers)
        assert select(client, path, provider_id).status_code == 200
    else:
        provider.replies = answers
        calls = provider.contexts
    request_id = str(uuid4())
    response = turn(client, path, content=WELCH, request_id=request_id)
    if failed_correction:
        assert response.status_code == 200, response.text
        assert "alcance definido" in client.get(path).json()["messages"][-1]["content"]
        assert not client.get(path).json()["proposals"]
        assert not any("¿Deseas describir todas" in m["content"] for m in client.get(path).json()["messages"])
        response = turn(client, path, content=WELCH)
    assert response.status_code == 200, response.text
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 1
    assert not detail["conversation"]["stage_data"]["requested_scope"]["unresolved"]
    assert len(calls) == (3 if failed_correction else 2)
    users = [
        m for m in detail["messages"] if m["role"] == "user" and m.get("metadata", {}).get("request_id") == request_id
    ]
    assert len(users) == 1


def test_rows_http_pages_preserve_original_and_do_not_call_ai(local):
    client, store, provider = local
    path = new(client, store)
    data = ("codigo,valor,marcador\n" + "".join(f"00{i},,NA\n" for i in range(123))).encode()
    file = upload(client, path, "s.csv", data)
    url = f"/projects/{store.project_id}/files/{file['id']}/rows"
    pages = [client.get(url, params={"offset": offset, "limit": 50}) for offset in (0, 50, 100)]
    assert all(page.status_code == 200 for page in pages)
    assert pages[0].headers["cache-control"] == "no-store"
    rows = [row for response in pages for row in response.json()["rows"]]
    assert len(rows) == 123 and rows[0] == ["000", "", "NA"] and rows[-1][0] == "00122"
    assert pages[-1].json()["has_more"] is False and pages[0].json()["total_rows"] == 123
    assert client.get(url, params={"limit": 1000}).status_code == 422
    assert client.get(url, params={"offset": -1}).status_code == 422
    assert client.get(url.replace(store.project_id, str(uuid4()))).status_code == 404
    store.data["projects"][0]["user_id"] = str(uuid4())
    assert client.get(url).status_code == 404
    assert not provider.contexts
    assert data in store.objects.values()


def test_xlsx_selected_sheet_formulas_and_json_records():
    settings = Settings(_env_file=None)
    book, out = Workbook(), io.BytesIO()
    book.active.title = "Otra"
    book.active.append(["ignorada"])
    book.active.append(["no seleccionar"])
    chosen = book.create_sheet("Datos")
    chosen.append(["código", "valor", "fórmula"])
    chosen.append(["001", None, "=1+2"])
    book.save(out)
    original = out.getvalue()
    file = {"file_role": "dataset", "file_type": "xlsx", "metadata": {"selected_sheet": "Datos"}}
    page = preview_rows(file, original, settings, 0, 50)
    assert page["columns"] == ["código", "valor", "fórmula"] and page["rows"] == [["001", None, "=1+2"]]
    assert out.getvalue() == original
    file = {"file_role": "dataset", "file_type": "json", "metadata": {"selected_sheet": "tabla"}}
    data = b'[{"texto":"  NA ","n":9007199254740993,"v":null},{"texto":"<script>x</script>","n":1.00}]'
    page = preview_rows(file, data, settings, 0, 1)
    assert page["rows"] == [["  NA ", "9007199254740993", None]] and page["has_more"]
    assert preview_rows(file, data, settings, 1, 50)["rows"][0][1] == "1.00"


def test_instrument_has_no_rows_endpoint(local):
    from test_session6 import PDF

    client, store, _ = local
    path = new(client, store)
    file = upload(client, path, PDF.name, PDF.read_bytes(), "instrument")
    response = client.get(f"/projects/{store.project_id}/files/{file['id']}/rows")
    assert response.status_code == 422 and "metadatos" in response.json()["detail"]


def test_explanation_guards_reject_observed_claims_but_allow_caution_and_real_id():
    run_id = str(uuid4())
    context = {
        "project_mode": "thesis",
        "research_context": None,
        "analysis_results": [{"run_id": run_id, "components": [{"statistics": {}, "tables": []}]}],
    }
    for text in [
        "La media supera la mediana, lo que evidencia una leve asimetría positiva.",
        "Ejecutado bajo el run_id archivo del proyecto.",
        f"run_id {uuid4()}",
        "He registrado tu objetivo general provisional.",
    ]:
        with pytest.raises(ValueError):
            validate_explanation(text, context)
    for text in [
        "La diferencia podría ser compatible con asimetría; no basta para confirmarla.",
        "Consideraré este objetivo en la conversación; no está guardado en Contexto.",
        f"Ejecución run_id {run_id}",
    ]:
        validate_explanation(text, context)


@pytest.mark.parametrize("provider_id", ["gemini", "openai"])
def test_observed_error_then_failed_correction_preserves_clear_request(local, provider_id):
    client, store, provider = local
    path = new(client, store)
    turn(client, path, action="instrument_no")
    file = upload(client, path, "s.csv", CSV)
    valid = welch(file["id"])
    # Primera generación y su corrección mezclan preguntas esenciales con un plan.
    invalid_envelope = reply(proposals=[valid], clarification_required=True, questions=["¿Diseño?"])
    invalid_output = reply(proposals=[{**valid, "expected_outputs": ["Balance integral no verificable"]}])
    answers = [invalid_envelope, invalid_envelope, invalid_output, invalid_output, reply(proposals=[valid])]
    if provider_id == "openai":
        calls = terra(client, answers)
        select(client, path, provider_id)
    else:
        provider.replies = answers
        calls = provider.contexts
    request_id = str(uuid4())
    assert turn(client, path, content=WELCH, request_id=request_id).status_code == 502
    # El UUID fallido se reintenta sin duplicar el mensaje, con la misma solicitud.
    assert turn(client, path, content=WELCH, request_id=request_id).status_code == 200
    detail = client.get(path).json()
    assert not detail["proposals"]
    assert not detail["conversation"]["stage_data"]["requested_scope"]["unresolved"]
    assert "alcance definido" in detail["messages"][-1]["content"]
    assert "¿Deseas describir todas" not in detail["messages"][-1]["content"]
    assert turn(client, path, content=WELCH).status_code == 200
    assert len(client.get(path).json()["proposals"]) == 1 and len(calls) == 5


def test_rows_require_authentication():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get(f"/projects/{uuid4()}/files/{uuid4()}/rows").status_code == 401


def test_saved_interpretation_gets_bounded_correction_without_changing_result(local):
    execute_flow(local, "gemini", "thesis", "Quiero descriptiva global de puntaje")
    client, store, provider = local
    conversation = store.data["conversations"][0]
    path = f"/projects/{store.project_id}/conversations/{conversation['id']}"
    saved = copy.deepcopy(store.data["analysis_runs"])
    provider.replies = [
        reply(response="La media es superior a la mediana, lo que evidencia una leve asimetría positiva."),
        reply(
            response="La diferencia entre media y mediana no basta para confirmar asimetría. Revisa la distribución sin atribuirle una intensidad no calculada."
        ),
    ]
    before = len(provider.contexts)
    assert turn(client, path, content="Interpreta el resultado guardado").status_code == 200
    assert len(provider.contexts) == before + 2 and provider.contexts[-1][1]
    assert store.data["analysis_runs"] == saved
    assert "no basta" in client.get(path).json()["messages"][-1]["content"]


def test_t10_corrects_ambiguous_registration_without_writing_context(local):
    client, store, provider = local
    store.data["projects"][0]["project_type"] = "thesis"
    path = new(client, store)
    turn(client, path, action="instrument_no")
    upload(client, path, "s.csv", CSV)
    provider.replies = [
        reply(response="He registrado tu objetivo general provisional."),
        reply(
            response="Consideraré ese objetivo en esta conversación; no está guardado en Contexto. Revísalo y confírmalo en ese módulo; las hipótesis no son obligatorias en un estudio descriptivo."
        ),
    ]
    assert turn(client, path, content="Mi objetivo general es describir puntaje").status_code == 200
    assert len(provider.contexts) == 2 and not store.data["research_contexts"]
    assert "no está guardado en Contexto" in client.get(path).json()["messages"][-1]["content"]


def test_repeated_request_repairs_old_scope_only_from_complete_user_evidence(local):
    client, store, provider = local
    path = new(client, store)
    turn(client, path, action="instrument_no")
    file = upload(client, path, "s.csv", CSV)
    old_id = str(uuid4())
    cid = path.rsplit("/", 1)[1]
    old_message = {
        "id": str(uuid4()),
        "conversation_id": cid,
        "role": "user",
        "content": WELCH,
        "message_type": "text",
        "position": len(store.data["messages"]),
        "metadata": {"request_id": old_id},
    }
    store.data["messages"].append(old_message)
    store.data["conversations"][0]["stage_data"]["requested_scope"] = {
        "version": 1,
        "products": ["global", "global_test"],
        "excluded_products": ["posthoc"],
        "unresolved": False,
        "mode": "analysis",
        "source_requests": [old_id],
        "through_position": old_message["position"],
    }
    frozen = copy.deepcopy(old_message)
    provider.replies = [reply(proposals=[welch(file["id"])])]
    assert turn(client, path, content=WELCH).status_code == 200
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 1
    scope = detail["conversation"]["stage_data"]["requested_scope"]
    assert "global" not in scope["products"] and scope["recognizer_version"] == 2
    assert old_message == frozen


def test_cache_rebuild_does_not_erase_authentic_global_request_or_truncated_history():
    request_id = str(uuid4())
    saved = {
        "version": 1,
        "products": ["global"],
        "unresolved": False,
        "source_requests": [request_id],
        "through_position": 1,
    }
    history = [
        {
            "role": "user",
            "content": "Solicito Resúmenes globales.",
            "position": 1,
            "metadata": {"request_id": request_id},
        }
    ]
    scope = requested_scope(
        {"stage_data": {"requested_scope": saved}}, history, Turn(request_id=uuid4(), content=WELCH)
    )
    assert "global" in scope["products"]
    truncated = [{"role": "user", "content": "Continúa", "position": i + 10, "metadata": {}} for i in range(30)]
    scope = requested_scope(
        {"stage_data": {"requested_scope": saved}}, truncated, Turn(request_id=uuid4(), content=WELCH)
    )
    assert "global" in scope["products"] and scope["unresolved"]
