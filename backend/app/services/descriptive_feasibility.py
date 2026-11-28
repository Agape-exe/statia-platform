"""Bloqueos conocidos del descriptivo, previos a aceptación; no calcula ni recorta planes."""

from app.services.planning_errors import PlanningError


def validate_descriptive_feasibility(plan, column_for):
    from app.services.statistics.preparation import plan_filters, sources

    scoped = bool(plan_filters(plan) or plan.comparison and plan.comparison.strata)
    steps = sources(plan)
    problems = []
    for step in steps:
        if step.procedure not in {"descriptive", "exploratory"}:
            continue
        for variable in step.variables:
            column = column_for(variable)
            name = variable.column
            if column.get("possible_identifier") or column.get("statistical_type") == "identifier":
                problems.append(
                    f"«{name}» es un identificador; el descriptivo de identificadores no está implementado."
                )
            elif column.get("possible_temporal") or column.get("statistical_type") == "temporal":
                problems.append(
                    f"«{name}» es temporal, no una medida cuantitativa; este catálogo no implementa su descriptivo temporal."
                )
            elif not scoped:
                if variable.role == "group" and column["unique"] > 20:
                    problems.append(f"«{name}» supera los 20 grupos admitidos por componente descriptivo.")
                elif (
                    variable.role != "group"
                    and column.get("statistical_type") != "quantitative"
                    and column["unique"] > 100
                ):
                    problems.append(
                        f"«{name}» tiene {column['unique']} categorías y supera el límite descriptivo de 100."
                    )
    if problems:
        raise PlanningError(
            "variable_type",
            " ".join(dict.fromkeys(problems))
            + " Reformula el plan con productos ejecutables. No omitas variables o productos pedidos expresamente: explica la limitación y pide una decisión de alcance.",
        )
