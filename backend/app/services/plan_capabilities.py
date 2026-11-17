"""Catálogo finito de productos descriptivos: la prosa desconocida no acredita cobertura.

Plan v1 conserva expected_outputs íntegro. Alias genéricos históricos significan solo
los productos por defecto del componente, nunca resúmenes globales adicionales.
"""

import unicodedata

from app.services.planning_errors import PlanningError

PRODUCT_INSTRUCTIONS = """
Para productos descriptivos en expected_outputs usa el catálogo verificable:
«Resúmenes globales», «Resúmenes por grupo», «Frecuencias categóricas»,
«Frecuencias categóricas por grupo», «Frecuencias de la variable de agrupación».
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


def product_coverage(plan, files=None, decisions=None):
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
    return descriptive, groups, measures, categories, covered


def validate_products(plan, files=None, decisions=None, execution_components=None):
    descriptive, groups, measures, categories, covered = product_coverage(plan, files, decisions)
    if not descriptive:
        return  # Las restricciones inferenciales permanecen en sus validadores específicos.
    for index, text in enumerate(plan.expected_outputs):
        literal = normalized(text)
        if literal in DEFAULT_OUTPUTS:
            continue
        kinds = OUTPUTS.get(literal)
        if kinds is None:
            raise PlanningError(
                "output_scope",
                f"El producto esperado {index + 1} no tiene un alcance descriptivo verificable. "
                "Aclara el alcance y solicita una propuesta revisada con productos del catálogo: "
                "Resúmenes globales; Resúmenes por grupo; Frecuencias categóricas; "
                "Frecuencias categóricas por grupo; Frecuencias de la variable de agrupación. "
                "El plan original se conserva y no se recortan productos automáticamente.",
            )
        for kind in kinds:
            if kind in {"mean_interval", "no_intervals", "pearson_interval", "combined_report"}:
                steps = plan.components if plan.procedure == "integral" else [plan]
                if kind == "combined_report":
                    valid = {"correlation", "group_comparison"} <= {s.procedure for s in steps}
                elif kind == "pearson_interval":
                    from app.services.statistics.methods import named_methods

                    valid = any(s.procedure == "correlation" and named_methods(s) == {"pearson"} for s in steps)
                elif execution_components is not None:
                    descriptive_indexes = {i for i, s in enumerate(steps) if s.procedure in DESCRIPTIVE}
                    flags = [
                        c.descriptive_intervals for c in execution_components if c.source_index in descriptive_indexes
                    ]
                    # Una revisión parcial sin este descriptivo no cambia sus decisiones.
                    valid = all(flags) if kind == "mean_interval" else not any(flags)
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
                    quantitative &= {key(v) for v in plan.variables}
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
