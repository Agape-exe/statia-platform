"""Productos verificables contra el catálogo del motor y el alcance de cada componente.

Plan v1 conserva expected_outputs íntegro. Alias genéricos históricos significan solo
los productos por defecto del componente, nunca resúmenes globales adicionales.
"""

import re
import unicodedata

from app.services.planning_errors import PlanningError

PRODUCT_INSTRUCTIONS = """
Para productos descriptivos en expected_outputs usa el catálogo verificable:
«Resúmenes globales», «Resúmenes por grupo», «Frecuencias categóricas»,
«Frecuencias categóricas por grupo», «Frecuencias de la variable de agrupación».
Los productos inferenciales incluyen «Valores p», «Coeficientes de correlación»,
«Intervalo de confianza para Pearson» y «Comparaciones post hoc», únicamente si
el catálogo del motor y las opciones confirmadas los permiten. Para vincular un
producto a un componente usa «Componente N: producto» (N empieza en 1).
Cada producto debe quedar cubierto por los componentes para todas sus variables
pertinentes. Un único descriptivo con role=group no produce resumen global ni
frecuencias del agrupador. Declara componentes separados para cubrirlos, sin unir
datos. Una integral exclusivamente descriptiva puede tener varios componentes de
la misma familia si sus alcances son distintos (global, agrupado y frecuencias);
no añadas inferencia para cumplir una cuota de procedimientos. Si falta alcance,
pregunta sin propuestas definitivas. No conviertas errores
de cobertura en avisos ni borres productos solicitados sin decisión del usuario.
"""

DEFAULT_OUTPUTS = frozenset(
    {
        "tabla descriptiva",
        "tablas descriptivas",
        "tablas y graficos",
        "tablas y png",
        "tabla de resultados al ejecutar en sesion 03",
        "tablas descriptivas en sesion 03",
        "tablas y graficos unicamente tras aceptacion y ejecucion autorizadas",
        "tablas de resumen estadistico",
        "conteos de valores faltantes por columna",
    }
)
OUTPUTS = {
    "resumenes globales": ("global",),
    "resumen global": ("global",),
    "descriptivos globales": ("global",),
    "resumenes por grupo": ("grouped",),
    "resumen agrupado": ("grouped",),
    "descriptivos por grupo": ("grouped",),
    "resumenes agrupados": ("grouped",),
    "frecuencias categoricas": ("frequencies",),
    "frecuencias categoricas globales": ("frequencies",),
    "frecuencias categoricas por grupo": ("grouped_frequencies",),
    "frecuencias de la variable de agrupacion": ("group_frequencies",),
    "frecuencias de grupo": ("group_frequencies",),
    "resumen global, agrupado y frecuencias de grupo": ("global", "grouped", "group_frequencies"),
    "intervalo de confianza de la media": ("mean_interval",),
    "tablas descriptivas sin intervalos de confianza": ("no_intervals",),
    "intervalo de confianza para pearson": ("pearson_interval",),
    "informes consolidados de descriptivos, correlacion y comparacion": ("combined_report",),
    "sin comparaciones post hoc": ("no_posthoc",),
    "valores p": ("p_value",),
    "valor p": ("p_value",),
    "coeficientes de correlacion": ("correlation_coefficient",),
    "coeficiente de correlacion": ("correlation_coefficient",),
    "comparaciones post hoc": ("posthoc",),
    "matriz o coeficientes de correlacion": ("correlation_coefficient",),
    "estadistico de prueba global": ("global_test",),
    "medias por grupo": ("group_means",),
    "n, media y desviacion estandar por grupo": ("grouped",),
    "n, medias y desviaciones estandar por grupo": ("grouped",),
    "f de welch": ("global_test",),
    "p global": ("p_value",),
    "valor p global": ("p_value",),
    "grados de libertad": ("degrees_of_freedom",),
    "grados de libertad del numerador y denominador": ("degrees_of_freedom",),
    "estimacion del cambio con incertidumbre": ("paired_change_interval",),
}
DESCRIPTIVE = {"descriptive", "exploratory"}


def normalized(text):
    text = "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(c))
    return " ".join(text.split()).rstrip(". ")


def key(variable):
    return variable.file_id, variable.sheet, variable.column


def separated_descriptives(plan):
    """Integral descriptiva válida solo con alcances estructurales distintos."""
    steps = plan.components
    if len(steps) < 2 or not all(s.procedure in DESCRIPTIVE for s in steps):
        return False
    scopes = {
        (
            tuple(sorted(key(v) for v in s.variables if v.role == "group")),
            tuple(sorted(key(v) for v in s.variables if v.role != "group")),
        )
        for s in steps
    }
    return len(scopes) == len(steps)


def product_coverage(plan, files=None, decisions=None, execution_components=None):
    """Cobertura estructural por columna; no convierte tipos ambiguos en hechos."""
    steps = plan.components if plan.procedure == "integral" else [plan]
    descriptive = [s for s in steps if s.procedure in DESCRIPTIVE]
    groups = {key(v) for s in steps for v in s.variables if v.role == "group"}
    measures = {key(v) for v in plan.variables} - groups
    categories = set()
    for file in files or []:
        for column in file["metadata"].get("profile", {}).get("columns", []):
            if column.get("statistical_type") in {"categorical", "categorical_or_ordinal"}:
                categories.add((file["id"], file["metadata"].get("selected_sheet"), column["name"]))
    if decisions is not None:
        categories = {key(d.variable) for d in decisions if d.statistical_type in {"nominal", "binary", "ordinal"}}
    categories &= {key(v) for v in plan.variables}
    covered = {kind: set() for kind in ("global", "grouped", "frequencies", "grouped_frequencies")}
    for source in descriptive:
        # describe() se despacha por archivo; nunca agrupa columnas de tablas distintas.
        for table in {(v.file_id, v.sheet) for v in source.variables}:
            variables = [v for v in source.variables if key(v)[:2] == table]
            source_groups = [key(v) for v in variables if v.role == "group"]
            if len(source_groups) > 1:
                raise PlanningError(
                    "output_capability", "El motor admite una sola agrupación por tabla y componente descriptivo."
                )
            grouped = bool(source_groups)
            columns = {key(v) for v in variables if v.role != "group"}
            covered["grouped" if grouped else "global"].update(
                {(v, source_groups[0]) for v in columns} if grouped else columns
            )
            covered["grouped_frequencies" if grouped else "frequencies"].update(
                {(v, source_groups[0]) for v in columns & categories} if grouped else columns & categories
            )
    # Las comparaciones de medias registradas también emiten el resumen numérico
    # por grupo. Solo acreditar sus resultados declarados y su agrupador exacto;
    # nunca resúmenes globales, frecuencias ni columnas de otros componentes.
    for index, source in enumerate(steps):
        if source.procedure != "group_comparison" or not supports_inference(
            plan, "group_means", index, files, decisions, execution_components
        ):
            continue
        grouping = [v for v in source.variables if v.role == "group"]
        outcomes = [v for v in source.variables if v.role == "outcome"]
        if len(grouping) == len(outcomes) == 1:
            covered["grouped"].add((key(outcomes[0]), key(grouping[0])))
    return descriptive, groups, measures, categories, covered


def output_request(text):
    """Gramática finita; una referencia libre a un componente necesita aclaración."""
    literal = normalized(text)
    binding = re.fullmatch(r"componente ([1-4]):\s*(.+)", literal)
    return (int(binding[1]) - 1, binding[2]) if binding else (None, literal)


def component_plan(plan, index):
    if index is None:
        return plan
    steps = plan.components if plan.procedure == "integral" else [plan]
    if index >= len(steps):
        raise PlanningError("output_capability", "El producto menciona un componente inexistente.")
    source = steps[index]
    return plan.model_copy(update={"procedure": source.procedure, "variables": source.variables, "components": []})


def executable_product(source, method, files, decisions, execution):
    """Viabilidad estructural; preparación/ejecución revalidan datos y diseño reales.

    Aquí no se calculan estadísticos ni se acredita una opción pendiente. Antes de
    ejecución se acredita la capacidad del método expresamente propuesto; después
    se exige el método seleccionado y sus opciones. No implica READY.
    """
    from app.services.statistics.catalog import CATALOG
    from app.services.statistics.preparation import (
        CATEGORICAL,
        INDEPENDENT_GROUPS,
        QUANTITATIVE,
    )

    if source.procedure not in CATALOG[method].families:
        return False
    if len({(v.file_id, v.sheet) for v in source.variables}) != 1:
        return False
    types = {key(d.variable): d.statistical_type for d in decisions or []}
    if decisions is None:
        types = {
            (f["id"], f["metadata"].get("selected_sheet"), c["name"]): "continuous"
            if c.get("statistical_type") == "quantitative"
            else "nominal"
            if c.get("statistical_type") in {"categorical", "categorical_or_ordinal"}
            else None
            for f in files or []
            for c in f["metadata"].get("profile", {}).get("columns", [])
            if not c.get("possible_identifier") and not c.get("possible_temporal")
        }
    measures = [v for v in source.variables if v.role not in {"group", "time", "pair_id"}]
    outcomes = [v for v in source.variables if v.role == "outcome"]
    groups = [v for v in source.variables if v.role == "group"]
    if method in {"pearson", "spearman"}:
        allowed = QUANTITATIVE | ({"ordinal"} if method == "spearman" else set())
        valid = 2 <= len(measures) <= 8 and all(types.get(key(v)) in allowed for v in measures)
    elif method in INDEPENDENT_GROUPS:
        allowed = QUANTITATIVE | ({"ordinal"} if method in {"mann_whitney", "kruskal"} else set())
        valid = len(outcomes) == len(groups) == 1 and all(types.get(key(v)) in allowed for v in outcomes)
    elif method in {"paired_t", "wilcoxon"}:
        valid = len(outcomes) == 2 and sum(v.role == "pair_id" for v in source.variables) == 1
        valid = valid and all(types.get(key(v)) in QUANTITATIVE for v in outcomes)
    elif method in {"chi_square", "fisher_exact"}:
        valid = len(source.variables) == 2 and all(types.get(key(v)) in CATEGORICAL for v in source.variables)
    else:
        valid = method == "descriptive"
    if execution and method != "descriptive":
        valid = valid and execution.design == ("paired" if method in {"paired_t", "wilcoxon"} else "independent")
        if method in {"student_t", "anova"}:
            valid = valid and execution.equal_variances_confirmed
    return valid


def supports_inference(plan, kind, binding, files, decisions, execution_components):
    from app.services.statistics.catalog import CATALOG
    from app.services.statistics.methods import named_methods, supported_request

    steps = plan.components if plan.procedure == "integral" else [plan]
    selected = {c.source_index: c for c in execution_components or []}
    for index, source in enumerate(steps):
        if binding is not None and binding != index:
            continue
        if not supported_request(source):
            continue
        named = named_methods(source)
        if not named and source.procedure == "correlation" and "correlacion" in normalized(source.method):
            # La familia histórica genérica puede acreditar únicamente productos
            # comunes a todos sus métodos; la preparación sigue exigiendo elegir.
            named = {code for code, entry in CATALOG.items() if source.procedure in entry.families}
        execution = selected.get(index)
        if execution_components is not None:
            if execution is None or not set(getattr(source, "depends_on", [])) <= selected.keys():
                continue
            method = execution.method
            if named and method not in named:
                continue
        elif named:
            # Una alternativa de método no impide un producto común a TODOS
            # sus métodos. No acredita un IC u opción que solo uno produciría.
            if all(
                kind in CATALOG[m].output_products and executable_product(source, m, files, decisions, None)
                for m in named
            ):
                if kind != "posthoc":
                    return True
            continue
        else:
            continue  # No escoger arbitrariamente un método pendiente del plan.
        if kind not in CATALOG[method].output_products:
            continue
        if kind == "posthoc" and (execution is None or execution.posthoc != "welch_holm"):
            continue  # El texto del modelo no activa una opción de ejecución.
        if executable_product(source, method, files, decisions, execution):
            return True
    return False


def requests_posthoc(text):
    literal = re.sub(
        r"\b(?:sin|no (?:incluir|realizar|hacer|quiero)) (?:comparaciones )?post[ -]?hoc\b", "", normalized(text)
    )
    return bool(re.search(r"post[ -]?hoc", literal))


def validate_products(plan, files=None, decisions=None, execution_components=None):
    from app.services.variable_types import confirmed_files

    if files is not None:
        files = confirmed_files(plan, files)
    for index, text in enumerate(plan.expected_outputs):
        binding, literal = output_request(text)
        scoped = component_plan(plan, binding)
        selected_components = execution_components
        if binding is not None and execution_components is not None:
            selected_components = [
                c.model_copy(update={"source_index": 0}) for c in execution_components if c.source_index == binding
            ]
        descriptive, groups, measures, categories, covered = product_coverage(
            scoped, files, decisions, selected_components
        )
        if literal in DEFAULT_OUTPUTS:
            continue
        kinds = OUTPUTS.get(literal)
        if kinds is None:
            raise PlanningError(
                "output_scope",
                f"El producto esperado {index + 1} no tiene un alcance verificable. "
                "Aclara el alcance y solicita una propuesta revisada con productos del catálogo: "
                "Resúmenes globales; Resúmenes por grupo; Frecuencias categóricas; "
                "Frecuencias categóricas por grupo; Frecuencias de la variable de agrupación; "
                "Valores p; Coeficientes de correlación. "
                "El plan original se conserva y no se recortan productos automáticamente.",
            )
        for kind in kinds:
            if kind == "no_posthoc":
                steps = plan.components if plan.procedure == "integral" else [plan]
                if any(requests_posthoc(s.method) for s in steps):
                    raise PlanningError(
                        "output_capability", "El plan excluye comparaciones post hoc pero su método las solicita."
                    )
                if execution_components and any(c.posthoc != "none" for c in execution_components):
                    raise PlanningError(
                        "output_capability", "Conserva la exclusión de comparaciones post hoc del plan aceptado."
                    )
                continue
            if kind in {
                "p_value",
                "correlation_coefficient",
                "pearson_interval",
                "posthoc",
                "global_test",
                "group_means",
                "degrees_of_freedom",
                "paired_change_interval",
            }:
                if not supports_inference(plan, kind, binding, files, decisions, execution_components):
                    raise PlanningError(
                        "output_capability",
                        f"El producto esperado {index + 1} no tiene un componente ejecutable que lo produzca "
                        "con el método y las opciones definidos. Aclara las decisiones pendientes sin sustituir el producto.",
                    )
                continue
            if kind in {"mean_interval", "no_intervals", "combined_report"}:
                if kind == "combined_report":
                    valid = bool(descriptive) and all(
                        supports_inference(plan, product, binding, files, decisions, execution_components)
                        for product in ("correlation_coefficient", "group_means")
                    )
                elif execution_components is not None:
                    all_steps = plan.components if plan.procedure == "integral" else [plan]
                    descriptive_indexes = {
                        i
                        for i, s in enumerate(all_steps)
                        if s.procedure in DESCRIPTIVE and (binding is None or binding == i)
                    }
                    flags = [
                        c.descriptive_intervals for c in execution_components if c.source_index in descriptive_indexes
                    ]
                    # Una revisión parcial sin este descriptivo no cambia sus decisiones.
                    valid = (
                        bool(flags) and all(flags) if kind == "mean_interval" else bool(descriptive) and not any(flags)
                    )
                else:
                    valid = bool(descriptive)
                if kind == "mean_interval":
                    quantitative = {
                        key(d.variable) for d in decisions or [] if d.statistical_type in {"continuous", "discrete"}
                    }
                    if decisions is None:
                        quantitative = {
                            (f["id"], f["metadata"].get("selected_sheet"), c["name"])
                            for f in files or []
                            for c in f["metadata"].get("profile", {}).get("columns", [])
                            if c.get("statistical_type") == "quantitative"
                        }
                    quantitative &= {key(v) for v in scoped.variables}
                    valid = (
                        valid
                        and bool(quantitative)
                        and quantitative <= covered["global"] | {v for v, _ in covered["grouped"]}
                    )
                if not valid:
                    raise PlanningError(
                        "output_capability",
                        f"El producto esperado {index + 1} no corresponde a los métodos o decisiones confirmados.",
                    )
                continue
            target = (
                groups
                if kind == "group_frequencies"
                else categories
                if kind == "frequencies"
                else categories - groups
                if kind == "grouped_frequencies"
                else measures
            )
            if kind in {"grouped", "grouped_frequencies"}:
                target = {(v, group) for v in target for group in groups if v[:2] == group[:2]}
            actual = covered["frequencies" if kind == "group_frequencies" else kind]
            if not target or not target <= actual:
                raise PlanningError(
                    "output_capability",
                    f"El producto esperado {index + 1} no está cubierto por los componentes: {text}. "
                    "Un descriptivo agrupado solo resume por grupo y omite frecuencias del agrupador. "
                    "Solicita componentes separados que cubran los productos requeridos o una propuesta "
                    "revisada con una decisión explícita de alcance; una advertencia no resuelve la incompatibilidad.",
                )


def descriptive_warnings(plan):
    """Aviso explicativo; no sustituye validate_products en ningún punto de control."""
    steps = plan.components if plan.procedure == "integral" else [plan]
    if any(s.procedure in DESCRIPTIVE and any(v.role == "group" for v in s.variables) for s in steps):
        return [
            "El descriptivo agrupado produce únicamente los productos cubiertos por sus componentes; "
            "el resumen global y las frecuencias del agrupador necesitan componentes separados."
        ]
    return []


def warn_capabilities(reply):
    # No modificar limitaciones ni supuestamente reparar planes añadiendo avisos.
    return reply
