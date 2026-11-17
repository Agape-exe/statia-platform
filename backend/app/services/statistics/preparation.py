"""Relectura acotada y decisiones locales a la ejecución; nunca escribe originales."""

import csv
import io
import json
from dataclasses import dataclass
from datetime import date, datetime

from openpyxl import load_workbook

from app.models.analysis import ExecutionSpec
from app.models.chat import Plan
from app.services.profiling import inspect_file, numeric
from app.services.statistics.catalog import CATALOG

QUANTITATIVE = {"continuous", "discrete"}
CATEGORICAL = {"nominal", "binary", "ordinal"}
COMPARISONS = {"student_t", "welch_t", "anova", "welch_anova"}
INDEPENDENT_GROUPS = COMPARISONS | {"mann_whitney", "kruskal"}


class AnalysisError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AnalysisError(message)


def key(variable):
    return variable.file_id, variable.sheet, variable.column


def sources(plan):
    return plan.components if plan.procedure == "integral" else [plan]


def component_order(plan):
    pending = set(range(len(sources(plan))))
    ordered = []
    while pending:
        ready = sorted(i for i in pending if set(getattr(sources(plan)[i], "depends_on", [])) <= set(ordered))
        require(
            bool(ready),
            "Las dependencias del plan son cíclicas o apuntan a componentes inexistentes. Revisa la propuesta.",
        )
        ordered.extend(ready)
        pending.difference_update(ready)
    return ordered


def plan_filters(plan):
    legacy = plan.comparison.filters if plan.comparison else []
    require(
        not plan.filters or not legacy or plan.filters == legacy,
        "El plan contiene filtros contradictorios. Solicita una propuesta revisada.",
    )
    return plan.filters or legacy


def active_spec(plan, spec):
    """Decisiones de las columnas usadas; las demás se conservan en la auditoría."""
    active = {key(v) for c in spec.components for v in sources(plan)[c.source_index].variables}
    active.update(key(f.variable) for f in spec.filters)
    if plan.comparison and plan.comparison.strata:
        active.add(key(plan.comparison.strata.variable))
    return spec.model_copy(update={"decisions": [d for d in spec.decisions if key(d.variable) in active]})


def validate_spec(plan: Plan, spec: ExecutionSpec, *, require_confirmation=True):
    from app.services.plan_capabilities import validate_products
    from app.services.planning_errors import PlanningError

    try:
        validate_products(plan, decisions=spec.decisions, execution_components=spec.components)
    except PlanningError as exc:
        raise AnalysisError(str(exc)) from None
    if require_confirmation:
        require(spec.decisions_confirmed, "Confirma las decisiones de ejecución antes de calcular.")
    require(not plan.joins, "Las uniones entre tablas no están implementadas. Solicita análisis separados.")
    components = sources(plan)
    component_order(plan)
    require(bool(components), "El plan integral antiguo no declara componentes. Solicita una propuesta actualizada.")
    require(
        (
            len({c.source_index for c in spec.components}) == len(spec.components)
            and all(c.source_index < len(components) for c in spec.components)
            and (
                spec.partial_execution
                or sorted(c.source_index for c in spec.components) == list(range(len(components)))
            )
        ),
        "Debes resolver exactamente una vez cada componente del plan, sin omisiones.",
    )
    expected = {key(v) for v in plan.variables}
    decisions = {key(d.variable): d for d in spec.decisions}
    require(
        len(decisions) == len(spec.decisions) and set(decisions) == expected,
        "Confirma los tipos y las ausencias de todas las variables del plan, sin agregar otras.",
    )
    for d in spec.decisions:
        require(
            not (set(d.missing_markers) & set(d.retained_markers)),
            "Un marcador no puede conservarse y excluirse a la vez.",
        )
    comparison = plan.comparison
    required_filters = plan_filters(plan)
    require(
        [f.model_dump() for f in spec.filters] == [f.model_dump() for f in required_filters],
        "Los filtros deben coincidir exactamente con el alcance del plan aceptado.",
    )
    if comparison:
        if any(c.method in {"paired_t", "wilcoxon"} for c in spec.components):
            require(
                comparison.effect_size.standardizer == "none" and comparison.effect_size.name == "mean_difference",
                "El efecto del plan pareado exige una variante no implementada. Solicita un plan centrado en la diferencia de medidas.",
            )
        if comparison.multiplicity != "pending":
            require(
                spec.multiplicity == comparison.multiplicity, "Conserva el ajuste de multiplicidad del plan aceptado."
            )
        require(
            (
                comparison.effect_size.name in ("cohen_d", "hedges_g")
                and comparison.effect_size.standardizer == "pooled_sd"
            )
            or (comparison.effect_size.name == "mean_difference" and comparison.effect_size.standardizer == "none"),
            "Este plan pide otro efecto o estandarizador. Solicita un plan con d/g de SD combinada o diferencia sin estandarizar.",
        )
    scope_keys = {key(f.variable) for f in required_filters} | (
        {key(comparison.strata.variable)} if comparison and comparison.strata else set()
    )
    require(
        {key(v) for s in components for v in s.variables} | scope_keys == expected,
        "Los componentes deben cubrir todas las variables declaradas por el plan.",
    )
    for component in spec.components:
        source = components[component.source_index]
        if component.method == "descriptive" and component.descriptive_intervals:
            require(
                component.design == "independent",
                "Los intervalos de media requieren independencia confirmada; desactiva los intervalos para describir únicamente los registros observados.",
            )
        from app.services.statistics.methods import named_methods

        named = named_methods(source)
        require(
            len(named) != 1 or component.method in named,
            "El método cambia el procedimiento expresamente aceptado. Solicita una propuesta revisada antes de ejecutarlo.",
        )
        if (
            comparison
            and comparison.design != "unknown"
            and component.method in INDEPENDENT_GROUPS | {"paired_t", "wilcoxon"}
        ):
            require(component.design == comparison.design, "El diseño debe coincidir con el plan aceptado.")
        require(
            source.procedure in CATALOG[component.method].families,
            "El procedimiento confirmado no corresponde a la familia del componente aceptado.",
        )
        variables = source.variables
        require(all(key(v) in expected for v in variables), "El componente contiene referencias ajenas al plan.")
        if component.method != "descriptive":
            require(
                len({(v.file_id, v.sheet) for v in variables}) == 1,
                "Este procedimiento requiere una única tabla; no se emparejan filas de archivos diferentes.",
            )
        require(
            component.posthoc == "none" or component.method in {"anova", "welch_anova"},
            "Las comparaciones Welch-Holm solo están disponibles tras un ANOVA confirmado.",
        )
        if component.method in INDEPENDENT_GROUPS:
            require(component.design == "independent", "Confirma un diseño de grupos independientes.")
            require(
                sum(v.role == "outcome" for v in variables) == 1 and sum(v.role == "group" for v in variables) == 1,
                "Selecciona un plan con una variable de resultado y una agrupación.",
            )
            if comparison:
                require(
                    component.group_values == comparison.groups, "Conserva los dos grupos y su orden del plan aceptado."
                )
            require(
                component.method not in {"student_t", "anova"} or component.equal_variances_confirmed,
                "Student y ANOVA clásico requieren confirmar la igualdad de varianzas. Considera Welch.",
            )
        if component.method in {"paired_t", "wilcoxon"}:
            require(
                component.design == "paired",
                "Confirma el diseño pareado y un identificador de par válido en tabla ancha.",
            )
            require(
                sum(v.role == "outcome" for v in variables) == 2 and sum(v.role == "pair_id" for v in variables) == 1,
                "El plan pareado requiere dos resultados y un identificador único de par explícito.",
            )
        if component.method in {"chi_square", "fisher_exact", "pearson", "spearman"}:
            require(
                component.design == "independent",
                "Confirma que las observaciones son independientes según el diseño de recolección.",
            )
        if component.method in {"pearson", "spearman"}:
            measures = [v for v in variables if v.role not in {"group", "time", "pair_id"}]
            require(2 <= len(measures) <= 8, "La correlación requiere entre 2 y 8 variables de medida.")
            for v in measures:
                allowed = QUANTITATIVE | ({"ordinal"} if component.method == "spearman" else set())
                require(
                    decisions[key(v)].statistical_type in allowed,
                    "Pearson exige medidas cuantitativas; Spearman también permite ordinales con orden confirmado.",
                )


def original_table(file, data, settings):
    # Reutiliza los límites y criterios de perfilado, con overrides globales desactivados.
    metadata = file["metadata"]
    sheet = metadata.get("selected_sheet")
    fresh = inspect_file(
        file["original_name"], data, "dataset", settings.model_copy(update={"missing_value_overrides": {}}), sheet
    )
    require(not fresh.get("needs_sheet_selection"), "Selecciona la hoja antes de ejecutar.")
    require(fresh["selected_sheet"] == sheet, "La hoja original no coincide con la seleccionada.")
    require(
        fresh["file_type"] == file["file_type"],
        "El formato registrado no coincide con el nombre y contenido del original.",
    )
    require(
        fresh["profile"]["row_count"] * fresh["profile"]["column_count"] <= 400000,
        "La ejecución admite como máximo 400 000 celdas por archivo. Reduce la tabla.",
    )
    if file["file_type"] == "xlsx":
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            iterator = book[sheet].iter_rows(values_only=True)
            headers = next(iterator)
            records = list(iterator)
        finally:
            book.close()
    else:
        text = data.decode("utf-8-sig")
        if file["file_type"] == "csv":
            try:
                delimiter = csv.Sniffer().sniff(text[:16000], delimiters=",;\t").delimiter
            except csv.Error:
                delimiter = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
            iterator = csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
            headers = next(iterator)
            records = list(iterator)
        else:
            objects = json.loads(text)
            headers = list(dict.fromkeys(h for row in objects for h in row))
            records = [[row.get(h) for h in headers] for row in objects]
    headers = [str(h).strip() for h in headers]
    require(
        len(records) * len(headers) <= 400000,
        "La ejecución admite como máximo 400 000 celdas por archivo. Reduce la tabla.",
    )
    records = [[v.isoformat() if isinstance(v, (datetime, date)) else v for v in row] for row in records]
    return fresh["profile"], [dict(zip(headers, row)) for row in records]


@dataclass
class Prepared:
    file_id: str
    sheet: str
    initial: int
    rows: list[dict]
    decisions: dict
    filtered_out: int


def prepare(file, data, spec, settings):
    profile, records = original_table(file, data, settings)
    columns = {c["name"]: c for c in profile["columns"]}
    decisions = {d.variable.column: d for d in spec.decisions if d.variable.file_id == file["id"]}
    candidate_tokens = {v.strip().casefold() for v in settings.missing_value_markers.split(",") if v.strip()}
    for name, d in decisions.items():
        require(
            d.variable.sheet == file["metadata"].get("selected_sheet") and name in columns,
            f"La hoja o columna «{name}» ya no existe en el original.",
        )
        require(
            not columns[name]["possible_identifier"] or d.statistical_type not in QUANTITATIVE,
            f"«{name}» está identificada como posible identificador; no se admite como medida sin revisar el plan.",
        )
        values = [r[name] for r in records]
        candidates = {v.strip() for v in values if isinstance(v, str) and v.strip().casefold() in candidate_tokens}
        require(
            candidates <= set(d.missing_markers) | set(d.retained_markers),
            f"Confirma si cada marcador de «{name}» significa ausencia o un valor legítimo: {', '.join(sorted(candidates))}.",
        )
        numeric_markers = {numeric(m) for m in d.missing_markers if numeric(m) is not None}
        for row in records:
            value = row[name]
            marker = str(value).strip() if value is not None else ""
            declared_missing = marker in d.missing_markers or (
                d.statistical_type in QUANTITATIVE and numeric(value) is not None and numeric(value) in numeric_markers
            )
            if value is None or (isinstance(value, str) and not value.strip()) or declared_missing:
                row[name] = None
                continue
            if d.statistical_type in QUANTITATIVE:
                converted = numeric(value)
                require(
                    converted is not None,
                    f"«{name}» contiene valores no numéricos o fórmulas. Resuelve su significado; no se descartan silenciosamente.",
                )
                require(
                    d.statistical_type != "discrete" or converted.is_integer(),
                    f"«{name}» contiene decimales y fue declarada discreta.",
                )
                row[name] = converted
            else:
                row[name] = str(value)
        present = {row[name] for row in records if row[name] is not None}
        require(d.statistical_type != "binary" or len(present) <= 2, f"«{name}» tiene más de dos categorías.")
        if d.statistical_type == "ordinal":
            require(
                len(d.ordinal_order) == len(set(d.ordinal_order)) and present <= set(d.ordinal_order),
                f"Confirma el orden completo y sin duplicados de las categorías de «{name}».",
            )
    initial = len(records)
    for selection in spec.filters:
        if selection.variable.file_id != file["id"]:
            continue
        require(selection.variable.column in decisions, "El filtro no tiene una decisión de tipo declarada.")
        name = selection.variable.column
        present = {str(row[name]) for row in records if row[name] is not None}
        # Numeric confirmed columns use their numeric canonical representation for filters.
        chosen = (
            {str(float(v)) for v in selection.values}
            if decisions[name].statistical_type in QUANTITATIVE
            else set(selection.values)
        )
        require(
            chosen <= present, f"El filtro de «{name}» contiene valores inexistentes después de preparar los datos."
        )
        records = [row for row in records if row[name] is not None and str(row[name]) in chosen]
    require(bool(records), "Los filtros dejan la tabla sin observaciones.")
    return Prepared(file["id"], file["metadata"]["selected_sheet"], initial, records, decisions, initial - len(records))
