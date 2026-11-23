"""Regresiones de Sesión 08 con API real y Auth/Storage/proveedores simulados."""

import copy
import json
from uuid import uuid4

import pytest
import test_chat_api
from pydantic import ValidationError
from test_chat_api import attach_dataset, new, plan, reply, turn
from test_gemini import SDKDouble
from test_instruments import (
    DEVICE_QUESTION,
    INTERNET_QUESTION,
    SKILLS_QUESTION,
    SKILLS_SCALE,
    docx,
    pdf,
    thematic_docx,
)
from test_provider_selection import select, terra

from app.core.config import Settings
from app.models.chat import AssistantReply, Turn
from app.models.research_context import ResearchContext
from app.services.conversation_text import interaction_mode
from app.services.gemini import SYSTEM, GeminiProvider
from app.services.instrument_context import PARTIAL_EVIDENCE
from app.services.profiling import inspect_file
from app.services.reply_contract import normalize_reply, parse_assistant_reply

api = test_chat_api.api


def upload_instrument(client, path, extension, text):
    data = docx(text) if extension == "docx" else pdf(text)
    response = client.post(
        path + "/files", files={"file": (f"escala.{extension}", data)}, data={"file_role": "instrument"}
    )
    assert response.status_code == 201, response.text
    return response.json(), data


def thesis_context(store, revision=3):
    store.data["projects"][0]["project_type"] = "thesis"
    document = ResearchContext(
        general_objective="Describir las respuestas del instrumento.",
        methodological_design="Observacional transversal descriptivo, análisis secundario.",
    ).model_dump(mode="json")
    store.data["research_contexts"] = [
        {
            "project_id": store.project_id,
            "document": document,
            "revision": revision,
            "updated_at": "2026-11-20T12:00:00Z",
        }
    ]


@pytest.mark.parametrize(
    "mode,extension",
    [
        ("general", "pdf"),
        ("general", "docx"),
        ("thesis", None),
        ("thesis", "pdf"),
        ("thesis", "docx"),
        ("thesis", "multiple"),
    ],
)
def test_understanding_and_simple_plan_remain_distinct_and_idempotent(api, mode, extension):
    client, store, provider = api
    if mode == "thesis":
        thesis_context(store)
    path = new(client, store)
    turn(client, path, action="instrument_yes" if extension else "instrument_no")
    originals = []
    for ext in ["pdf", "docx"] if extension == "multiple" else [extension] if extension else []:
        record, original = upload_instrument(
            client, path, ext, ["Z17: ¿Con qué frecuencia recibe apoyo?", "Nunca; A veces; Siempre"]
        )
        assert record["file_role"] == "instrument" and record["original_name"] == f"escala.{ext}"
        assert record["file_size"] == len(original)
        originals.append((record, original))
    if extension:
        assert turn(client, path, action="instruments_done").status_code == 200
    fid = attach_dataset(client, path)
    invalid = plan(fid, mode == "thesis")
    invalid["variables"][0]["column"] = "columna_inexistente"
    provider.replies.append(
        reply(
            response="Los archivos están asociados; revisaré su estructura.",
            proposals=[invalid],
            suggested_stage="proposal",
            detected_goal="Comprender archivos",
        )
    )
    request_id = str(uuid4())
    assert turn(client, path, action="files_ready", request_id=request_id).status_code == 200
    assert turn(client, path, action="files_ready", request_id=request_id).json()["replayed"]
    detail = client.get(path).json()
    assert not detail["proposals"] and detail["conversation"]["primary_goal"] is None
    assert detail["conversation"]["title"] == "Exploración de archivos"
    assert detail["conversation"]["stage_data"]["title_provisional"] is True
    assert len(provider.contexts) == 1 and provider.contexts[-1][0]["interaction_mode"] == "understanding"
    if mode == "thesis":
        assert provider.contexts[-1][0]["research_context"]["revision"] == 3
    proposed = plan(fid, mode == "thesis")
    proposed["components"] = [
        {"procedure": "descriptive", "method": proposed["method"], "variables": proposed["variables"]}
    ]
    provider.replies.append(reply(response="Revisa la propuesta descriptiva.", proposals=[proposed]))
    assert turn(client, path, content="Quiero un plan descriptivo de nota").status_code == 200
    detail = client.get(path).json()
    assert len(provider.contexts) == 2 and len(detail["proposals"]) == 1
    assert not detail["proposals"][0]["analysis_plan"]["components"]
    assert (
        client.patch(path + "/proposals/" + detail["proposals"][0]["id"], json={"status": "accepted"}).status_code
        == 200
    )
    assert not store.data["analysis_runs"]
    for record, original in originals:
        download = client.get(f"/projects/{store.project_id}/files/{record['id']}/download")
        assert download.status_code == 200 and download.content == original


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_document_query_retrieves_late_question_and_missing_code_uses_no_provider(api, extension):
    client, store, provider = api
    thesis_context(store)
    path = new(client, store)
    turn(client, path, action="instrument_yes")
    preamble = [f"Section {i}: orientation text for participants. " * 14 for i in range(35)]
    record, original = upload_instrument(
        client,
        path,
        extension,
        preamble + ["SUP097: Perceived community support?", "Options: None, Sometimes, Always."],
    )
    query = "¿Qué pregunta y opciones corresponden a SUP097 en el instrumento?"
    assert turn(client, path, content=query).status_code == 200
    assert not provider.contexts
    assert "no está autorizado" in client.get(path).json()["messages"][-1]["content"]
    provider.replies.append(
        reply(response="SUP097: «Perceived community support?». Opciones recuperadas: None, Sometimes, Always.")
    )
    assert turn(client, path, content=query, share_instrument_text=True).status_code == 200
    context = provider.contexts[-1][0]
    instrument = next(f["instrument"] for f in context["files"] if "instrument" in f)
    assert "SUP097" in str(instrument["fragments_shared"])
    assert len(str(instrument)) < 16000 and instrument["fragments_omitted"] > 0
    content = client.get(path).json()["messages"][-1]["content"]
    assert record["original_name"] in content and "Fuentes de los fragmentos" in content
    assert not client.get(path).json()["proposals"]
    assert (
        turn(client, path, content="¿Qué dice ABSENT099 en el instrumento?", share_instrument_text=True).status_code
        == 200
    )
    assert len(provider.contexts) == 1
    assert "No encontré" in client.get(path).json()["messages"][-1]["content"]
    assert store.objects[record["storage_path"]] == original


def test_legacy_extraction_expands_ephemerally_only_with_consent(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action="instrument_yes")
    record, _ = upload_instrument(client, path, "pdf", ["Introduction", "OLD057: New fragment."])
    file = store.data["project_files"][0]
    file["metadata"] = {"sheets": [], "text_excerpt": "Introduction"}
    old = copy.deepcopy(file)
    assert turn(client, path, content="Busca OLD057 en el instrumento").status_code == 200
    provider.replies.append(reply(response="OLD057: «New fragment.»"))
    assert turn(client, path, content="Busca OLD057 en el instrumento", share_instrument_text=True).status_code == 200
    assert "OLD057" in str(provider.contexts[-1][0]["files"])
    assert store.data["project_files"][0] == old
    assert record["id"] == file["id"]


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_document_layout_codes_reach_provider_and_title_preserves_manual_choice(api, extension):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action="instrument_yes")
    upload_instrument(client, path, extension, ["EDU_030: Participation?", "A Never; B Often."])
    provider.replies.append(reply(response="EDU030: «Participation?». A Never; B Often."))
    assert turn(client, path, content="Busca EDU 030", share_instrument_text=True).status_code == 200
    assert len(provider.contexts) == 1
    saved = client.get(path).json()
    assert saved["conversation"]["title"] == "Busca EDU 030"
    assert saved["conversation"]["primary_goal"] is None
    assert saved["messages"][-1]["metadata"]["instrument_retrieval"][0]["retrieval"] == "matched"
    assert "word/document.xml" not in saved["messages"][-1]["content"]
    assert client.patch(path, json={"title": "Mi consulta documental"}).status_code == 200
    provider.replies.append(reply(response="EDU030: «Participation?"))
    assert (
        turn(client, path, content="Describe EDU030 en el instrumento", share_instrument_text=True).status_code == 200
    )
    assert client.get(path).json()["conversation"]["title"] == "Mi consulta documental"


def test_empty_document_diagnostic_is_distinct_and_never_calls_provider(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action="instrument_yes")
    upload_instrument(client, path, "pdf", [""])
    assert turn(client, path, content="Busca EDU030 en el instrumento", share_instrument_text=True).status_code == 200
    message = client.get(path).json()["messages"][-1]
    assert "No se recuperó texto" in message["content"]
    assert message["metadata"]["instrument_retrieval"][0]["retrieval"] == "no_text"
    assert not provider.contexts


def test_thematic_docx_turn_covers_distant_topics_and_validates_quotes_with_consent(api):
    client, store, provider = api
    thesis_context(store, 1)
    path = new(client, store)
    assert turn(client, path, action="instrument_yes").status_code == 200
    upload = client.post(
        path + "/files", files={"file": ("encuesta.docx", thematic_docx())}, data={"file_role": "instrument"}
    )
    assert upload.status_code == 201
    assert turn(client, path, action="instruments_done").status_code == 200
    attach_dataset(client, path)
    query = (
        "¿Qué preguntas relacionadas con equipos electrónicos, conectividad y alfabetización digital hay? "
        "Incluye el texto de las preguntas y opciones de respuesta de cada tema, respetando el orden original. " * 4
    )
    assert turn(client, path, content=query, share_instrument_text=False).status_code == 200
    assert not provider.contexts
    unauthorized = client.get(path).json()["messages"][-1]["metadata"]["instrument_retrieval"][0]
    assert unauthorized["retrieval"] == "not_authorized"
    absent = "¿Qué preguntas relacionadas con la atención médica contiene el instrumento?"
    assert turn(client, path, content=absent, share_instrument_text=True).status_code == 200
    assert not provider.contexts
    assert client.get(path).json()["messages"][-1]["metadata"]["instrument_retrieval"][0]["retrieval"] == "no_match"

    provider.replies.append(reply(response="«Do you own a phone?»\n«Yes / No»"))
    provider.replies.append(
        reply(
            response="\n".join(
                f"«{text}»" for text in (DEVICE_QUESTION, INTERNET_QUESTION, SKILLS_QUESTION, SKILLS_SCALE)
            )
            + f"\n{PARTIAL_EVIDENCE}",
            warnings=["Invented option"],
        )
    )
    result = turn(client, path, content=query, share_instrument_text=True)
    assert result.status_code == 200, result.text
    assert len(provider.contexts) == 2 and "document_evidence" in provider.contexts[1][1]
    context = provider.contexts[0][0]
    assert context["interaction_mode"] == "document" and context["instrument_text_authorized"] is True
    instrument = next(file["instrument"] for file in context["files"] if file["role"] == "instrument")
    assert instrument["retrieval_method"] == "thematic"
    fragments = instrument["fragments_shared"]
    assert {DEVICE_QUESTION, INTERNET_QUESTION, SKILLS_QUESTION, SKILLS_SCALE} <= {
        fragment["text"] for fragment in fragments
    }
    assert len(fragments) <= 10 and sum(len(fragment["text"]) for fragment in fragments) <= 12000
    saved = client.get(path).json()["messages"][-1]
    assert "Do you own" not in saved["content"] and not saved["metadata"]["warnings"]
    assert context["research_context"]["revision"] == 1


def test_numbered_document_query_uses_previously_persisted_fragments(api, monkeypatch):
    client, store, provider = api
    thesis_context(store, 1)
    path = new(client, store)
    assert turn(client, path, action="instrument_no").status_code == 200
    attach_dataset(client, path)
    store.data["project_files"][0]["created_at"] = "2026-11-21T12:05:00Z"
    conversation = store.data["conversations"][0]
    conversation["current_stage"] = "goal"
    file_id = str(uuid4())
    name = "encuesta.docx"
    metadata = inspect_file(name, thematic_docx(), "instrument", Settings(_env_file=None))
    metadata["text_excerpt"] = "Vista previa de una versión anterior sin los ítems."
    record = {
        "id": file_id,
        "project_id": store.project_id,
        "original_name": name,
        "file_role": "instrument",
        "file_type": "docx",
        "storage_path": "original-privado.docx",
        "created_at": "2026-11-21T12:00:00Z",
        "metadata": metadata,
    }
    persisted = json.loads(json.dumps(record))
    store.data["project_files"].append(persisted)
    store.data["conversation_files"].append({"conversation_id": conversation["id"], "file_id": file_id})

    async def unexpected_download(*args, **kwargs):
        pytest.fail("El turno con extracción versionada debe usar los fragmentos ya persistidos.")

    monkeypatch.setattr(store, "download", unexpected_download)
    before = client.get(path).json()
    assert any(file["id"] == file_id for file in before["files"])
    requested = (
        "Consulta los fragmentos autorizados del instrumento Word encuesta.docx.\n"
        "Necesito identificar las preguntas relacionadas con:\n"
        "1. El uso de dispositivos digitales para estudiar, trabajar o entretenerse.\n"
        "2. El acceso y uso de internet, únicamente con evidencia verificable.\n"
        "3. Las habilidades o competencias digitales de los estudiantes.\n"
        "Indica el texto, las alternativas y la ubicación. No prepares propuestas estadísticas."
    )
    provider.replies.append(reply(response=f"«{DEVICE_QUESTION}»\n«{SKILLS_SCALE}»\n{PARTIAL_EVIDENCE}"))
    result = turn(client, path, content=requested, share_instrument_text=True)
    assert result.status_code == 200, result.text
    assert len(provider.contexts) == 1
    context, correction = provider.contexts[0]
    assert correction is None and context["interaction_mode"] == "document"
    assert context["research_context"]["revision"] == 1 and context["instrument_text_authorized"] is True
    instrument = next(file["instrument"] for file in context["files"] if file["file_id"] == file_id)
    assert instrument["retrieval"] == "matched" and instrument["retrieval_method"] == "thematic"
    assert instrument["fragments_available"] == len(metadata["fragments"])
    assert {DEVICE_QUESTION, INTERNET_QUESTION, SKILLS_QUESTION, SKILLS_SCALE} <= {
        fragment["text"] for fragment in instrument["fragments_shared"]
    }
    assert store.data["chat_requests"][-1]["payload"]["content"] == requested
    after = client.get(path).json()
    assert after["messages"][: len(before["messages"])] == before["messages"]
    assert SKILLS_SCALE in after["messages"][-1]["content"] and not after["proposals"]

    absent = "Consulta el instrumento:\n1. Preguntas de atención médica.\n2. Preguntas de seguridad alimentaria."
    assert turn(client, path, content=absent, share_instrument_text=True).status_code == 200
    assert len(provider.contexts) == 1
    blocked = client.get(path).json()["messages"][-1]
    assert blocked["metadata"]["instrument_retrieval"][0]["retrieval"] == "no_match"
    assert blocked["metadata"]["generation"]["source"] == "deterministic"
    assert persisted == record


def test_long_document_query_recovers_dotted_codes_across_pages_with_explicit_consent(api):
    client, store, provider = api
    path = new(client, store)
    assert turn(client, path, action="instrument_yes").status_code == 200
    introductory_pages = ["Instructions for participants. " * 30] * 20
    items = [
        "QST.030: Do you attend workshops? Options: yes or no.",
        "QST.050: How often do you read? Options: weekly or monthly.",
        "QST.120: How far is the library? Options: near or far.",
    ]
    record, _ = upload_instrument(client, path, "pdf", introductory_pages + items)
    assert not any(item in record["metadata"]["text_excerpt"] for item in items)
    assert turn(client, path, action="instruments_done").status_code == 200
    attach_dataset(client, path)
    query = (
        "Recupera las preguntas del instrumento y sus opciones de respuesta. "
        + "Indica la página del fragmento y conserva las opciones en el orden del documento. " * 12
        + "Busca QST030, QST.050, QST 120 y ZZZ999."
    )
    assert turn(client, path, content=query, share_instrument_text=False).status_code == 200
    unshared = client.get(path).json()
    assert unshared["conversation"]["title"].startswith("Recupera las preguntas")
    assert unshared["messages"][-1]["metadata"]["instrument_retrieval"][0]["retrieval"] == "not_authorized"
    assert not provider.contexts
    provider.replies.append(
        reply(
            response="QST.030: «Do you attend workshops?». QST050: «How often do you read?». QST 120: «How far is the library?». No encontré ZZZ.999."
        )
    )
    assert turn(client, path, content=query, share_instrument_text=True).status_code == 200
    assert len(provider.contexts) == 1
    context = provider.contexts[0][0]
    assert context["interaction_mode"] == "document" and context["instrument_text_authorized"] is True
    assert store.data["chat_requests"][-1]["payload"]["share_instrument_text"] is True
    evidence = next(item["instrument"] for item in context["files"] if "instrument" in item)
    for page, item in enumerate(items, start=21):
        assert any(f["location"] == f"Página {page}" and item in f["text"] for f in evidence["fragments_shared"])
    assert evidence["fragments_available"] > len(evidence["fragments_shared"])
    assert len(evidence["fragments_shared"]) <= 10
    assert not client.get(path).json()["proposals"]


@pytest.mark.parametrize("provider_name", ["gemini", "openai"])
def test_transport_discards_malformed_unsolicited_plan_without_extra_calls(api, monkeypatch, provider_name):
    client, store, _ = api
    path = new(client, store)
    turn(client, path, action="instrument_no")
    attach_dataset(client, path)
    raw = reply(
        response="El archivo contiene mediciones.", proposals=[{"invalid": "not a plan"}], suggested_stage="proposal"
    )
    if provider_name == "gemini":
        sdk = SDKDouble([json.dumps(raw)])
        monkeypatch.setattr("app.services.gemini.genai.Client", lambda **_: sdk)
        client.app.state.provider = GeminiProvider(Settings(_env_file=None, gemini_api_key="synthetic"))
        calls = sdk.calls
    else:
        calls = terra(client, [raw])
        assert select(client, path, "openai").status_code == 200
    assert turn(client, path, action="files_ready").status_code == 200
    assert len(calls) == 1 and not client.get(path).json()["proposals"]
    with pytest.raises(ValidationError):
        parse_assistant_reply(json.dumps(raw), "planning")


def test_methodology_ignores_old_unresolved_scope_and_does_not_change_it(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action="instrument_no")
    attach_dataset(client, path)
    saved_scope = {"version": 1, "products": ["p_value"], "unresolved": True, "mode": "analysis"}
    store.data["conversations"][0]["stage_data"]["requested_scope"] = copy.deepcopy(saved_scope)
    provider.replies.append(reply(response="Un diseño transversal observa una medición temporal por unidad."))
    assert turn(client, path, content="Explícame qué es un diseño transversal").status_code == 200
    assert len(provider.contexts) == 1 and "requested_scope" not in provider.contexts[0][0]
    assert store.data["conversations"][0]["stage_data"]["requested_scope"] == saved_scope


def test_incompatible_component_is_not_normalized_and_stays_rejected(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action="instrument_no")
    fid = attach_dataset(client, path)
    wrong = plan(fid)
    wrong["components"] = [{"procedure": "correlation", "method": "Pearson", "variables": wrong["variables"]}]
    provider.replies.extend([reply(proposals=[wrong]), reply(proposals=[wrong])])
    result = turn(client, path, content="Describe las notas")
    assert result.status_code == 502 and result.headers["x-statia-error"] == "planning_validation"
    assert len(provider.contexts) == 2 and not client.get(path).json()["proposals"]
    original = AssistantReply.model_validate(reply(proposals=[wrong]))
    assert normalize_reply(original, "planning").proposals[0].components


def test_confirmed_context_false_denial_corrected_and_current_revision_sent(api):
    client, store, provider = api
    thesis_context(store)
    path = new(client, store)
    turn(client, path, action="instrument_no")
    attach_dataset(client, path)
    provider.replies.extend(
        [
            reply(response="Tus objetivos todavía no están guardados en Contexto."),
            reply(response="El Contexto confirmado, revisión 3, ya contiene tu objetivo descriptivo."),
        ]
    )
    assert turn(client, path, content="Explícame el contexto confirmado").status_code == 200
    assert len(provider.contexts) == 2
    assert "revision" in str(provider.contexts[-1][0]["research_context"])
    assert "confirmado" in client.get(path).json()["messages"][-1]["content"]
    assert store.data["research_contexts"][0]["revision"] == 3


ASK_THREE = (
    "Genera hasta tres alternativas de análisis estadístico descriptivo basadas en "
    "los objetivos confirmados del Contexto y las variables existentes."
)
ASK_ONE = (
    "Prepara una única propuesta descriptiva de los patrones de uso. Incluye columnas exactas, "
    "tipos de variables, ausencias, tablas y gráficos y limitaciones metodológicas. "
    "No ejecutes cálculos todavía."
)


def planning_workspace(api):
    client, store, provider = api
    thesis_context(store, 1)
    context = store.data["research_contexts"][0]["document"]
    context["specific_objectives"] = ["Describir mediciones y categorías de participación."]
    path = new(client, store)
    assert turn(client, path, action="instrument_yes").status_code == 200
    upload_instrument(client, path, "docx", ["CA31: ¿Cómo participa?"])
    assert turn(client, path, action="instruments_done").status_code == 200
    dataset = client.post(
        path + "/files",
        files={
            "file": (
                "respuestas.csv",
                b"rango,mixta,modalidad,ambito\n1,10,habitual,uno\n2,otra,ocasional,dos\n3,15,habitual,uno\n"
                b"1,otra,ocasional,dos\n2,10,habitual,uno\n3,15,ocasional,dos\n",
            )
        },
        data={"file_role": "dataset"},
    )
    assert dataset.status_code == 201, dataset.text
    return path, dataset.json()["id"]


def frequency_plan(fid, column):
    option = plan(fid, thesis=True)
    option.update(
        title=f"Distribución de {column}",
        objective=f"Describir la distribución de `{column}`.",
        method=f"Frecuencias de `{column}`",
        requirements=["Informar ausencias por variable y conservar las respuestas mixtas como categorías."],
        expected_outputs=["Frecuencias categóricas"],
    )
    option["variables"][0]["column"] = column
    return option


@pytest.mark.parametrize("invalid", [None, "column_reference", "internal_contract"])
def test_thesis_explicit_alternatives_persist_only_valid_reviewable_plans(api, monkeypatch, invalid):
    client, store, provider = api
    path, fid = planning_workspace(api)
    original_context = copy.deepcopy(store.data["research_contexts"])
    options = [frequency_plan(fid, name) for name in ("rango", "modalidad", "ambito")]
    payload = reply(
        response="He preparado tres propuestas descriptivas.", proposals=options, suggested_stage="proposal"
    )
    if invalid == "column_reference":
        options[-1]["variables"][0]["column"] = "inexistente"
    if invalid == "internal_contract":
        del options[-1]["requirements"]

    # La doble respuesta atraviesa el mismo parser de contratos de los proveedores.
    async def generate(context, correction=None):
        provider.contexts.append((context, correction))
        return parse_assistant_reply(
            json.dumps(payload), context["interaction_mode"], validate_plans_separately="proposal_limit" in context
        )

    monkeypatch.setattr(provider, "generate", generate)
    request_id = str(uuid4())
    result = turn(client, path, content=ASK_THREE, request_id=request_id)
    assert result.status_code == 200, result.text
    expected = 2 if invalid else 3
    detail = client.get(path).json()
    message = detail["messages"][-1]
    assert f" {expected} " in message["content"] and "Contexto" not in message["content"]
    assert len(detail["proposals"]) == expected
    assert all(row["status"] == "proposed" and row["source_message_id"] == message["id"] for row in detail["proposals"])
    context = provider.contexts[0][0]
    assert context["interaction_mode"] == "planning" and context["proposal_limit"] == 3
    assert context["research_context"]["revision"] == 1
    assert context["research_context"]["document"]["specific_objectives"]
    assert context["research_context"]["document"]["methodological_design"]
    columns = {col["name"]: col for file in context["files"] if file["role"] == "dataset" for col in file["columns"]}
    assert columns["rango"]["statistical_type"] == "categorical_or_ordinal"
    assert columns["mixta"]["inferred_type"] == columns["mixta"]["statistical_type"] == "mixed"
    assert not store.data["analysis_runs"] and store.data["research_contexts"] == original_context
    if invalid:
        assert len(provider.contexts) == 2 and invalid in provider.contexts[-1][1]
        assert message["metadata"]["planning_validation"]["partial"]

    first, second, *_ = detail["proposals"]
    assert client.patch(path + "/proposals/" + first["id"], json={"status": "accepted"}).status_code == 200
    assert client.patch(path + "/proposals/" + second["id"], json={"status": "rejected"}).status_code == 200
    assert turn(client, path, content=ASK_THREE, request_id=request_id).json()["replayed"]
    reloaded = client.get(path).json()
    assert {row["id"]: row["status"] for row in reloaded["proposals"]} == {
        row["id"]: ("accepted" if row == first else "rejected" if row == second else "proposed")
        for row in detail["proposals"]
    }
    assert len([msg for msg in reloaded["messages"] if msg["content"] == ASK_THREE]) == 1
    assert not store.data["analysis_runs"] and store.data["research_contexts"] == original_context


@pytest.mark.parametrize(
    "failure", ["proposal_missing", "response_content", "objective_variables", "essential_clarification"]
)
def test_explicit_single_plan_failure_is_diagnostic_and_can_retry_without_duplicates(api, failure):
    client, store, provider = api
    path, fid = planning_workspace(api)
    valid = frequency_plan(fid, "rango")
    bad = copy.deepcopy(valid)
    if failure == "proposal_missing":
        answer = reply(response="He preparado una propuesta. ¿Deseas revisarla?", suggested_stage="proposal")
    elif failure == "response_content":
        answer = reply(response="Acepta la propuesta en el módulo Contexto.", proposals=[bad])
    else:
        if failure == "objective_variables":
            bad["objective"] = "Describir las mediciones."
        else:
            bad["methodology_confirmed"] = False
        answer = reply(proposals=[bad])
    provider.replies.extend([answer, copy.deepcopy(answer), reply(proposals=[valid])])
    request_id = str(uuid4())
    response = turn(client, path, content=ASK_ONE, request_id=request_id)
    assert response.status_code == 502 and failure in response.headers["x-statia-validation"]
    assert "Puedes reintentar" in response.json()["detail"]
    detail = client.get(path).json()
    assert not detail["proposals"] and detail["retry_turn"]["request_id"] == request_id
    assert turn(client, path, content=ASK_ONE, request_id=request_id).status_code == 200
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 1
    assert len([msg for msg in detail["messages"] if msg["content"] == ASK_ONE]) == 1
    assert provider.contexts[-1][0]["proposal_limit"] == 1 and not store.data["analysis_runs"]


def test_methodological_discussion_stays_without_proposals(api):
    client, store, provider = api
    path, fid = planning_workspace(api)
    provider.replies.append(
        reply(
            response="Las frecuencias describen categorías y la mediana necesita un orden interpretable.",
            proposals=[frequency_plan(fid, "rango")],
        )
    )
    response = turn(client, path, content="¿Qué métodos descriptivos serían adecuados? Solo explica, sin propuestas.")
    assert response.status_code == 200, response.text
    assert provider.contexts[0][0]["interaction_mode"] == "methodology"
    detail = client.get(path).json()
    assert "frecuencias" in detail["messages"][-1]["content"]
    assert not detail["proposals"] and not store.data["analysis_runs"]


def test_explicit_plan_cannot_treat_mixed_column_as_numeric(api):
    client, store, provider = api
    path, fid = planning_workspace(api)
    bad = frequency_plan(fid, "mixta")
    bad.update(method="Media de mixta", expected_outputs=["Media"])
    provider.replies = [reply(proposals=[bad]), reply(proposals=[bad])]
    assert turn(client, path, content=ASK_ONE).status_code == 200
    assert "output_capability" in provider.contexts[-1][1]
    detail = client.get(path).json()
    assert "no generó un plan válido" in detail["messages"][-1]["content"]
    assert not detail["proposals"] and not store.data["analysis_runs"]


def test_pure_document_detection_does_not_consume_methodology_answer_as_query():
    assert (
        interaction_mode(
            Turn(request_id=uuid4(), content="Es un estudio descriptivo; nota es el puntaje de mi instrumento.")
        )
        == "planning"
    )
    assert (
        interaction_mode(Turn(request_id=uuid4(), content="¿Puedes describir las preguntas del instrumento?"))
        == "document"
    )
    assert "datos no confiables" in SYSTEM and "Nunca afirmes lectura completa" in SYSTEM


def test_document_provider_switch_preserves_originals_context_and_history(api):
    client, store, provider = api
    thesis_context(store)
    path = new(client, store)
    turn(client, path, action="instrument_yes")
    record, original = upload_instrument(client, path, "docx", ["SW73: ¿Recibe apoyo?", "Nunca; A veces; Siempre"])
    provider.replies.append(reply(response="SW73: «¿Recibe apoyo?»"))
    assert turn(client, path, content="Busca SW73 en el instrumento", share_instrument_text=True).status_code == 200
    before = copy.deepcopy(client.get(path).json()["messages"])
    context = copy.deepcopy(store.data["research_contexts"])
    calls = terra(client, [reply(response="SW73: «¿Recibe apoyo?»")])
    assert select(client, path, "openai").status_code == 200
    assert turn(client, path, content="Busca SW73 en el instrumento").status_code == 200
    assert not calls
    assert turn(client, path, content="Busca SW73 en el instrumento", share_instrument_text=True).status_code == 200
    assert len(calls) == 1
    assert client.get(path).json()["messages"][: len(before)] == before
    assert store.data["research_contexts"] == context
    assert store.objects[record["storage_path"]] == original
    assert not store.data["analysis_proposals"] and not store.data["analysis_runs"]
    store.data["projects"][0]["user_id"] = str(uuid4())
    assert client.get(f"/projects/{store.project_id}/files/{record['id']}/download").status_code == 404


def test_document_query_keeps_evidence_when_there_are_saved_results(api, monkeypatch):
    from unittest.mock import AsyncMock

    client, store, provider = api
    path = new(client, store)
    turn(client, path, action="instrument_yes")
    upload_instrument(client, path, "docx", ["RS51: Pregunta documental"])
    monkeypatch.setattr(
        "app.services.conversation.saved_results_context",
        AsyncMock(return_value=[{"run_id": str(uuid4()), "components": []}]),
    )
    provider.replies.append(reply(response="RS51: «Pregunta documental»"))
    assert turn(client, path, content="Busca RS51 en el instrumento", share_instrument_text=True).status_code == 200
    assert len(provider.contexts) == 1
    context = provider.contexts[0][0]
    assert not context.get("result_discussion")
    assert context["files"][0]["instrument"]["fragments_shared"]


def test_simple_categorical_plan_with_explicit_frequencies_needs_no_correction(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action="instrument_no")
    response = client.post(
        path + "/files",
        files={"file": ("categoria.csv", b"estado\nHabitual\nOcasional\nHabitual\nSin opinion\n")},
        data={"file_role": "dataset"},
    )
    fid = response.json()["id"]
    proposed = plan(fid)
    proposed.update(
        objective="Describir `estado`", method="Frecuencias de `estado`", expected_outputs=["Frecuencias categóricas"]
    )
    proposed["variables"][0]["column"] = "estado"
    provider.replies.append(reply(proposals=[proposed]))
    assert turn(client, path, content="Quiero un plan descriptivo de estado").status_code == 200
    assert len(provider.contexts) == 1
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 1
    proposal = detail["proposals"][0]
    assert client.patch(path + "/proposals/" + proposal["id"], json={"status": "accepted"}).status_code == 200
    from app.models.chat import Plan
    from app.services.requested_scope import validate_plan_scope

    with pytest.raises(ValueError):
        validate_plan_scope(
            Plan.model_validate(proposal["analysis_plan"]), {"unresolved": False, "products": ["mean"]}, detail["files"]
        )
