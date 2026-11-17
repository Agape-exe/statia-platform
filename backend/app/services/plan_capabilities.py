"""Avisos conservadores del catálogo real; no interpretar exhaustivamente prosa libre."""

from app.models.chat import AssistantReply


def descriptive_warnings(plan):
    steps = plan.components if plan.procedure == "integral" else [plan]
    if any(
        step.procedure in ("descriptive", "exploratory") and any(v.role == "group" for v in step.variables)
        for step in steps
    ):
        return [
            "Alcance descriptivo: cada componente agrupado produce resúmenes por grupo. "
            "No añade simultáneamente un resumen global ni frecuencias de la columna usada como agrupador. "
            "Si esos productos aparecen en la propuesta, no están cubiertos por ese componente: "
            "solicita planes separados y revísalos antes de ejecutar."
        ]
    return []


def warn_capabilities(reply):
    data = reply.model_dump(mode="json")
    warnings = []
    for plan, serialized in zip(reply.proposals, data["proposals"]):
        for warning in descriptive_warnings(plan):
            if not any(warning in item for item in serialized["limitations"]):
                # Conservar todas las limitaciones previas incluso al alcanzar el máximo del contrato.
                serialized["limitations"][0] += " " + warning
            if warning not in warnings:
                warnings.append(warning)
    if warnings:
        combined = " ".join(warnings)
        if any(combined in item for item in data["warnings"]):
            return AssistantReply.model_validate(data)
        if data["warnings"]:
            data["warnings"][0] = combined + " " + data["warnings"][0]
        else:
            data["warnings"] = [combined]
    return AssistantReply.model_validate(data)
