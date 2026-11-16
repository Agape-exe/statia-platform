from collections import Counter
from itertools import combinations

import numpy as np
from scipy import stats

from app.models.analysis import Assumption, ComponentResult, ResultTable
from app.services.statistics.catalog import CATALOG
from app.services.statistics.charts import Charts
from app.services.statistics.numerics import correlation, mean_summary, one_way, two_groups
from app.services.statistics.preparation import AnalysisError, CATEGORICAL, QUANTITATIVE, require


def table(title, rows):
    return ResultTable(title=title, columns=list(rows[0]) if rows else [], rows=rows)


def label(variable, prepared):
    unit = prepared.decisions[variable.column].unit
    return variable.column + (f' ({unit})' if unit else '')


def p_text(p):
    return 'p < 0.001' if p < .001 else f'p = {p:.4f}'


def inference_text(p, alpha):
    conclusion = ('Hay evidencia contra la hipótesis nula en el nivel registrado.' if p < alpha else
                  'No hay evidencia suficiente contra la hipótesis nula en el nivel registrado; esto no demuestra ausencia de efecto ni que H0 sea verdadera.')
    return f'{p_text(p)}; α = {alpha:.3g}. {conclusion} El valor p describe la compatibilidad con H0 bajo los supuestos del método, no la probabilidad de que H0 sea verdadera. La significación no determina la importancia práctica.'


def quantitative_row(name, values, missing, confidence):
    summary = mean_summary(values, confidence)
    ci = summary['mean_ci']
    row = {'Variable': name, 'N válido': summary['n'], 'Ausentes': missing, 'Media': summary['mean'], 'Mediana': summary['median'],
           'Modas': summary['modes'], 'DE muestral': summary['sd'], 'Varianza muestral': summary['variance'],
           'Mínimo': summary['min'], 'Máximo': summary['max'], 'Rango': summary['range'], 'Q1': summary['q1'], 'Q3': summary['q3'],
           'RIC': summary['iqr'], 'IC media inferior': ci['low'] if ci else None, 'IC media superior': ci['high'] if ci else None}
    return row, summary


def describe(result, source, prepared, spec, charts):
    groups = [v for v in source.variables if v.role == 'group']
    require(len(groups) <= 1, 'El descriptivo admite una sola agrupación por componente.')
    require(not groups or prepared.decisions[groups[0].column].statistical_type in CATEGORICAL,
            'La agrupación descriptiva debe ser categórica.')
    levels = sorted({row[groups[0].column] for row in prepared.rows if row[groups[0].column] is not None}) if groups else [None]
    require(len(levels) <= 20, 'El descriptivo agrupado admite hasta 20 grupos.')
    numeric_rows, frequencies, medians = [], [], []
    for v in source.variables:
        name, decision = v.column, prepared.decisions[v.column]
        if v.role == 'group':
            continue
        require(decision.statistical_type not in {'identifier', 'temporal'}, f'«{name}»: descriptivo temporal o de identificadores no implementado; usa un plan de medidas o categorías.')
        for group in levels:
            records = [row for row in prepared.rows if row[groups[0].column] == group] if groups else prepared.rows
            values = [row[name] for row in records if row[name] is not None]
            missing = len(records) - len(values)
            display = label(v, prepared) + (f' / {group}' if group is not None else '')
            if not values:
                result.status = 'partial'
                result.warnings.append(f'{display}: sin observaciones válidas; no se calculó un resumen.')
                continue
            if decision.statistical_type in QUANTITATIVE:
                row, summary = quantitative_row(display, values, missing, spec.confidence_level)
                numeric_rows.append(row)
                if summary['mean_ci'] is None:
                    result.warnings.append(f'{display}: IC de media no disponible por muestra insuficiente o varianza nula.')
                charts.histogram(values, display)
                charts.box([values], [str(group) if group is not None else 'Todas'], display)
            else:
                counts = Counter(values)
                require(len(counts) <= 100, f'«{name}» tiene más de 100 categorías; no se genera una tabla truncada.')
                for value, count in sorted(counts.items()):
                    frequencies.append({'Variable / grupo': display, 'Categoría': value, 'Frecuencia': count,
                                        'Frecuencia relativa válida': count / len(values), 'Porcentaje válido': count / len(values) * 100,
                                        'N válido': len(values), 'Ausentes': missing})
                if decision.statistical_type == 'ordinal':
                    indexes = sorted(decision.ordinal_order.index(value) for value in values)
                    medians.append({'Variable / grupo': display, 'Categoría mediana inferior': decision.ordinal_order[indexes[(len(indexes) - 1) // 2]],
                                    'Categoría mediana superior': decision.ordinal_order[indexes[len(indexes) // 2]], 'N válido': len(values)})
                if len(counts) <= 20:
                    charts.frequencies(counts, display)
        if groups:
            missing_group = sum(row[groups[0].column] is None for row in prepared.rows)
            result.warnings.append(f'Agrupación {groups[0].column}: {missing_group} filas sin grupo, excluidas de los resúmenes agrupados.')
    for title, rows in [('Descriptivos cuantitativos (IC t, cuartiles lineales)', numeric_rows),
                        ('Frecuencias sobre observaciones válidas', frequencies), ('Medianas ordinales por orden confirmado', medians)]:
        if rows:
            result.tables.append(table(title, rows))
    require(bool(result.tables), 'No hay variables con observaciones válidas para describir.')
    result.assumptions.append(Assumption(name='IC de media', status='pending', detail='Los IC t requieren independencia y normalidad aproximada de la media; el descriptivo no verifica el diseño.'))
    result.interpretation = 'Se describieron las observaciones válidas de cada variable y grupo. Los porcentajes usan como denominador los valores presentes; los ausentes se informan aparte. DE y varianza son muestrales (n−1). No se eliminaron atípicos ni se demuestra causalidad.'


def correlate(result, source, prepared, spec, charts):
    measures = [v for v in source.variables if v.role not in {'group', 'time', 'pair_id'}]
    pairs, rows = [], []
    matrix = np.full((len(measures), len(measures)), np.nan)
    for (i, a), (j, b) in combinations(enumerate(measures), 2):
        values = [(row[a.column], row[b.column]) for row in prepared.rows if row[a.column] is not None and row[b.column] is not None]
        x, y = [v[0] for v in values], [v[1] for v in values]
        for v, array in [(a, x), (b, y)]:
            decision = prepared.decisions[v.column]
            if decision.statistical_type == 'ordinal':
                array[:] = [decision.ordinal_order.index(value) for value in array]
        pair = {'variable_x': a.column, 'variable_y': b.column, 'n': len(values), 'excluded_missing': len(prepared.rows) - len(values)}
        try:
            computed = correlation(x, y, result.method, spec.confidence_level)
            pair.update(computed)
            matrix[i, j] = matrix[j, i] = computed['coefficient']
            if len(pairs) < 3:
                charts.scatter(x, y, label(a, prepared), label(b, prepared))
            if result.method == 'spearman':
                if len(set(x)) < len(x) or len(set(y)) < len(y):
                    result.warnings.append(f'{a.column} / {b.column}: hay empates; se usan rangos medios.')
                if len(x) <= 500:
                    result.warnings.append(f'{a.column} / {b.column}: p asintótico de Spearman; precisión limitada con N ≤ 500, sin permutaciones implementadas.')
            elif len(x) <= 3:
                result.warnings.append(f'{a.column} / {b.column}: IC Fisher z no disponible con N ≤ 3.')
        except AnalysisError as exc:
            pair.update(coefficient=None, p=None, ci=None, unavailable_reason=str(exc))
            result.warnings.append(f'{a.column} / {b.column}: {exc}')
        pairs.append(pair)
        ci = pair['ci']
        rows.append({'Variable X': a.column, 'Variable Y': b.column, 'N por pareja': len(values), 'Exclusiones por ausencias': pair['excluded_missing'],
                     'Coeficiente': pair['coefficient'], 'p': pair['p'], 'IC inferior': ci['low'] if ci else None, 'IC superior': ci['high'] if ci else None,
                     'Disponibilidad': pair.get('unavailable_reason', 'Calculado')})
    require(any(p['coefficient'] is not None for p in pairs), 'Ninguna pareja tiene una correlación calculable; revisa constantes y tamaños muestrales.')
    if any(p['coefficient'] is None for p in pairs):
        result.status = 'partial'
    if len(measures) > 2:
        charts.matrix(matrix, [v.column for v in measures])
    result.statistics = {'pairs': pairs, 'ci_method': 'Fisher z (Pearson, N>3)' if result.method == 'pearson' else 'IC de Spearman no implementado'}
    result.tables.append(table('Correlaciones por parejas completas', rows))
    result.assumptions.extend([
        Assumption(name='Independencia', status='pending', detail='Debe respaldarse en el diseño; las filas no demuestran independencia.'),
        Assumption(name='Forma de asociación', status='pending', detail='Revisa dispersión, atípicos y relación lineal (Pearson) o monótona (Spearman). La normalidad bivariada de Pearson no se verifica con un test univariado.'),
    ])
    result.interpretation = 'Se calculó cada asociación usando exclusivamente parejas válidas; los tamaños muestrales pueden diferir. El coeficiente describe dirección y magnitud de la asociación y no demuestra causalidad. ' + ' '.join(
        f'{p["variable_x"]} / {p["variable_y"]}: coeficiente = {p["coefficient"]:.4g}, N = {p["n"]}; {inference_text(p["p"], 1 - spec.confidence_level)}'
        for p in pairs if p['p'] is not None)


def diagnostics(arrays, labels, alpha):
    rows, assumptions = [], []
    for x, name in zip(arrays, labels):
        q1, q3 = np.quantile(x, [.25, .75])
        outliers = int(np.sum((x < q1 - 1.5 * (q3 - q1)) | (x > q3 + 1.5 * (q3 - q1))))
        # Shapiro se limita a 5000 observaciones; no selecciona el método.
        subset = x[np.linspace(0, len(x) - 1, min(5000, len(x)), dtype=int)]
        shapiro = stats.shapiro(subset) if len(subset) >= 3 else None
        rows.append({'Grupo': name, 'N': len(x), 'Atípicos IQR (conservados)': outliers,
                     'Shapiro W': float(shapiro.statistic) if shapiro else None, 'p Shapiro': float(shapiro.pvalue) if shapiro else None,
                     'N diagnóstico': len(subset), 'Alcance': 'Diagnóstico; no selecciona procedimientos'})
    levene = stats.levene(*arrays, center='median')
    assumptions.append(Assumption(name='Homogeneidad (Levene centrado en mediana)', status='evaluated',
                                  detail=f'Estadístico {levene.statistic:.6g}; {p_text(levene.pvalue)}. No prueba igualdad de varianzas; Welch admite desigualdad.'))
    assumptions.append(Assumption(name='Normalidad', status='evaluated', detail='Shapiro y atípicos IQR en tabla; inspeccionar también gráficos y N. N diagnóstico máximo 5000. No se seleccionó el método según estos valores p.'))
    return rows, assumptions


def compare(result, source, prepared, component, spec, charts):
    outcome = next(v for v in source.variables if v.role == 'outcome')
    group = next(v for v in source.variables if v.role == 'group')
    require(prepared.decisions[outcome.column].statistical_type in QUANTITATIVE, 'La variable de resultado debe ser cuantitativa, no ordinal ni un código.')
    require(prepared.decisions[group.column].statistical_type in CATEGORICAL, 'La agrupación debe ser nominal, binaria u ordinal.')
    available = sorted({row[group.column] for row in prepared.rows if row[group.column] is not None})
    labels = component.group_values or available
    require(len(labels) == len(set(labels)), 'No repitas grupos en la selección.')
    require(set(labels) <= set(available), 'Un grupo seleccionado no tiene observaciones después de filtrar.')
    if result.method.endswith('_t'):
        require(len(labels) == 2, 'La prueba t necesita exactamente dos grupos confirmados; no se descartan categorías automáticamente.')
    else:
        require(3 <= len(labels) <= 20, 'El ANOVA requiere entre 3 y 20 grupos.')
    records = [row for row in prepared.rows if row[group.column] in labels and row[outcome.column] is not None]
    arrays = [np.asarray([row[outcome.column] for row in records if row[group.column] == level], dtype=float) for level in labels]
    result.sample.update(groups=[{'group': name, 'n': len(x)} for name, x in zip(labels, arrays)],
                         used=len(records), excluded_missing=sum(row[group.column] is None or (row[group.column] in labels and row[outcome.column] is None) for row in prepared.rows),
                         excluded_unselected_groups=sum(row[group.column] is not None and row[group.column] not in labels for row in prepared.rows))
    computed = two_groups(*arrays, result.method, spec.confidence_level) if result.method.endswith('_t') else one_way(arrays, result.method)
    result.statistics = computed
    desc = []
    for name, x in zip(labels, arrays):
        row, _ = quantitative_row(str(name), x.tolist(), sum(r[group.column] == name and r[outcome.column] is None for r in prepared.rows), spec.confidence_level)
        row['Variable'] = label(outcome, prepared) + ' / ' + name
        desc.append(row)
    result.tables.append(table('Resumen por grupos (orden de la diferencia: grupo 1 − grupo 2)', desc))
    scalar = {k: v for k, v in computed.items() if isinstance(v, (int, float))}
    names = {'df': 'Grados de libertad del contraste', 'df_between': 'Grados de libertad del numerador', 'df_within': 'Grados de libertad del denominador',
             'difference': 'Diferencia de medias (grupo 1 − grupo 2)', 'standard_error': 'Error estándar de la diferencia',
             'cohen_d': 'd de Cohen (SD combinada)', 'hedges_g': 'g de Hedges (J exacto)', 'pooled_sd': 'SD combinada',
             'hedges_df': 'Grados de libertad de Hedges', 'hedges_J': 'Factor J de Hedges', 'eta_squared': 'Eta cuadrado clásico'}
    result.tables.append(table('Contraste y tamaños del efecto', [{'Medida': names.get(k, k), 'Valor': v} for k, v in scalar.items()]))
    if 'effect_definition' in computed:
        result.warnings.append(computed['effect_definition'])
    if 'difference_ci' in computed:
        ci = computed['difference_ci']
        result.tables.append(table('Intervalo de confianza de la diferencia de medias', [{'Límite inferior': ci['low'], 'Límite superior': ci['high'], 'Nivel': ci['level'], 'Método': ci['method'] }]))
    diag, assumptions = diagnostics(arrays, labels, 1 - spec.confidence_level)
    result.tables.append(table('Diagnósticos de distribución', diag))
    result.assumptions = assumptions + [Assumption(name='Independencia', status='pending', detail='Diseño independiente declarado por el usuario; no verificable solo con el dataset. Revisa muestreo, conglomerados y mediciones repetidas.')]
    if result.method in {'student_t', 'anova'}:
        result.assumptions.append(Assumption(name='Igualdad de varianzas', status='pending', detail='Requisito confirmado por el usuario; el diagnóstico de Levene no demuestra igualdad.'))
    if min(len(x) for x in arrays) < 10:
        result.warnings.append('Hay grupos con menos de 10 observaciones; revisa distribución y robustez antes de concluir.')
    if result.method == 'welch_t':
        result.warnings.append('d y g usan SD combinada como estandarizador descriptivo. Con varianzas distintas su interpretación requiere cautela; no reemplaza el error estándar de Welch.')
    result.warnings.extend(CATALOG[result.method].limitations)
    charts.box(arrays, labels, label(outcome, prepared))
    result.interpretation = f'Se analizó {outcome.column} por {group.column} mediante {CATALOG[result.method].name}, confirmado antes de calcular. ' + inference_text(computed['p'], 1 - spec.confidence_level)
    if 'difference' in computed:
        result.interpretation += f' Diferencia (grupo 1 − grupo 2) = {computed["difference"]:.6g}; d = {computed["cohen_d"]:.4g}; g = {computed["hedges_g"]:.4g}. Evalúa su magnitud en las unidades y el contexto del estudio; no se aplican umbrales universales.'
    elif 'eta_squared' in computed:
        result.interpretation += f' η² clásico = {computed["eta_squared"]:.4g}: proporción descriptiva de variación atribuida al factor en esta muestra.'
    else:
        result.interpretation += ' No hay un tamaño del efecto global específico de Welch implementado.'
    result.interpretation += ' Un contraste global no identifica qué pares difieren. No se demuestra causalidad.' if not result.method.endswith('_t') else ' El diseño determina si puede sostenerse una interpretación causal; este cálculo por sí solo no la demuestra.'


DISPATCH = {'descriptive': describe, 'pearson': correlate, 'spearman': correlate,
            'student_t': compare, 'welch_t': compare, 'anova': compare, 'welch_anova': compare}


def run_component(source, prepared, component, spec, prefix, scope):
    result = ComponentResult(source_index=component.source_index, method=component.method, title=CATALOG[component.method].name,
                             status='completed', variables=source.variables, scope=scope,
                             sample={'file_id': prepared.file_id, 'sheet': prepared.sheet, 'initial': prepared.initial,
                                     'after_filters': len(prepared.rows), 'excluded_filters': prepared.filtered_out})
    charts = Charts(prefix)
    try:
        if component.method == 'descriptive':
            describe(result, source, prepared, spec, charts)
        elif component.method in {'pearson', 'spearman'}:
            correlate(result, source, prepared, spec, charts)
        else:
            compare(result, source, prepared, component, spec, charts)
        result.charts = list(charts.resources)
        if len(charts.resources) == 8:
            result.warnings.append('Límite de 8 gráficos por componente; las tablas contienen todas las variables calculadas.')
    except (AnalysisError, ValueError, FloatingPointError, OverflowError) as exc:
        result.status, result.error = 'failed', str(exc)
        result.tables, result.charts, result.statistics = [], [], {}
        charts.resources = {}
        result.interpretation = f'No se pudo ejecutar este componente: {exc}'
    return result, charts.resources
