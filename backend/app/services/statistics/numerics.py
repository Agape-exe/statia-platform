"""Fórmulas auditables. No hay selección de métodos según los valores p."""

import math
from collections import Counter

import numpy as np
from scipy import special, stats

from app.services.statistics.preparation import require


def mean_summary(values, confidence, *, intervals=True):
    x = np.asarray(values, dtype=float)
    n = len(x)
    require(n > 0, "No hay observaciones cuantitativas válidas.")
    mean = float(np.mean(x))
    median = float(np.median(x))
    q1, q3 = np.quantile(x, [0.25, 0.75], method="linear")
    variance = float(np.var(x, ddof=1)) if n > 1 else None
    sd = math.sqrt(variance) if variance is not None else None
    counts = Counter(values)
    maximum = max(counts.values())
    modes = sorted(v for v, count in counts.items() if count == maximum) if maximum > 1 else []
    ci = None
    if intervals and n > 1 and sd > 0:
        margin = float(stats.t.ppf((1 + confidence) / 2, n - 1)) * sd / math.sqrt(n)
        ci = {
            "low": mean - margin,
            "high": mean + margin,
            "level": confidence,
            "method": "t de Student para la media",
            "df": n - 1,
        }
    return {
        "n": n,
        "mean": mean,
        "median": median,
        "modes": modes[:20],
        "mode_count": len(modes),
        "sd": sd,
        "variance": variance,
        "min": float(x.min()),
        "max": float(x.max()),
        "range": float(np.ptp(x)),
        "q1": float(q1),
        "q3": float(q3),
        "iqr": float(q3 - q1),
        "mean_ci": ci,
    }


def two_groups(a, b, method, confidence):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    n1, n2 = len(a), len(b)
    require(min(n1, n2) >= 2, "Cada grupo necesita al menos dos observaciones válidas.")
    m1, m2 = float(np.mean(a)), float(np.mean(b))
    v1, v2 = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    require(v1 > 0 and v2 > 0, "Hay un grupo con varianza nula; este contraste no está habilitado para ese caso.")
    hedges_df = n1 + n2 - 2
    pooled_variance = ((n1 - 1) * v1 + (n2 - 1) * v2) / hedges_df
    pooled_sd = math.sqrt(pooled_variance)
    difference = m1 - m2
    if method == "student_t":
        se = pooled_sd * math.sqrt(1 / n1 + 1 / n2)
        df = float(hedges_df)
    else:
        se = math.sqrt(v1 / n1 + v2 / n2)
        df = (v1 / n1 + v2 / n2) ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    t = difference / se
    p = float(2 * stats.t.sf(abs(t), df))
    critical = float(stats.t.ppf((1 + confidence) / 2, df))
    d = difference / pooled_sd
    # J exacto: Γ(ν/2)/(sqrt(ν/2) Γ((ν−1)/2)); ν_H no es ν de Welch.
    correction = float(
        np.exp(special.gammaln(hedges_df / 2) - special.gammaln((hedges_df - 1) / 2) - 0.5 * np.log(hedges_df / 2))
    )
    return {
        "t": t,
        "df": df,
        "p": p,
        "difference": difference,
        "standard_error": se,
        "difference_ci": {
            "low": difference - critical * se,
            "high": difference + critical * se,
            "level": confidence,
            "method": "t con gl del contraste",
        },
        "cohen_d": d,
        "hedges_g": correction * d,
        "pooled_sd": pooled_sd,
        "hedges_df": hedges_df,
        "hedges_J": correction,
        "effect_definition": "d=(media1-media2)/s_p; s_p²=((n1−1)s1²+(n2−1)s2²)/(n1+n2−2); g=J(ν_H)d; ν_H=n1+n2−2; J exacto mediante gamma.",
        "effect_ci": None,
        "effect_ci_limitation": "IC de d de Cohen y g de Hedges no implementados.",
    }


def one_way(groups, method):
    arrays = [np.asarray(group, dtype=float) for group in groups]
    k = len(arrays)
    require(3 <= k <= 20, "ANOVA requiere de 3 a 20 grupos declarados.")
    ns = np.asarray([len(g) for g in arrays], dtype=float)
    require(min(ns) >= 2, "Cada grupo necesita al menos dos observaciones válidas.")
    means = np.asarray([np.mean(g) for g in arrays])
    variances = np.asarray([np.var(g, ddof=1) for g in arrays])
    require(bool(np.all(variances > 0)), "Hay un grupo con varianza nula; este ANOVA no está habilitado para ese caso.")
    if method == "anova":
        grand = np.sum(ns * means) / np.sum(ns)
        ss_between = float(np.sum(ns * (means - grand) ** 2))
        ss_within = float(np.sum((ns - 1) * variances))
        df1, df2 = float(k - 1), float(np.sum(ns) - k)
        f = (ss_between / df1) / (ss_within / df2)
        effect = ss_between / (ss_between + ss_within)
        result = {
            "eta_squared": effect,
            "effect_definition": "η² clásico=SS_entre/SS_total; no trasladable al ANOVA de Welch.",
        }
    else:
        weights = ns / variances
        total_weight = np.sum(weights)
        weighted_mean = np.sum(weights * means) / total_weight
        term = float(np.sum((1 - weights / total_weight) ** 2 / (ns - 1)))
        f = float(np.sum(weights * (means - weighted_mean) ** 2) / (k - 1) / (1 + 2 * (k - 2) * term / (k**2 - 1)))
        df1, df2 = float(k - 1), (k**2 - 1) / (3 * term)
        result = {
            "effect_global": None,
            "effect_limitation": "Tamaño del efecto global específico de ANOVA de Welch no implementado.",
        }
    return {
        **result,
        "F": f,
        "df_between": df1,
        "df_within": df2,
        "p": float(stats.f.sf(f, df1, df2)),
        "global_ci": None,
        "ci_limitation": "Intervalo global y post-hoc no implementados.",
    }


def correlation(x, y, method, confidence):
    require(len(x) >= 3, "La correlación requiere al menos tres parejas válidas.")
    require(len(set(x)) > 1 and len(set(y)) > 1, "Una variable es constante; la correlación no está definida.")
    if method == "pearson":
        computed = stats.pearsonr(x, y)
        ci = None
        if len(x) > 3:
            interval = computed.confidence_interval(confidence_level=confidence)
            ci = {"low": float(interval.low), "high": float(interval.high), "level": confidence, "method": "Fisher z"}
    else:
        computed = stats.spearmanr(x, y)
        ci = None
    return {"coefficient": float(computed.statistic), "p": float(computed.pvalue), "ci": ci}


def holm(pvalues):
    """Holm step-down: orden estable, máximo acumulado y restitución de índices."""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted, previous = [0.0] * len(pvalues), 0.0
    for rank, index in enumerate(order):
        previous = max(previous, min(1.0, (len(pvalues) - rank) * pvalues[index]))
        adjusted[index] = previous
    return adjusted
