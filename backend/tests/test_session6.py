"""Recorridos locales con HTTP/proceso estadístico reales y Auth/Storage/IA simulados."""

import copy
import io
from pathlib import Path
from statistics import mean, stdev
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from scipy import stats
from test_analysis_api import ResultsStore
from test_automatic_preparation import confirmed_job, resolve
from test_chat_api import ControlledProvider, new, reply, turn
from test_provider_selection import select, terra
from test_statistics import job_for

from app.core.auth import Identity, authenticated
from app.core.config import Settings
from app.main import create_app
from app.models.analysis import ExecutionSpec
from app.models.chat import Plan
from app.services.provider_runtime import RequestBudget, current_trace
from app.services.requested_scope import product_request
from app.services.statistics.engine import calculate
from app.services.statistics.preparation import AnalysisError, validate_spec

PDF = Path(__file__).parent / "fixtures/instrumento_sesion6.pdf"
# Fixture nueva de 45 observaciones: no sustituye el CSV de la prueba manual.
ROWS = [(48 + i * 0.73 + (i % 4) * 1.21, 15 + (i * 7 % 41) * 0.61, "ABC"[i // 15], i % 5 + 1) for i in range(45)]
CSV = (Path(__file__).parent / "fixtures/regresion_sesion6.csv").read_bytes()


@pytest.fixture
def local():
    store, provider = ResultsStore(), ControlledProvider()
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[authenticated] = lambda: Identity(store.user_id, store)
    app.state.provider = provider
    with TestClient(app) as client:
        yield client, store, provider


def upload(client, path, name, data, role="dataset"):
    response = client.post(path + "/files", files={"file": (name, data)}, data={"file_role": role})
    assert response.status_code == 201, response.text
    return response.json()


def proposal(fid, case):
    measure = {"file_id": fid, "sheet": "tabla", "column": "puntaje", "role": "outcome"}
    other = {**measure, "column": "tiempo_min", "role": "predictor"}
    group = {**measure, "column": "grupo", "role": "group"}
    plan = {
        "title": "Análisis solicitado",
        "objective": "Describir puntaje",
        "variables": [measure],
        "procedure": "descriptive",
        "method": "Estadística descriptiva de puntaje",
        "justification": "Finalidad indicada",
        "requirements": ["Revisar el alcance"],
        "limitations": ["Describe los registros observados"],
        "expected_outputs": ["Resúmenes globales"],
        "methodology_confirmed": True,
    }
    if case == "pearson":
        plan.update(
            objective="Relacionar puntaje y tiempo_min",
            variables=[measure, other],
            procedure="correlation",
            method="Pearson de puntaje y tiempo_min",
            expected_outputs=["Coeficientes de correlación", "Valores p"],
        )
    elif case == "welch":
        plan.update(
            objective="Comparar puntaje según grupo",
            variables=[measure, group],
            procedure="group_comparison",
            method="ANOVA de Welch de puntaje según grupo",
            comparison=None,
            expected_outputs=["Medias por grupo", "Estadístico de prueba global", "Valores p"],
        )
    elif case == "integral":
        plan.update(
            objective="Describir puntaje y tiempo_min y correlacionar puntaje y tiempo_min",
            variables=[measure, other],
            procedure="integral",
            method="Descripción y Pearson de puntaje y tiempo_min",
            expected_outputs=["Resúmenes globales", "Coeficientes de correlación"],
            components=[
                {
                    "procedure": "descriptive",
                    "method": "Descripción de puntaje y tiempo_min",
                    "variables": [measure, other],
                },
                {
                    "procedure": "correlation",
                    "method": "Pearson de puntaje y tiempo_min",
                    "variables": [measure, other],
                },
            ],
        )
    return plan


@pytest.mark.parametrize("provider_id", ["gemini", "openai"])
@pytest.mark.parametrize(
    "case,user_request",
    [
        ("descriptive", "Quiero descriptiva global de puntaje, con media, mediana, DE, mínimo y máximo."),
        ("pearson", "Quiero correlación Pearson de tiempo_min con puntaje."),
        ("welch", "Quiero ANOVA de Welch de puntaje según grupo, sin comparaciones post hoc."),
        ("integral", "Quiero un análisis integral descriptivo y Pearson de puntaje y tiempo_min."),
        (
            "thesis",
            "Solicito descriptiva global de puntaje compatible con mi objetivo vigente exclusivamente descriptivo.",
        ),
    ],
)
def test_natural_request_accept_prepare_execute_and_saved_interpretation(local, provider_id, case, user_request):
    client, store, provider = local
    if case == "thesis":
        from app.models.research_context import ResearchContext

        store.data["projects"][0]["project_type"] = "thesis"
        store.data["research_contexts"] = [
            {
                "project_id": store.project_id,
                "revision": 2,
                "document": ResearchContext(
                    general_objective="Describir exclusivamente el puntaje observado"
                ).model_dump(mode="json"),
            }
        ]
    path = new(client, store)
    assert turn(client, path, action="instrument_no").status_code == 200
    file = upload(client, path, "regresion_sesion6.csv", CSV)
    proposed = proposal(file["id"], case)
    responses = [
        reply(proposals=[proposed], suggested_stage="proposal"),
        reply(response="El resultado guardado describe los registros observados. Puedes preguntar por sus tablas."),
    ]
    if provider_id == "openai":
        calls = terra(client, responses)
        assert select(client, path, provider_id).status_code == 200
    else:
        provider.replies = responses
        calls = provider.contexts
    response = turn(client, path, content=user_request)
    assert response.status_code == 200, response.text
    detail = client.get(path).json()
    assert len(detail["proposals"]) == 1 and len(calls) == 1
    if case == "thesis" and provider_id == "gemini":
        assert calls[0][0]["research_context"]["revision"] == 2
        assert (
            calls[0][0]["research_context"]["document"]["general_objective"]
            == "Describir exclusivamente el puntaje observado"
        )
    pid = detail["proposals"][0]["id"]
    assert client.patch(path + "/proposals/" + pid, json={"status": "accepted"}).status_code == 200
    response = turn(client, path, action="prepare_execution", proposal_id=pid)
    assert response.status_code == 200, response.text
    for _ in range(6):
        prep = client.get(path).json()["conversation"]["stage_data"]["execution_preparation"]["result"]
        if prep["status"] == "READY":
            break
        assert prep["questions"], prep
        q = prep["questions"][0]
        values = {c["value"] for c in q["choices"]}
        answer = "yes" if "yes" in values else "none"
        assert turn(client, path, action="clarify_execution", question_id=q["id"], answer=answer).status_code == 200
    assert prep["status"] == "READY", prep
    if case in {"descriptive", "thesis"}:
        assert not prep["questions"] and all(c["method"] == "descriptive" for c in prep["specification"]["components"])
        assert all(not c["descriptive_intervals"] for c in prep["specification"]["components"])
    spec = {**prep["specification"], "decisions_confirmed": True}
    response = client.post(
        path + "/proposals/" + pid + "/runs",
        json={"request_id": prep["request_id"], "specification": spec, "preparation_fingerprint": prep["fingerprint"]},
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "completed" and run["artifacts"]
    result = run["result"]
    component = result["components"][-1]
    p = [round(row[0], 2) for row in ROWS]
    t = [round(row[1], 2) for row in ROWS]
    if case == "welch":
        reference = stats.f_oneway(*(p[i : i + 15] for i in (0, 15, 30)), equal_var=False)
        assert [g["n"] for g in component["sample"]["groups"]] == [15, 15, 15]
        assert component["statistics"]["F"] == pytest.approx(reference.statistic, rel=1e-10)
        assert component["statistics"]["p"] == pytest.approx(reference.pvalue, rel=1e-10)
        assert component["statistics"]["df_between"] == 2
        assert spec["components"][0]["posthoc"] == "none"
        summary = next(table for table in component["tables"] if table["title"] == "Resumen por grupos")
        for i, row in enumerate(summary["rows"]):
            assert row["N válido"] == 15
            assert row["Media"] == pytest.approx(mean(p[i * 15 : (i + 1) * 15]))
            assert row["DE muestral"] == pytest.approx(stdev(p[i * 15 : (i + 1) * 15]))
    elif case in {"pearson", "integral"}:
        pair = component["statistics"]["pairs"][0]
        reference = stats.pearsonr(p, t)
        assert pair["coefficient"] == pytest.approx(reference.statistic, rel=1e-10)
        assert pair["p"] == pytest.approx(reference.pvalue, rel=1e-10)
    else:
        # Contraste independiente de los agregados canónicos, no del texto del proveedor.
        summary = component["tables"][0]["rows"][0]
        assert summary["Media"] == pytest.approx(mean(p))
        assert summary["DE muestral"] == pytest.approx(stdev(p))
    snapshot = copy.deepcopy(store.data["analysis_runs"])
    assert turn(client, path, content="Interpreta el resultado guardado").status_code == 200
    assert store.data["analysis_runs"] == snapshot
    assert len(calls) == 2
    if provider_id == "gemini":
        assert calls[-1][0]["analysis_results"]


def test_t10_thesis_without_saved_context_remains_empty(local):
    client, store, provider = local
    store.data["projects"][0]["project_type"] = "thesis"
    path = new(client, store)
    assert turn(client, path, action="instrument_no").status_code == 200
    upload(client, path, "sintetico.csv", CSV)
    provider.replies = [
        reply(
            response="Puedes iniciar sin Contexto guardado. ¿Cuál es tu objetivo general? Revisa y confirma la metodología en el módulo Contexto.",
            questions=["¿Cuál es tu objetivo general?"],
            clarification_required=True,
        )
    ]
    assert turn(client, path, content="Quiero comenzar mi tesis; aún no tengo Contexto guardado").status_code == 200
    assert provider.contexts[0][0]["research_context"] is None
    assert not store.data["research_contexts"]
    assert not client.get(path).json()["proposals"]
    provider.replies = [
        reply(
            response="Podemos orientar la descripción de puntaje con tu objetivo conversacional. Revisa y confirma esa información en Contexto.",
            questions=["¿Qué representa puntaje?"],
            clarification_required=True,
        )
    ]
    assert turn(client, path, content="Quiero describir globalmente el puntaje de mi estudio").status_code == 200
    assert provider.contexts[-1][0]["goal_evidence"]
    assert provider.contexts[-1][0]["research_context"] is None
    assert not store.data["research_contexts"]


def test_instrument_pdf_privacy_reuse_rejections_and_content_deduplication(local):
    client, store, provider = local
    path = new(client, store)
    assert turn(client, path, action="instrument_yes").status_code == 200
    original = PDF.read_bytes()
    instrument = upload(client, path, PDF.name, original, "instrument")
    assert instrument["file_role"] == "instrument" and instrument["metadata"]["pages"] == 1
    assert "Horas de estudio" in instrument["metadata"]["text_excerpt"]
    assert "profile" not in instrument["metadata"]
    assert turn(client, path, action="instruments_done").status_code == 200
    dataset = upload(client, path, "sintetico.csv", CSV)
    provider.replies = [reply(questions=["¿Cuál es tu objetivo?"]), reply(questions=["¿Qué deseas analizar?"])]
    assert turn(client, path, action="files_ready").status_code == 200
    assert "untrusted_instrument_excerpt" not in str(provider.contexts[-1][0])
    assert turn(client, path, action="files_ready", share_instrument_text=True).status_code == 200
    assert "untrusted_instrument_excerpt" in str(provider.contexts[-1][0])
    assert {f["id"] for f in client.get(path).json()["files"]} == {instrument["id"], dataset["id"]}
    other = new(client, store)
    assert turn(client, other, action="reuse", file_ids=[instrument["id"], dataset["id"]]).status_code == 200
    assert upload(client, other, "renombrado.pdf", original, "instrument")["id"] == instrument["id"]
    assert upload(client, other, "sintetico.csv", CSV)["id"] == dataset["id"]
    changed = upload(client, other, "sintetico.csv", CSV.replace(b"48.00", b"49.00"))
    assert changed["id"] != dataset["id"]
    root = f"/projects/{store.project_id}/files"
    assert len(client.get(root).json()) == 3
    assert client.get(root + "/" + instrument["id"] + "/download").content == original
    for name, data, role in [
        ("instrumento.docx", b"PK", "instrument"),
        ("invalido.pdf", b"no pdf", "instrument"),
        ("instrumento.pdf", original, "dataset"),
    ]:
        rejected = client.post(other + "/files", files={"file": (name, data)}, data={"file_role": role})
        assert rejected.status_code == 422 and rejected.json()["detail"]
    writer, out = PdfWriter(), io.BytesIO()
    writer.append(PdfReader(io.BytesIO(original)))
    writer.encrypt("clave-sintetica")
    writer.write(out)
    assert (
        client.post(
            other + "/files", files={"file": ("cifrado.pdf", out.getvalue())}, data={"file_role": "instrument"}
        ).status_code
        == 422
    )
    writer, out = PdfWriter(), io.BytesIO()
    writer.add_blank_page(width=595, height=842)
    writer.write(out)
    scanned = upload(client, other, "sin_texto.pdf", out.getvalue(), "instrument")
    assert scanned["metadata"]["text_excerpt"] == "" and "OCR" in str(scanned["metadata"]["warnings"])
    assert client.get(root + "/" + scanned["id"] + "/download").content == out.getvalue()
    assert client.get(root.replace(store.project_id, str(uuid4()))).status_code == 404


def test_explicit_numeric_confirmation_survives_planning_and_execution(local):
    client, store, provider = local
    path = new(client, store)
    turn(client, path, action="instrument_no")
    file = upload(client, path, "sintetico.csv", CSV)
    frozen = copy.deepcopy(file["metadata"])
    assert (
        next(c for c in frozen["profile"]["columns"] if c["name"] == "horas_estudio")["statistical_type"]
        == "categorical_or_ordinal"
    )
    proposed = proposal(file["id"], "pearson")
    for v in proposed["variables"]:
        if v["column"] == "tiempo_min":
            v["column"] = "horas_estudio"
    proposed["objective"] = "Relacionar puntaje y horas_estudio"
    proposed["method"] = "Pearson de puntaje y horas_estudio"
    provider.replies = [reply(proposals=[proposed], suggested_stage="proposal")]
    response = turn(
        client,
        path,
        content="Confirmo que `horas_estudio` es cuantitativa discreta. Quiero Pearson de puntaje con horas_estudio.",
    )
    assert response.status_code == 200, response.text
    stored = client.get(path).json()["proposals"][0]
    assert stored["analysis_plan"]["type_confirmations"][0]["statistical_type"] == "discrete"
    assert client.patch(path + "/proposals/" + stored["id"], json={"status": "accepted"}).status_code == 200
    job = job_for(CSV, "correlation", ["pearson"])
    job["plan"] = stored["analysis_plan"]
    job["files"][0].update(id=file["id"], metadata=frozen)
    ready = resolve(job)
    assert ready["status"] == "READY", ready
    decision = next(d for d in ready["specification"]["decisions"] if d["variable"]["column"] == "horas_estudio")
    assert decision["statistical_type"] == "discrete"
    calculated, _ = calculate(confirmed_job(job, ready))
    reference = stats.pearsonr([round(r[0], 2) for r in ROWS], [r[3] for r in ROWS])
    assert calculated["components"][0]["statistics"]["pairs"][0]["coefficient"] == pytest.approx(reference.statistic)
    assert store.data["project_files"][0]["metadata"] == frozen
    tampered = copy.deepcopy(ready["specification"])
    next(d for d in tampered["decisions"] if d["variable"]["column"] == "horas_estudio")["statistical_type"] = "nominal"
    tampered["decisions_confirmed"] = True
    with pytest.raises(AnalysisError):
        validate_spec(Plan.model_validate(job["plan"]), ExecutionSpec.model_validate(tampered))


def test_exclusions_and_conceptual_questions_are_not_requested_products():
    products, excluded, uncertain, _ = product_request("No quiero resúmenes globales, solo resúmenes por grupo.")
    assert products == {"grouped"} and excluded == {"global"} and not uncertain
    assert product_request("¿Qué es Pearson?") == (set(), set(), False, False)
    products, excluded, uncertain, _ = product_request(
        "ANOVA de Welch de puntaje según grupo sin comparaciones post hoc"
    )
    assert products == {"global_test"} and excluded == {"posthoc"} and not uncertain


def test_excluded_posthoc_cannot_be_enabled_in_advanced_execution():
    from app.services.plan_capabilities import validate_products

    job = job_for(CSV)
    plan = proposal(job["files"][0]["id"], "welch")
    plan["expected_outputs"].append("Sin comparaciones post hoc")
    spec = ExecutionSpec.model_validate(job["specification"])
    spec.decisions[0].variable.column = "puntaje"
    spec.decisions[1].variable.column = "grupo"
    spec.components[0].method = "welch_anova"
    spec.components[0].posthoc = "welch_holm"
    with pytest.raises(ValueError, match="exclusión"):
        validate_products(Plan.model_validate(plan), decisions=spec.decisions, execution_components=spec.components)


def test_numeric_codes_need_confirmation_and_identifiers_cannot_be_confirmed():
    from app.services.gemini import validate_plan
    from app.services.profiling import inspect_file

    fid = str(uuid4())
    metadata = inspect_file("datos.csv", CSV, "dataset", Settings(_env_file=None))
    files = [{"id": fid, "metadata": metadata, "file_role": "dataset"}]
    plan = proposal(fid, "pearson")
    plan["variables"][1]["column"] = "horas_estudio"
    plan.update(objective="Relacionar puntaje y horas_estudio", method="Pearson de puntaje y horas_estudio")
    with pytest.raises(ValueError):
        validate_plan(Plan.model_validate(plan), files, {"project_type": "general"})
    plan["type_confirmations"] = [{"variable": plan["variables"][1], "statistical_type": "discrete"}]
    validate_plan(Plan.model_validate(plan), files, {"project_type": "general"})
    next(c for c in metadata["profile"]["columns"] if c["name"] == "horas_estudio")["possible_identifier"] = True
    with pytest.raises(ValueError):
        validate_plan(Plan.model_validate(plan), files, {"project_type": "general"})


def test_budget_retry_after_rejections_and_separate_providers(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.services.provider_runtime.time.monotonic", lambda: now[0])
    settings = Settings(_env_file=None, ai_requests_per_minute=2, ai_max_requests_per_turn=2)
    gemini, terra_budget = RequestBudget(settings), RequestBudget(settings)
    gemini.reserve()
    now[0] += 10
    gemini.reserve()
    with pytest.raises(HTTPException) as exc:
        gemini.reserve()
    assert exc.value.headers["Retry-After"] == "50" and len(gemini.requests) == 2
    terra_budget.reserve()
    assert len(terra_budget.requests) == 1
    token = current_trace.set({"requests": 2})
    try:
        with pytest.raises(HTTPException) as exc:
            terra_budget.reserve()
        assert exc.value.headers["X-Statia-Error"] == "provider_request_limit"
        assert "Retry-After" not in exc.value.headers and len(terra_budget.requests) == 1
    finally:
        current_trace.reset(token)
    now[0] = 160
    gemini.reserve()
    assert len(gemini.requests) == 2


def test_natural_clarification_and_negated_method_preserve_scope():
    from app.models.chat import Turn
    from app.services.requested_scope import requested_scope, validate_plan_scope

    turn = Turn(request_id=uuid4(), content="Quiero solo descriptiva global de puntaje")
    scope = requested_scope(
        {"stage_data": {"requested_scope": {"version": 1, "products": [], "unresolved": True}}}, [], turn
    )
    assert scope["products"] == ["global"] and not scope["unresolved"]
    fid = str(uuid4())
    from app.services.profiling import inspect_file

    files = [
        {"id": fid, "file_role": "dataset", "metadata": inspect_file("d.csv", CSV, "dataset", Settings(_env_file=None))}
    ]
    plan = proposal(fid, "welch")
    plan["method"] += ", sin comparaciones post hoc"
    validate_plan_scope(
        Plan.model_validate(plan),
        {"products": ["global_test"], "excluded_products": ["posthoc"], "unresolved": False},
        files,
    )
