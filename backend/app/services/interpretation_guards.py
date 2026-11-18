"""Controles finitos sobre afirmaciones observadas; no sustituyen revisión científica."""

import re

from app.services.plan_capabilities import normalized
from app.services.planning_errors import PlanningError

UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"


def result_ids(context):
    ids = set()
    for result in (context or {}).get("analysis_results", []):
        ids.add(result.get("run_id"))
        ids.update(c.get("completed_run_id") for c in result.get("component_states", []))
    return {value for value in ids if isinstance(value, str) and re.fullmatch(UUID, value, re.I)}


def validate_explanation(text, context):
    context = context or {}
    literal = normalized(text)
    known = result_ids(context)
    for match in re.finditer(r"\brun_id`?\s*[:=]?\s*`?(" + UUID + r")", text, re.I):
        if match[1] not in known:
            raise PlanningError(
                "response_content",
                "No inventes identificadores de ejecución. Usa método y fecha disponibles u omite la referencia.",
            )
    if re.search(
        r"run_id`?\s*[:=]?\s*`?(?:archivo del proyecto|\[valor omitido\]|<[^>]+>|pendiente|desconocido)", literal
    ):
        raise PlanningError("response_content", "Omite marcadores de posición: no identifican una ejecución real.")
    if context.get("project_mode") == "thesis" and not context.get("research_context"):
        for sentence in re.split(r"[.!?\n]", literal):
            if (
                re.search(r"he (?:registrado|guardado|actualizado) (?:tu |el )?(?:objetivo|contexto)", sentence)
                and "conversacion" not in sentence
                and not re.search(r"\bno\b", sentence)
            ):
                raise PlanningError(
                    "response_content",
                    "Aclara que el objetivo solo se considera en esta conversación y no está guardado en el módulo Contexto.",
                )
    if not context.get("analysis_results"):
        return
    has_skewness = any(
        "skewness" in c.get("statistics", {})
        or any(
            any(
                "asimetr" in normalized(column) or "skewness" in normalized(column)
                for column in table.get("columns", [])
            )
            for table in c.get("tables", [])
        )
        for result in context["analysis_results"]
        for c in result.get("components", [])
    )
    if not has_skewness:
        for sentence in re.split(r"[.!?\n]", literal):
            if (
                re.search(r"asimetr", sentence)
                and re.search(r"evidencia|demuestra|confirma", sentence)
                and not re.search(r"\bno\b|insuficiente|no basta|no permite|podria|requiere|sin evidencia", sentence)
            ):
                raise PlanningError(
                    "response_content",
                    "La media y la mediana no confirman asimetría ni su intensidad. Distingue la hipótesis de un hecho calculado y no inventes medidas.",
                )
