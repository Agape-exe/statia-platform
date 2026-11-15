"""Viabilidad y decisiones de planificación; no ejecuta pruebas estadísticas."""
import re
from app.services.conversation_text import normalize
from app.services.independence import validate_independence


def validate_objective_columns(plan, files, context=None):
    """Referencias comprobables en prosa y componentes, sin diccionario por dataset."""
    def mentioned(name, text):
        if len(name) < 3 and '_' not in name:
            return f'`{name}`' in text
        name = re.escape(normalize(name)).replace('_', r'[ _]')
        return bool(re.search(r'(?<!\w)' + name + r'(?!\w)', normalize(text)))

    def check(text, variables):
        selected = {_key(v) for v in variables}
        for file in files.values():
            for column in file['metadata'].get('profile', {}).get('columns', []):
                if mentioned(column['name'], text) and not any(key[2] == column['name'] for key in selected):
                    raise ValueError(f'El objetivo o método promete analizar {column["name"]}, pero no está declarada entre sus variables. Alinea objetivo, método y selección.')
    check(plan.objective + '\n' + plan.method, plan.variables)
    # La prosa nueva debe ser auditable aun cuando las etiquetas sean traducciones.
    # Los planes anteriores siguen legibles; su aceptación repetida no los reinterpreta.
    if (context or {}).get('canonical_objectives'):
        if any(not mentioned(v.column, plan.objective) for v in plan.variables if v.role in ('outcome', 'predictor')):
            raise ValueError('El objetivo debe identificar por su nombre exacto todas las columnas de resultado o predictoras que promete analizar, junto a las etiquetas legibles. Alinea también método y componentes.')
    for step in plan.components:
        check(step.method, step.variables)
    validate_independence('\n'.join([plan.objective, plan.method, plan.justification, *plan.requirements, *plan.limitations]), context, require_pending=False)
    if plan.procedure == 'integral':
        used = {_key(v) for step in plan.components for v in step.variables}
        selectors = ([s.variable for s in plan.comparison.filters] + ([plan.comparison.strata.variable] if plan.comparison.strata else [])) if plan.comparison else []
        used.update(_key(v) for v in selectors)
        if any(_key(v) not in used for v in plan.variables):
            raise ValueError('Cada variable del plan integral debe participar en un componente, filtro o estrato declarado.')


def available_analyses(files):
    available = {'descriptive'} if any(f['metadata'].get('profile') for f in files) else set()
    for file in files:
        columns = file['metadata'].get('profile', {}).get('columns', [])
        quantitative = [c for c in columns if c['statistical_type'] == 'quantitative' and not c['possible_identifier'] and not c['possible_temporal'] and c.get('min') != c.get('max')]
        groups = [c for c in columns if c['statistical_type'] in ('categorical', 'categorical_or_ordinal') and 2 <= c['unique'] <= 20 and not c['possible_identifier']]
        if len(quantitative) >= 2:
            available.add('correlation')
        if quantitative and groups:
            available.add('group_comparison')
    if len(available) >= 2:
        available.add('integral')
    return sorted(available)


def is_welch_t(method):
    return bool(re.search(r'welch', method, re.I)) and not bool(re.search(r'anova', method, re.I))


def _key(variable):
    return variable.file_id, variable.sheet, variable.column


def levels(column):
    return {str(level['value']) for level in column.get('levels', column.get('distribution', []))}


def validate_methodology(plan, column_for, context=None):
    context = context or {}
    selections = {_key(v) for v in plan.variables}
    if plan.procedure == 'integral':
        if len(plan.components) < 2 or len({s.procedure for s in plan.components}) < 2:
            raise ValueError('El plan integral debe declarar al menos dos procedimientos distintos, pertinentes y verificables en components.')
    elif plan.components:
        raise ValueError('Solo un plan integral puede agrupar componentes.')
    steps = plan.components if plan.procedure == 'integral' else [plan]
    has_welch = False
    for step in steps:
        if step.procedure == 'integral':
            raise ValueError('No anidar planes integrales.')
        if plan.procedure == 'integral' and step.procedure == 'inferential':
            raise ValueError('El componente integral debe especificar una familia verificable, no un procedimiento inferencial arbitrario.')
        if any(_key(v) not in selections for v in step.variables):
            raise ValueError('Las variables de cada componente deben estar declaradas en el plan integral.')
        columns = [column_for(v) for v in step.variables]
        numeric = [c for c in columns if c['physical_type'] == 'numeric' and not c['possible_identifier'] and not c['possible_temporal']]
        varying = [c for c in numeric if 'min' not in c or c.get('min') != c.get('max')]
        if step.procedure == 'correlation' and len({_key(v) for v, c in zip(step.variables, columns) if c in varying}) < 2:
            raise ValueError('Cada correlación requiere dos variables numéricas distintas, sin identificadores ni años.')
        if step.procedure == 'group_comparison':
            outcomes = [c for v, c in zip(step.variables, columns) if v.role == 'outcome']
            groups = [c for v, c in zip(step.variables, columns) if v.role == 'group']
            if not outcomes or any(c not in numeric for c in outcomes) or not groups or any(c['unique'] < 2 or c['possible_identifier'] for c in groups):
                raise ValueError('La comparación requiere resultados numéricos y variables de grupo válidas.')
        if step.procedure == 'paired_comparison' and sum(v.role == 'outcome' and c in numeric for v, c in zip(step.variables, columns)) < 2:
            raise ValueError('La comparación pareada del componente requiere las dos mediciones numéricas correspondientes.')
        if is_welch_t(step.method):
            has_welch = True
            if step.procedure != 'group_comparison' or not plan.comparison:
                raise ValueError('Para una t de Welch define comparison: diseño, grupos, alcance, casos válidos, supuestos y tamaño del efecto.')
            if any(c['statistical_type'] != 'quantitative' for v, c in zip(step.variables, columns) if v.role == 'outcome'):
                raise ValueError('Welch necesita una medida cuantitativa confirmada, no un año, código o escala ambigua.')
            if any(c not in varying for v, c in zip(step.variables, columns) if v.role == 'outcome'):
                raise ValueError('No recomendar Welch para una variable de resultado constante.')
    comparison = plan.comparison
    if not comparison:
        return
    validate_independence(comparison.independence, context)
    if not any(s.procedure in ('group_comparison', 'paired_comparison') for s in steps):
        raise ValueError('Los detalles de comparación deben corresponder a un componente comparativo.')
    if has_welch and comparison.design != 'independent':
        raise ValueError('No recomendar Welch de muestras independientes para datos pareados o diseño desconocido; solicita aclaración.')
    if has_welch and comparison.variance_assumption != 'unequal_allowed':
        raise ValueError('Welch no requiere igualdad de varianzas.')
    if len(set(comparison.groups)) != 2:
        raise ValueError('Welch requiere dos grupos distintos explícitos.')
    group_columns = [column_for(v) for step in steps for v in step.variables if v.role == 'group']
    if not any(set(comparison.groups) <= levels(c) for c in group_columns):
        raise ValueError('Los grupos seleccionados no existen en las variables de agrupación.')
    for column in group_columns:
        ordinary = levels(column) - set(column.get('ambiguous_missing', {}))
        narrowed = any(s.variable.column == column['name'] and set(s.values) == set(comparison.groups) for s in comparison.filters)
        if set(comparison.groups) <= ordinary and len(ordinary) > 2 and not narrowed:
            raise ValueError('Hay más de dos grupos ordinarios: considera un análisis global como ANOVA, o solicita una elección explícita antes de excluir grupos de una t de Welch.')
    for selection in comparison.filters + ([comparison.strata] if comparison.strata else []):
        column = column_for(selection.variable)
        if not set(selection.values) <= levels(column):
            raise ValueError('El filtro o los estratos deben seleccionar categorías reales del archivo.')
        if _key(selection.variable) not in selections:
            raise ValueError('Declara también en variables la columna de filtros o estratos.')
    scope = context.get('comparison_scope')
    if scope:
        selected = comparison.strata if scope['mode'] == 'all' else next((s for s in comparison.filters if s.variable.column == scope['column'] and s.variable.file_id == scope['file_id']), None)
        if not selected or selected.variable.file_id != scope['file_id'] or selected.variable.column != scope['column'] or set(selected.values) != set(scope['values']):
            raise ValueError('Respeta la especie o las especies elegidas explícitamente; no amplíes el alcance.')
        if scope['mode'] == 'single' and comparison.strata:
            raise ValueError('El usuario eligió una sola especie; no crear comparaciones por varios estratos.')
    elif comparison.strata:
        raise ValueError('Antes de comparar por varios estratos, pregunta y registra el alcance elegido por el usuario.')
    if not re.search(r'gr[aá]fic|q.?q|tama[nñ]o|distribuci|robust|asimetr', comparison.normality, re.I):
        raise ValueError('Evaluar normalidad por grupo con gráficos/distribución y tamaño muestral, no solo un test automático.')
    effect = comparison.effect_size
    if (effect.name == 'mean_difference') != (effect.standardizer == 'none'):
        raise ValueError('Define un estandarizador para los efectos estandarizados; la diferencia de medias conserva sus unidades.')
    if not re.search(r'media|mean|promedio', effect.definition, re.I):
        raise ValueError('Documenta la diferencia de medias y la fórmula o definición del tamaño del efecto.')
    if effect.standardizer == 'pooled_sd' and not re.search(r'combinad|pooled|n_?1|n₁', effect.definition, re.I):
        raise ValueError('Para d o g combinadas, define explícitamente la desviación estándar combinada y sus ponderaciones.')
    if effect.standardizer == 'average_variance_sd' and not re.search(r'promedio.*varianz|average.*varian|s.?1.*s.?2|s₁.*s₂', effect.definition, re.I):
        raise ValueError('Define el estandarizador alternativo mediante la raíz del promedio de varianzas de ambos grupos.')
    if effect.name == 'glass_delta' and effect.standardizer != 'reference_group_sd':
        raise ValueError('Glass delta requiere la desviación estándar de un grupo de referencia explícito.')
    if effect.standardizer == 'reference_group_sd' and not any(group.lower() in effect.definition.lower() for group in comparison.groups):
        raise ValueError('Identifica qué grupo aporta la desviación estándar de referencia.')
    if effect.name == 'hedges_g' and (re.search(r'no aplica|ninguna|sin correcci', effect.correction, re.I) or not re.search(r'J|Hedges|factor|sesgo', effect.correction, re.I)):
        raise ValueError('g de Hedges debe documentar su factor de corrección por sesgo.')
    if effect.name == 'hedges_g' and not re.search(r'df|\bgl\b|grados|n_?1|n₁', effect.correction, re.I):
        raise ValueError('Documenta los grados de libertad o tamaños de grupo usados por la corrección de Hedges.')
    if effect.name == 'hedges_g' and effect.standardizer == 'pooled_sd':
        correction = normalize(effect.correction).translate(str.maketrans('₁₂−', '12-'))
        correction = re.sub(r'[\s_{}()]', '', correction)
        if not re.search(r'n1\+n2-2', correction) or re.search(r'j(?:df|gl|ν)?welch|(?:df|gl|ν)h=(?:welch|satterthwaite|νw|dfw)', correction):
            raise ValueError('Con SD combinada, Hedges usa ν_H=n1+n2−2 en J(ν_H); no usar los grados de libertad Welch–Satterthwaite del contraste. Diferencia ambos y conserva el IC previsto.')
    if effect.standardizer == 'pooled_sd' and not any(re.search(r'varianz|heterog|estandariz|combinad', limitation, re.I) for limitation in plan.limitations):
        raise ValueError('Explica la interpretación y limitación de un estandarizador combinado con varianzas potencialmente distintas.')
    if comparison.strata and len(comparison.strata.values) > 1 and comparison.purpose == 'confirmatory' and comparison.multiplicity == 'pending':
        raise ValueError('Antes de confirmar múltiples contrastes, define y justifica una estrategia de multiplicidad (por ejemplo Holm).')
    contrasts = max(1, len(comparison.strata.values) if comparison.strata else 1) * len({
        _key(v) for step in steps if is_welch_t(step.method) for v in step.variables if v.role == 'outcome'})
    if contrasts == 1 and comparison.multiplicity == 'holm':
        raise ValueError('Este plan contiene un solo contraste; no aplicar Holm arbitrariamente sin una familia de comparaciones declarada.')
