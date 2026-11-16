import math

from app.models.analysis import ResultTable


def table(title, rows):
    return ResultTable(title=title, columns=list(rows[0]) if rows else [], rows=rows)


def label(variable, prepared):
    unit = prepared.decisions[variable.column].unit
    return variable.column + (f" ({unit})" if unit else "")


def p_text(p):
    if not math.isfinite(p):
        return "p no calculable"
    return "p < 0.001" if p < 0.001 else f"p = {p:.4f}"


def inference_text(p, alpha):
    if not math.isfinite(p):
        return "El valor p no es calculable en precisión finita; no se puede interpretar este contraste."
    conclusion = (
        "Hay evidencia contra la hipótesis nula en el nivel registrado."
        if p < alpha
        else "No hay evidencia suficiente contra la hipótesis nula en el nivel registrado; esto no demuestra ausencia de efecto ni que H0 sea verdadera."
    )
    return f"{p_text(p)}; α = {alpha:.3g}. {conclusion} El valor p describe la compatibilidad con H0 bajo los supuestos del método, no la probabilidad de que H0 sea verdadera. La significación no determina la importancia práctica."
