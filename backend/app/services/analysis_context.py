"""Resumen agregado para preguntas posteriores; jamás envía filas originales al proveedor."""

import json
import math
import re

from app.models.analysis import AnalysisResult
from app.services.planning_errors import PlanningError
from app.services.profiling import SENSITIVE

PRIVATE_VALUE = re.compile(
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b|(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)",
    re.I,
)


def safe_text(value):
    return PRIVATE_VALUE.sub("[valor omitido]", str(value))[:600]


def safe_aggregate(value):
    if isinstance(value, str):
        return safe_text(value)
    if isinstance(value, dict):
        return {safe_text(k): safe_aggregate(v) for k, v in value.items() if not PRIVATE_VALUE.search(str(k))}
    if isinstance(value, list):
        return [safe_aggregate(v) for v in value]
    return value


def result_tables(component, question):
    """Tablas calculadas agregadas; nunca observaciones ni etiquetas identificadoras."""
    tables = []
    for table in component.tables[:6]:
        rows = []
        for row in table.rows:
            label = str(row.get("Variable / grupo", row.get("Variable", "")))
            if SENSITIVE.search(label.split(" / ")[0]) or any(
                isinstance(v, str) and PRIVATE_VALUE.search(v) for v in row.values()
            ):
                continue
            if "Categoría" in row and (
                len(str(row["Categoría"])) > 80 or len({str(r.get("Categoría")) for r in table.rows}) > 20
            ):
                continue
            rows.append(
                {
                    k: safe_text(v) if isinstance(v, str) else v
                    for k, v in row.items()
                    if isinstance(v, (str, int, float, bool)) or v is None
                }
            )
        rows.sort(
            key=lambda row: (
                not any(
                    str(value).casefold() in question.casefold()
                    for key, value in row.items()
                    if key in {"Variable", "Variable / grupo", "Categoría"} and len(str(value)) > 1
                )
            )
        )
        selected = rows[: 20 if "Frecuencia" in table.columns else 12]
        tables.append(
            {"title": safe_text(table.title), "rows": selected, "rows_omitted": len(table.rows) - len(selected)}
        )
    return tables


async def saved_results_context(store, conversation, question=""):
    ids = re.findall(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", question, re.I)
    filters = {
        "conversation_id": conversation["id"],
        "project_id": conversation["project_id"],
        "status": ["completed", "partial", "failed"],
    }
    if ids:
        filters["id"] = ids[:3]
    rows = await store.rows(
        "analysis_runs",
        filters,
        order="created_at.asc"
        if re.search(
            r"primer[oa]?\s+(?:an[aá]lisis|resultado|ejecuci[oó]n)|(?:resultado|an[aá]lisis|ejecuci[oó]n)\s+(?:m[aá]s\s+)?antigu",
            question,
            re.I,
        )
        and not ids
        else "created_at.desc",
        limit=3,
        select="id,title,created_at,status,result,error",
    )
    summaries = []
    for row in rows:
        if row.get("result") is None and row["status"] == "failed":
            failure = {
                "run_id": row["id"],
                "title": safe_text(row["title"]),
                "date": row["created_at"],
                "status": "failed",
                "error": safe_text(row.get("error") or "La ejecución falló sin resultados persistidos."),
                "components": [],
                "component_states": [],
            }
            if len(json.dumps(summaries + [failure], ensure_ascii=False)) <= 16000:
                summaries.append(failure)
            continue
        try:
            result = AnalysisResult.model_validate(row["result"])
        except (ValueError, TypeError):
            continue  # No usar JSON alterado o incompatible como evidencia numérica.

        def relevant(item):
            return any(
                len(str(value)) > 1 and str(value).casefold() in question.casefold()
                for name, value in item.items()
                if name in {"group_1", "group_2", "variable_x", "variable_y"}
            )

        components = []
        ordered = sorted(
            result.components, key=lambda c: not any(str(v).casefold() in question.casefold() for v in c.scope.values())
        )
        for c in ordered[:8]:
            sensitive_group = any(v.role == "group" and SENSITIVE.search(v.column) for v in c.variables)
            metrics = dict(c.statistics)
            for field in ["pairs", "posthoc"]:
                if field in metrics:
                    values = metrics[field]
                    metrics[field] = sorted(values, key=lambda item: not relevant(item))[:6]
                    metrics[f"{field}_available_count"] = len(values)
                    metrics[f"{field}_omitted_count"] = max(0, len(values) - 6)
            tables = [] if sensitive_group else result_tables(c, question)
            components.append(
                {
                    "method": c.method,
                    "scope": {} if sensitive_group else {k: safe_text(v) for k, v in c.scope.items()},
                    "variables": [safe_text(v.column) for v in c.variables],
                    "grouping": [safe_text(v.column) for v in c.variables if v.role == "group"],
                    "sample": {} if sensitive_group else safe_aggregate(c.sample),
                    "statistics": {} if sensitive_group else safe_aggregate(metrics),
                    "status": c.status,
                    "error": safe_text(c.error) if c.error else None,
                    "tables": tables,
                    "warnings": [safe_text(w) for w in c.warnings[:4]],
                    "assumptions": [safe_aggregate(a.model_dump(mode="json")) for a in c.assumptions[:6]],
                    "tables_omitted": max(0, len(c.tables) - len(tables)),
                }
            )
        summary = {
            "run_id": row["id"],
            "title": safe_text(row["title"]),
            "date": row["created_at"],
            "status": row["status"],
            "proposal_id": str(result.proposal_id),
            "files": [{"id": f.get("id"), "sheet": f.get("sheet"), "sha256": f.get("sha256")} for f in result.files],
            "confidence_level": result.specification.confidence_level,
            "multiplicity": result.specification.multiplicity,
            "components": components,
            "components_omitted": max(0, len(result.components) - 8),
            "component_states": [
                {
                    "source_index": c.source_index,
                    "method": c.method,
                    "status": c.status,
                    "variables": [v.column for v in c.variables],
                    "blockers": [safe_text(b) for b in c.blockers[:2]],
                    "completed_run_id": c.completed_run_id,
                }
                for c in result.component_states
            ],
        }
        if not result.component_states:
            declared = result.plan_snapshot.get("components") or [result.plan_snapshot]
            completed = {c.source_index for c in result.components if c.status == "completed"}
            summary["component_states"] = [
                {
                    "source_index": i,
                    "method": s.get("method", "Procedimiento histórico"),
                    "status": "COMPLETED" if i in completed else "NOT_CALCULATED",
                    "blockers": []
                    if i in completed
                    else ["El resultado histórico no registra un cálculo completado ni su motivo metodológico."],
                }
                for i, s in enumerate(declared)
            ]
        if len(json.dumps(summary, ensure_ascii=False)) > 14000:
            for component in components:
                component.pop("tables", None)
                component["context_limited"] = True
        if len(json.dumps(summaries + [summary], ensure_ascii=False)) <= 16000:
            summaries.append(summary)
    return summaries


def validate_numeric_claims(text, context):
    validate_descriptive_claims(text, context)
    if (context or {}).get("result_discussion") and not any(
        c.get("method") != "descriptive" and c.get("status") in {"completed", "partial"}
        for r in context.get("analysis_results", [])
        for c in r["components"]
    ):
        for sentence in re.split(r"[.;!?]|\bpero\b|\bsin embargo\b", text, flags=re.I):
            if re.search(
                r"estad[ií]sticamente significativ|diferencias? significativ|rechaz[ae]r? la hip[oó]tesis|demuestra causalidad|prueba causalidad",
                sentence,
                re.I,
            ) and not re.search(
                r"\bno (?:se (?:puede|ha|ejecut)|podemos|puede|permite|es posible|demuestra|prueba)|sin (?:poder|inferencia)",
                sentence,
                re.I,
            ):
                raise PlanningError(
                    "response_content",
                    "Solo hay resultados descriptivos disponibles. No atribuyas significación, rechazo de hipótesis o causalidad a procedimientos no ejecutados.",
                )
    claims = list(
        re.finditer(
            r"(?i)\b(p|t|f|r|rho|d|g|chi2|χ²|h|u|w|v|d_z)\s*(?:\([^)]{0,40}\))?\s*(=|<)\s*([-+]?\d*[.,]?\d+(?:e[-+]?\d+)?)",
            text,
        )
    )
    if not claims:
        return
    results = (context or {}).get("analysis_results", [])
    if not results:
        raise PlanningError(
            "response_content",
            "No presentes estadísticos inferenciales calculados: solo se preparan planes cuando no hay resultados guardados.",
        )
    values = {name: [] for name in ["p", "t", "f", "r", "rho", "d", "g", "chi2", "χ²", "h", "u", "w", "v", "d_z"]}
    for result in results:
        for component in result["components"]:
            metrics = component["statistics"]
            for symbol, name in [
                ("p", "p"),
                ("p", "p_adjusted"),
                ("t", "t"),
                ("f", "F"),
                ("d", "cohen_d"),
                ("g", "hedges_g"),
                ("chi2", "chi2"),
                ("χ²", "chi2"),
                ("h", "H"),
                ("u", "U"),
                ("w", "W"),
                ("v", "cramers_v"),
                ("d_z", "cohen_dz"),
            ]:
                if isinstance(metrics.get(name), (int, float)):
                    values[symbol].append(metrics[name])
            for pair in metrics.get("pairs", []) + metrics.get("posthoc", []):
                for symbol, name in [("p", "p_holm"), ("t", "t"), ("d", "cohen_d"), ("g", "hedges_g")]:
                    if isinstance(pair.get(name), (int, float)):
                        values[symbol].append(pair[name])
                for symbol, name in [
                    ("p", "p"),
                    ("p", "p_adjusted"),
                    ("r" if component["method"] == "pearson" else "rho", "coefficient"),
                ]:
                    if isinstance(pair.get(name), (int, float)):
                        values[symbol].append(pair[name])
    for claim in claims:
        symbol, operator, literal = claim.groups()
        literal = literal.replace(",", ".")
        number = float(literal)
        decimals = len(literal.lower().split("e")[0].split(".")[1]) if "." in literal else 0
        exponent = int(literal.lower().split("e")[1]) if "e" in literal.lower() else 0
        tolerance = 0.500001 * 10.0 ** min(300, max(-300, exponent - decimals))
        valid = any(
            (v < number if operator == "<" else math.isclose(v, number, rel_tol=1e-7, abs_tol=tolerance))
            for v in values[symbol.lower()]
        )
        if symbol.lower() == "p" and operator == "=" and number == 0:
            valid = False  # No presentar p = 0.000, incluso si hubo underflow de float64.
        if not valid:
            raise PlanningError(
                "response_content",
                "La explicación incluye una cifra inferencial que no coincide con los resultados guardados. Usa solo valores calculados y su redondeo correcto.",
            )


def matches_rounded(literal, values):
    literal = literal.replace(",", ".").lower()
    coefficient, _, exponent = literal.partition("e")
    decimals = len(coefficient.split(".")[1]) if "." in coefficient else 0
    tolerance = 0.500001 * 10.0 ** min(300, max(-300, int(exponent or 0) - decimals))
    number = float(literal)
    return any(math.isclose(number, value, rel_tol=1e-7, abs_tol=tolerance) for value in values)


def validate_descriptive_claims(text, context):
    results = (context or {}).get("analysis_results", [])
    if not results:
        return
    rows = [
        row
        for result in results
        for component in result["components"]
        for table in component.get("tables", [])
        for row in table["rows"]
    ]
    metrics = {
        "media": "Media",
        "promedio": "Media",
        "mediana": "Mediana",
        "desviación estándar": "DE muestral",
        "desviacion estandar": "DE muestral",
        "varianza": "Varianza muestral",
        "mínimo": "Mínimo",
        "máximo": "Máximo",
        "frecuencia": "Frecuencia",
        "porcentaje": "Porcentaje válido",
    }
    number = r"([-+]?\d+(?:[.,]\d+)?(?:e[-+]?\d+)?)"
    for match in re.finditer(r"(?i)\b(" + "|".join(metrics) + r")\s*(?:es|fue|de|=|:)\s*" + number, text):
        metric, literal = match.groups()
        values = [
            row[metrics[metric.lower()]] for row in rows if isinstance(row.get(metrics[metric.lower()]), (int, float))
        ]
        if not matches_rounded(literal, values):
            raise PlanningError(
                "response_content",
                "La cifra descriptiva no coincide con las tablas agregadas disponibles. Cita únicamente valores guardados, sin calcular ni inventar agregados.",
            )
    for match in re.finditer(number + r"\s*%", text, re.I):
        literal = match.group(1)
        percentages = [
            row["Porcentaje válido"] for row in rows if isinstance(row.get("Porcentaje válido"), (int, float))
        ] + [r["confidence_level"] * 100 for r in results if isinstance(r.get("confidence_level"), (int, float))]
        if not matches_rounded(literal, percentages):
            raise PlanningError(
                "response_content",
                "El porcentaje no está disponible en los resultados agregados. No lo recalcules a partir de filas o frecuencias.",
            )
