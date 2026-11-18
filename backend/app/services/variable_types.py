"""Confirmaciones por referencia exacta; nunca convertir códigos automáticamente."""

import copy
import re

from app.services.planning_errors import PlanningError


def confirmed_files(plan, files):
    if not plan.type_confirmations:
        return files
    result = copy.deepcopy(files)
    seen = set()
    for decision in plan.type_confirmations:
        v = decision.variable
        key = v.file_id, v.sheet, v.column
        if key in seen or key not in {(x.file_id, x.sheet, x.column) for x in plan.variables}:
            raise PlanningError("variable_type", "La confirmación debe referirse a una variable única del plan.")
        seen.add(key)
        file = next(
            (f for f in result if f["id"] == v.file_id and f["metadata"].get("selected_sheet") == v.sheet), None
        )
        column = next(
            (
                c
                for c in (file or {}).get("metadata", {}).get("profile", {}).get("columns", [])
                if c["name"] == v.column
            ),
            None,
        )
        if (
            not column
            or column["physical_type"] != "numeric"
            or column.get("possible_identifier")
            or column.get("possible_temporal")
        ):
            raise PlanningError(
                "variable_type", "Solo pueden confirmarse medidas numéricas; no identificadores ni fechas."
            )
        column["statistical_type"] = "quantitative"
    return result


def capture_confirmations(content, files, previous):
    decisions = {(d["variable"]["file_id"], d["variable"]["sheet"], d["variable"]["column"]): d for d in previous}
    # Una forma deliberadamente explícita. Si el nombre existe en varias tablas,
    # se pide desambiguar en vez de aplicar la decisión globalmente.
    for match in re.finditer(r"confirmo que `([^`]+)` es cuantitativa (discreta|continua)\b", content, re.IGNORECASE):
        name, kind = match.groups()
        candidates = [
            (f, c)
            for f in files
            if f["file_role"] == "dataset"
            for c in f["metadata"].get("profile", {}).get("columns", [])
            if c["name"] == name
        ]
        if len(candidates) != 1:
            raise PlanningError(
                "variable_type",
                "La columna debe existir en un único archivo asociado para confirmar su tipo desde el chat.",
            )
        file, column = candidates[0]
        if column["physical_type"] != "numeric" or column.get("possible_identifier") or column.get("possible_temporal"):
            raise PlanningError(
                "variable_type",
                "La columna debe contener valores numéricos y no representar identificadores ni fechas.",
            )
        variable = {
            "file_id": file["id"],
            "sheet": file["metadata"]["selected_sheet"],
            "column": name,
            "role": "description",
        }
        decisions[(file["id"], variable["sheet"], name)] = {
            "variable": variable,
            "statistical_type": "discrete" if kind.lower() == "discreta" else "continuous",
        }
    return list(decisions.values())


def bind_confirmations(reply, decisions, files):
    from app.models.chat import TypeConfirmation

    for plan in reply.proposals:
        selected = {(v.file_id, v.sheet, v.column): v for v in plan.variables}
        plan.type_confirmations = [
            TypeConfirmation(variable=selected[key], statistical_type=d["statistical_type"])
            for d in decisions
            if (key := (d["variable"]["file_id"], d["variable"]["sheet"], d["variable"]["column"])) in selected
        ]
        confirmed_files(plan, files)
    return type(reply).model_validate(reply.model_dump())
