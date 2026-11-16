"""Resumen agregado para preguntas posteriores; jamás envía filas originales al proveedor."""

import json
import math
import re

from app.models.analysis import AnalysisResult
from app.services.planning_errors import PlanningError


async def saved_results_context(store, conversation, question=""):
    rows = await store.rows(
        "analysis_runs",
        {
            "conversation_id": conversation["id"],
            "project_id": conversation["project_id"],
            "status": ["completed", "partial"],
        },
        order="created_at.desc",
        limit=3,
        select="id,title,created_at,status,result",
    )
    summaries = []
    for row in rows:
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
            metrics = dict(c.statistics)
            for field in ["pairs", "posthoc"]:
                if field in metrics:
                    values = metrics[field]
                    metrics[field] = sorted(values, key=lambda item: not relevant(item))[:6]
                    metrics[f"{field}_available_count"] = len(values)
                    metrics[f"{field}_omitted_count"] = max(0, len(values) - 6)
            # Solo tablas numéricas agregadas; nunca categorías de tablas de frecuencias o filas originales.
            tables = [
                {"title": t.title, "rows": t.rows[:8], "rows_omitted": max(0, len(t.rows) - 8)}
                for t in c.tables[:2]
                if "Frecuencias" not in t.title and "frecuencias" not in t.title
            ]
            components.append(
                {
                    "method": c.method,
                    "scope": c.scope,
                    "variables": [v.column for v in c.variables],
                    "sample": c.sample,
                    "statistics": metrics,
                    "status": c.status,
                    "error": c.error,
                    "tables": tables,
                    "warnings": c.warnings[:4],
                }
            )
        summary = {
            "run_id": row["id"],
            "title": row["title"],
            "date": row["created_at"],
            "status": row["status"],
            "confidence_level": result.specification.confidence_level,
            "multiplicity": result.specification.multiplicity,
            "components": components,
            "components_omitted": max(0, len(result.components) - 8),
        }
        if len(json.dumps(summary, ensure_ascii=False)) > 14000:
            for component in components:
                component.pop("tables", None)
        if len(json.dumps(summaries + [summary], ensure_ascii=False)) <= 16000:
            summaries.append(summary)
    return summaries


def validate_numeric_claims(text, context):
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
