"""Despachador cerrado y reproducible; usado exclusivamente en el proceso acotado."""

import base64
import hashlib
import math
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from types import SimpleNamespace

from app.core.config import Settings
from app.models.analysis import AnalysisResult, ExecutionSpec
from app.models.chat import Plan
from app.services.statistics.common import inference_text, table
from app.services.statistics.numerics import holm
from app.services.statistics.preparation import (
    Prepared,
    active_spec,
    component_order,
    key,
    prepare,
    require,
    sources,
    validate_spec,
)
from app.services.statistics.procedures import run_component


def finite_json(value, warnings):
    if isinstance(value, float) and not math.isfinite(value):
        warnings.add(
            "Un valor numérico no finito no es calculable y se registró como null; revisa magnitud, constantes y supuestos."
        )
        return None
    if isinstance(value, dict):
        return {k: finite_json(v, warnings) for k, v in value.items()}
    if isinstance(value, list):
        return [finite_json(v, warnings) for v in value]
    return value


def calculate(job):
    plan = Plan.model_validate(job["plan"])
    spec = ExecutionSpec.model_validate(job["specification"])
    validate_spec(plan, spec)
    preparation = None
    if job.get("preparation_fingerprint"):
        from app.services.statistics.automatic import assess

        preparation = assess({**job, **job["preparation_context"]})
        require(
            preparation["status"] in {"READY", "PARTIALLY_READY"}
            and preparation["fingerprint"] == job["preparation_fingerprint"],
            "Los datos o decisiones cambiaron. Vuelve a preparar el análisis antes de ejecutarlo.",
        )
        expected = spec.model_dump(mode="json")
        expected["decisions_confirmed"] = False
        require(
            expected == preparation["specification"], "La especificación no coincide con los componentes preparados."
        )
    require(
        not spec.partial_execution or preparation is not None,
        "La ejecución selectiva requiere una preparación vigente.",
    )
    settings = Settings(_env_file=None, **job.get("limits", {}))
    prepared, provenance = {}, []
    required_files = {v.file_id for v in plan.variables}
    require(
        required_files == {f["id"] for f in job["files"]},
        "Los originales no corresponden a todas las variables del plan.",
    )
    for file in job["files"]:
        data = base64.b64decode(file["data"], validate=True)
        prepared[file["id"]] = prepare(file, data, active_spec(plan, spec), settings)
        provenance.append(
            {
                "id": file["id"],
                "name": file["original_name"],
                "sheet": file["metadata"]["selected_sheet"],
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "initial_rows": prepared[file["id"]].initial,
            }
        )
    if job.get("review_conditions"):
        from app.services.statistics.automatic import check_conditions

        check_conditions(plan, spec, prepared)
    results, resources = [], {}
    original_sources = sources(plan)
    selected = {c.source_index: c for c in spec.components}
    for index in component_order(plan):
        if index not in selected:
            continue
        component = selected[index]
        source = original_sources[component.source_index]
        dependencies = getattr(source, "depends_on", [])
        previous = {c["source_index"] for c in (preparation or {}).get("components", []) if c["status"] == "COMPLETED"}
        completed = {
            r.source_index
            for r in results
            if r.status == "completed"
            and all(x.status == "completed" for x in results if x.source_index == r.source_index)
        }
        if not set(dependencies) <= previous | completed:
            continue
        # Descriptivos de varios archivos son independientes; nunca se unen filas.
        for file_id in sorted({v.file_id for v in source.variables}):
            dataset = prepared[file_id]
            subset = SimpleNamespace(variables=[v for v in source.variables if v.file_id == file_id])
            strata = (
                plan.comparison.strata
                if plan.comparison and component.method in {"student_t", "welch_t", "mann_whitney"}
                else None
            )
            if strata:
                require(strata.variable.file_id == file_id, "Los estratos deben pertenecer a la misma tabla.")
                require(
                    key(strata.variable) in {key(d.variable) for d in spec.decisions},
                    "El estrato carece de decisión de datos.",
                )
            for level in strata.values if strata else [None]:
                current = dataset
                scope = {}
                if strata:
                    rows = [row for row in dataset.rows if str(row[strata.variable.column]) == level]
                    current = Prepared(
                        dataset.file_id,
                        dataset.sheet,
                        dataset.initial,
                        rows,
                        dataset.decisions,
                        dataset.initial - len(rows),
                    )
                    scope = {strata.variable.column: level}
                result, charts = run_component(
                    subset, current, component, spec, f"componente_{len(results) + 1}", scope
                )
                results.append(result)
                resources.update(charts)
    # Familia explícita: todos los contrastes inferenciales calculados de la ejecución.
    tests = []
    for result in results:
        if result.status == "failed":
            continue
        if "p" in result.statistics:
            tests.append((result, result.statistics))
        tests.extend((result, pair) for pair in result.statistics.get("pairs", []) if pair.get("p") is not None)
    adjusted = (
        holm([test["p"] for _, test in tests]) if spec.multiplicity == "holm" else [test["p"] for _, test in tests]
    )
    for (result, test), p_adjusted in zip(tests, adjusted):
        test["p_adjusted"] = p_adjusted
        test["multiplicity"] = spec.multiplicity
    if spec.multiplicity == "holm":
        for result in results:
            family = [test for owner, test in tests if owner is result]
            if family:
                result.tables.append(
                    table(
                        "Familia de contrastes: ajuste de Holm",
                        [
                            {
                                "Contraste": f"{test.get('variable_x', result.title)} / {test.get('variable_y', ', '.join(f'{k}: {v}' for k, v in result.scope.items()) or 'comparación global')}",
                                "p sin ajuste": test["p"],
                                "p Holm": test["p_adjusted"],
                                "Contrastes en la familia": len(tests),
                            }
                            for test in family
                        ],
                    )
                )
                result.interpretation = (
                    "Los valores p sin ajuste permanecen en las tablas. Para esta familia confirmada se usa Holm. "
                    + " ".join(inference_text(test["p_adjusted"], 1 - spec.confidence_level) for test in family)
                    + " Los efectos y los intervalos individuales permanecen sin ajuste simultáneo. No se demuestra causalidad."
                )
    elif len(tests) > 1:
        for result in results:
            result.warnings.append(
                f"{len(tests)} contrastes inferenciales sin ajuste de multiplicidad por decisión confirmada; aumenta el riesgo de falsos positivos."
            )
    successful = sum(r.status != "failed" for r in results)
    status = (
        "completed"
        if results and all(r.status == "completed" for r in results)
        else "partial"
        if successful
        else "failed"
    )
    states = preparation["components"] if preparation else []
    for state in states:
        calculated = [r for r in results if r.source_index == state["source_index"]]
        if calculated:
            state["status"] = "COMPLETED" if all(r.status == "completed" for r in calculated) else "FAILED"
            if state["status"] == "COMPLETED":
                state["completed_run_id"] = job["run_id"]
        elif state["source_index"] in selected and state["depends_on"]:
            state["status"] = "NEEDS_CLARIFICATION"
            state["blockers"].append("Una dependencia no terminó correctamente; este componente no se calculó.")
    if states and any(s["status"] != "COMPLETED" for s in states) and successful:
        status = "partial"
    result = AnalysisResult(
        run_id=job["run_id"],
        project_id=job["project_id"],
        conversation_id=job["conversation_id"],
        proposal_id=job["proposal_id"],
        created_at=datetime.now(timezone.utc),
        title=plan.title,
        specification=spec,
        plan_snapshot=job["plan"],
        files=provenance,
        dependencies={
            "python": platform.python_version(),
            **{name: version(name) for name in ["numpy", "scipy", "matplotlib", "openpyxl"]},
        },
        components=results,
        component_states=states,
        status=status,
        summary=(
            f"{sum(s['status'] == 'COMPLETED' for s in states)} de {len(states)} componentes del plan completados. "
            if states
            else f"{successful} de {len(results)} componentes con resultados. "
        )
        + (
            "Quedan componentes pendientes que no se calcularon; consulta sus motivos y revisa las aclaraciones para continuar. "
            if status == "partial" and states and all(r.status == "completed" for r in results)
            else "Hay componentes fallidos o parcialmente calculables; revisa los motivos antes de concluir. "
            if status != "completed"
            else ""
        )
        + "¿Tienes alguna duda o pregunta respecto a los resultados que hemos obtenido?",
    )
    # JSON estricto incluso ante valores extremos provenientes de bibliotecas externas.
    data = result.model_dump(mode="json")
    for component in data["components"]:
        warnings = set()
        cleaned = finite_json(component, warnings)
        component.clear()
        component.update(cleaned)
        component["warnings"].extend(sorted(warnings))
        if warnings and component["status"] == "completed":
            component["status"] = "partial"
            component["warnings"].append(
                "La ejecución terminó, pero algunas medidas se registraron como no calculables; consulta null y advertencias."
            )
    if any(c["status"] == "partial" for c in data["components"]):
        data["status"] = "partial"
        if result.status == "completed":
            data["summary"] = "Hay medidas numéricas no calculables; consulta sus advertencias. " + data["summary"]
    return data, resources
