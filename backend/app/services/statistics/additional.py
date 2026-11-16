"""P1: procedimientos cerrados, variantes explícitas y límites de aproximación."""

import math

import numpy as np
from scipy import stats

from app.models.analysis import Assumption
from app.services.statistics.common import inference_text, label, table
from app.services.statistics.numerics import mean_summary
from app.services.statistics.preparation import CATEGORICAL, QUANTITATIVE, require


def independent_ranks(result, source, prepared, component, spec, charts):
    outcome = next(v for v in source.variables if v.role == "outcome")
    group = next(v for v in source.variables if v.role == "group")
    decision = prepared.decisions[outcome.column]
    require(
        decision.statistical_type in QUANTITATIVE | {"ordinal"},
        "El resultado debe ser cuantitativo u ordinal con orden confirmado.",
    )
    require(prepared.decisions[group.column].statistical_type in CATEGORICAL, "La agrupación debe ser categórica.")
    labels = component.group_values or sorted(
        {row[group.column] for row in prepared.rows if row[group.column] is not None}
    )
    require(len(labels) == len(set(labels)), "No repitas grupos en la selección.")
    require(
        len(labels) == 2 if result.method == "mann_whitney" else 3 <= len(labels) <= 20,
        "El número de grupos no es compatible con el método de rangos elegido.",
    )
    records = [row for row in prepared.rows if row[group.column] in labels and row[outcome.column] is not None]
    arrays = [
        np.asarray(
            [
                decision.ordinal_order.index(row[outcome.column])
                if decision.statistical_type == "ordinal"
                else row[outcome.column]
                for row in records
                if row[group.column] == level
            ],
            dtype=float,
        )
        for level in labels
    ]
    require(
        all(len(x) >= 2 for x in arrays),
        "Cada grupo requiere al menos dos valores válidos; hay un grupo vacío o insuficiente.",
    )
    require(
        len(set(np.concatenate(arrays))) > 1, "Todos los valores son iguales; el contraste de rangos no es calculable."
    )
    if result.method == "mann_whitney":
        test = stats.mannwhitneyu(*arrays, alternative="two-sided", method="asymptotic", use_continuity=True)
        computed = {
            "U": float(test.statistic),
            "p": float(test.pvalue),
            "rank_biserial": float(2 * test.statistic / (len(arrays[0]) * len(arrays[1])) - 1),
            "effect_definition": "r_rb=2U1/(n1*n2)−1; positivo: valores del grupo 1 tienden a ser mayores. U1 incluye medio crédito por empates.",
            "p_method": "Normal asintótica; corrección de empates y continuidad (0.5).",
        }
    else:
        test = stats.kruskal(*arrays)
        computed = {
            "H": float(test.statistic),
            "df": len(arrays) - 1,
            "p": float(test.pvalue),
            "p_method": "Chi-cuadrado asintótico; H con corrección por empates.",
            "effect_global": None,
            "effect_limitation": "Efecto global de rangos no implementado.",
        }
    computed.update(ci=None, ci_limitation="IC para este procedimiento no implementado.")
    result.statistics = computed
    result.sample.update(
        used=len(records),
        excluded_missing=sum(
            row[group.column] is None or (row[group.column] in labels and row[outcome.column] is None)
            for row in prepared.rows
        ),
        excluded_unselected_groups=sum(
            row[group.column] is not None and row[group.column] not in labels for row in prepared.rows
        ),
        groups=[{"group": name, "n": len(x)} for name, x in zip(labels, arrays)],
    )
    result.tables.append(
        table(
            "Contraste de rangos",
            [{"Medida": name, "Valor": value} for name, value in computed.items() if isinstance(value, (int, float))],
        )
    )
    if decision.statistical_type == "ordinal":
        summaries = []
        for name, x in zip(labels, arrays):
            ordered = sorted(int(v) for v in x)
            summaries.append(
                {
                    "Grupo": name,
                    "N válido": len(x),
                    "Categoría mediana inferior": decision.ordinal_order[ordered[(len(x) - 1) // 2]],
                    "Categoría mediana superior": decision.ordinal_order[ordered[len(x) // 2]],
                }
            )
            counts = {
                value: int(np.count_nonzero(x == i)) for i, value in enumerate(decision.ordinal_order) if np.any(x == i)
            }
            charts.frequencies(counts, f"{outcome.column} / {name}")
        result.tables.append(table("Resumen ordinal por grupo (orden confirmado)", summaries))
    else:
        result.tables.append(
            table(
                "Resumen por grupo",
                [
                    {"Grupo": name, "N válido": len(x), "Mediana": float(np.median(x))}
                    for name, x in zip(labels, arrays)
                ],
            )
        )
        charts.box(arrays, labels, label(outcome, prepared))
    all_values = np.concatenate(arrays)
    if len(np.unique(all_values)) < len(all_values):
        result.warnings.append(
            "Hay empates; el contraste usa rangos medios y la corrección de empates implementada por SciPy."
        )
    result.assumptions = [
        Assumption(
            name="Independencia",
            status="pending",
            detail="Declarada por el usuario; debe justificarse mediante el diseño.",
        ),
        Assumption(
            name="Forma de las distribuciones",
            status="pending",
            detail="Sin formas comparables, no interpretar automáticamente como una diferencia de medianas.",
        ),
    ]
    if min(len(x) for x in arrays) < 10:
        result.warnings.append(
            "Hay muestras pequeñas; el p asintótico puede ser impreciso. No se implementaron permutaciones para este contraste."
        )
    result.interpretation = (
        "Se compararon distribuciones mediante rangos, conservando empates y atípicos. "
        + inference_text(computed["p"], 1 - spec.confidence_level)
        + " No es una prueba universal de igualdad de medianas ni demuestra causalidad."
    )


def paired(result, source, prepared, component, spec, charts):
    a, b = [v for v in source.variables if v.role == "outcome"]
    pair_id = next(v for v in source.variables if v.role == "pair_id")
    require(
        all(prepared.decisions[v.column].statistical_type in QUANTITATIVE for v in [a, b]),
        "Los procedimientos pareados implementados requieren dos medidas cuantitativas.",
    )
    require(
        prepared.decisions[pair_id.column].statistical_type == "identifier",
        "Declara el identificador de par con tipo identificador.",
    )
    ids = [row[pair_id.column] for row in prepared.rows if row[pair_id.column] is not None]
    require(
        len(ids) == len(set(ids)),
        "El identificador de par está repetido. No se emparejan arbitrariamente mediciones de varias filas.",
    )
    records = [row for row in prepared.rows if all(row[v.column] is not None for v in [a, b, pair_id])]
    n = len(records)
    require(n >= 3, "Se necesitan al menos tres pares completos identificados.")
    x = np.asarray([row[a.column] for row in records], dtype=float)
    y = np.asarray([row[b.column] for row in records], dtype=float)
    differences = x - y
    summary = mean_summary(differences.tolist(), spec.confidence_level)
    require(
        summary["sd"] > 0, "Las diferencias son constantes; este contraste pareado no está habilitado para ese caso."
    )
    if result.method == "paired_t":
        se = summary["sd"] / math.sqrt(n)
        t = summary["mean"] / se
        computed = {
            "t": t,
            "df": n - 1,
            "p": float(2 * stats.t.sf(abs(t), n - 1)),
            "difference": summary["mean"],
            "difference_ci": summary["mean_ci"],
            "cohen_dz": summary["mean"] / summary["sd"],
            "effect_definition": "d_z=media de diferencias/SD muestral de diferencias. No es d con SD combinada de grupos independientes.",
            "effect_ci": None,
            "effect_ci_limitation": "IC de d_z no implementado.",
        }
    else:
        nonzero = int(np.count_nonzero(differences))
        require(
            nonzero >= 10, "Wilcoxon asintótico requiere al menos diez diferencias no nulas en esta implementación."
        )
        computed_test = stats.wilcoxon(
            differences, alternative="two-sided", zero_method="wilcox", correction=True, method="asymptotic"
        )
        computed = {
            "W": float(computed_test.statistic),
            "p": float(computed_test.pvalue),
            "zero_differences": n - nonzero,
            "nonzero_pairs": nonzero,
            "p_method": "Normal asintótica bilateral; zero_method=wilcox y corrección de continuidad. No se redondearon diferencias automáticamente.",
            "effect": None,
            "ci": None,
            "limitation": "Efecto estandarizado e IC de Wilcoxon no implementados.",
        }
    result.statistics = computed
    result.sample.update(used=n, pairs=n, excluded_missing=len(prepared.rows) - n)
    result.tables.append(
        table(
            "Contraste pareado",
            [{"Medida": name, "Valor": value} for name, value in computed.items() if isinstance(value, (int, float))],
        )
    )
    result.tables.append(
        table(
            "Diferencias de pares completos (primera medida − segunda)",
            [
                {
                    "Primera medida": a.column,
                    "Segunda medida": b.column,
                    "N de pares": n,
                    "Media de diferencias": summary["mean"],
                    "Mediana de diferencias": summary["median"],
                    "DE de diferencias": summary["sd"],
                }
            ],
        )
    )
    if result.method == "paired_t":
        ci = computed["difference_ci"]
        result.tables.append(
            table(
                "IC de la media de diferencias",
                [{"Límite inferior": ci["low"], "Límite superior": ci["high"], "Nivel": ci["level"]}],
            )
        )
    charts.histogram(differences, f"{a.column} − {b.column}")
    charts.scatter(x, y, label(a, prepared), label(b, prepared))
    result.assumptions = [
        Assumption(
            name="Pareamiento",
            status="evaluated",
            detail=f"Dos medidas en la misma fila con identificador único «{pair_id.column}». El usuario confirmó que corresponden al mismo par.",
        ),
        Assumption(
            name="Independencia entre pares",
            status="pending",
            detail="Debe justificarse en el diseño, no por la unicidad del identificador.",
        ),
        Assumption(
            name="Distribución de diferencias",
            status="pending",
            detail="Revisar histograma; normalidad aproximada para t y simetría para interpretar Wilcoxon como localización.",
        ),
    ]
    result.interpretation = (
        f"Se analizaron {n} pares completos identificados, con diferencia {a.column} − {b.column}. "
        + inference_text(computed["p"], 1 - spec.confidence_level)
        + " La identificación respalda la correspondencia de las mediciones, pero no demuestra causalidad."
    )


def association(result, source, prepared, component, spec, charts):
    variables = [v for v in source.variables if v.role not in {"pair_id", "time"}]
    require(len(variables) == 2, "La asociación categórica requiere exactamente dos variables de medida.")
    require(
        all(prepared.decisions[v.column].statistical_type in CATEGORICAL for v in variables),
        "Chi-cuadrado y Fisher requieren variables categóricas.",
    )
    a, b = variables
    records = [row for row in prepared.rows if row[a.column] is not None and row[b.column] is not None]
    levels_a = sorted({row[a.column] for row in records})
    levels_b = sorted({row[b.column] for row in records})
    require(
        2 <= len(levels_a) <= 20 and 2 <= len(levels_b) <= 20, "La tabla debe tener de 2 a 20 categorías por variable."
    )
    observed = np.zeros((len(levels_a), len(levels_b)), dtype=int)
    index_a, index_b = {v: i for i, v in enumerate(levels_a)}, {v: i for i, v in enumerate(levels_b)}
    for row in records:
        observed[index_a[row[a.column]], index_b[row[b.column]]] += 1
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / observed.sum()
    if result.method == "chi_square":
        test = stats.chi2_contingency(observed, correction=False)
        computed = {
            "chi2": float(test.statistic),
            "df": int(test.dof),
            "p": float(test.pvalue),
            "cramers_v": math.sqrt(float(test.statistic) / (len(records) * min(len(levels_a) - 1, len(levels_b) - 1))),
            "effect_definition": "V de Cramér convencional=sqrt(chi²/(N*min(filas−1,columnas−1))); sin corrección de sesgo.",
            "expected_min": float(expected.min()),
            "expected_below_5": int(np.count_nonzero(expected < 5)),
            "p_method": "Chi-cuadrado de Pearson sin corrección de Yates.",
            "effect_ci": None,
            "effect_ci_limitation": "IC de V no implementado.",
        }
        if np.any(expected < 5):
            result.warnings.append(
                "Hay frecuencias esperadas menores que 5: el p asintótico puede ser poco fiable. Para 2×2, revisa y confirma Fisher antes de una nueva ejecución; no se cambió el método."
            )
    else:
        require(observed.shape == (2, 2), "La prueba exacta de Fisher implementada requiere una tabla 2×2.")
        test = stats.fisher_exact(observed, alternative="two-sided")
        computed = {
            "p": float(test.pvalue),
            "odds_ratio": float(test.statistic) if math.isfinite(test.statistic) else None,
            "p_method": "Fisher exacto bilateral (ordenación por probabilidad hipergeométrica).",
            "ci": None,
            "limitation": "IC de odds ratio no implementado; odds ratio indefinido/infinito se registra como null.",
        }
    result.statistics = computed
    result.sample.update(used=len(records), excluded_missing=len(prepared.rows) - len(records))
    result.tables.append(
        table(
            "Asociación categórica",
            [{"Medida": name, "Valor": value} for name, value in computed.items() if isinstance(value, (int, float))],
        )
    )
    result.tables.append(
        table(
            "Frecuencias observadas y esperadas bajo independencia",
            [
                {
                    "Variable fila": a.column,
                    "Categoría fila": row_name,
                    "Variable columna": b.column,
                    "Categoría columna": col_name,
                    "Observada": int(observed[i, j]),
                    "Esperada": float(expected[i, j]),
                }
                for i, row_name in enumerate(levels_a)
                for j, col_name in enumerate(levels_b)
            ],
        )
    )
    charts.contingency(observed, levels_a, levels_b, a.column, b.column)
    result.assumptions = [
        Assumption(
            name="Independencia de observaciones",
            status="pending",
            detail="Confirmada por el usuario como diseño; no puede probarse con la tabla de frecuencias.",
        ),
        Assumption(
            name="Frecuencias esperadas",
            status="violated" if result.method == "chi_square" and np.any(expected < 5) else "evaluated",
            detail=f"Mínimo esperado={expected.min():.6g}; {np.count_nonzero(expected < 5)} celdas con esperada < 5. Fisher no requiere la aproximación chi-cuadrado.",
        ),
    ]
    result.interpretation = (
        f"Se evaluó la asociación entre {a.column} y {b.column} con casos completos. "
        + inference_text(computed["p"], 1 - spec.confidence_level)
        + " Una asociación no establece causalidad ni dirección temporal."
    )
