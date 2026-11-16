"""Resumen agregado para preguntas posteriores; jamás envía filas originales al proveedor."""
import json
import math
import re

from app.models.analysis import AnalysisResult
from app.services.planning_errors import PlanningError


async def saved_results_context(store, conversation):
    rows = await store.rows('analysis_runs', {'conversation_id': conversation['id'], 'project_id': conversation['project_id'],
                                             'status': ['completed', 'partial']}, order='created_at.desc', limit=3,
                            select='id,title,created_at,status,result')
    summaries = []
    for row in rows:
        try:
            result = AnalysisResult.model_validate(row['result'])
        except (ValueError, TypeError):
            continue  # No usar JSON alterado o incompatible como evidencia numérica.
        summary = {'run_id': row['id'], 'title': row['title'], 'date': row['created_at'], 'status': row['status'],
                   'confidence_level': result.specification.confidence_level, 'multiplicity': result.specification.multiplicity,
                   'components': [{'method': c.method, 'scope': c.scope, 'variables': [v.column for v in c.variables],
                                   'sample': c.sample, 'statistics': c.statistics, 'status': c.status, 'error': c.error,
                                   'warnings': c.warnings[:4]} for c in result.components]}
        if len(json.dumps(summaries + [summary], ensure_ascii=False)) <= 16000:
            summaries.append(summary)
    return summaries


def validate_numeric_claims(text, context):
    claims = list(re.finditer(r'(?i)\b(p|t|f|r|rho|d|g|chi2|χ²)\s*(?:\([^)]{0,40}\))?\s*(=|<)\s*([-+]?\d*[.,]?\d+(?:e[-+]?\d+)?)', text))
    if not claims:
        return
    results = (context or {}).get('analysis_results', [])
    if not results:
        raise PlanningError('response_content', 'No presentes estadísticos inferenciales calculados: solo se preparan planes cuando no hay resultados guardados.')
    values = {name: [] for name in ['p', 't', 'f', 'r', 'rho', 'd', 'g', 'chi2', 'χ²']}
    for result in results:
        for component in result['components']:
            metrics = component['statistics']
            for symbol, name in [('p', 'p'), ('p', 'p_adjusted'), ('t', 't'), ('f', 'F'), ('d', 'cohen_d'), ('g', 'hedges_g')]:
                if isinstance(metrics.get(name), (int, float)):
                    values[symbol].append(metrics[name])
            for pair in metrics.get('pairs', []):
                for symbol, name in [('p', 'p'), ('p', 'p_adjusted'), ('r' if component['method'] == 'pearson' else 'rho', 'coefficient')]:
                    if isinstance(pair.get(name), (int, float)):
                        values[symbol].append(pair[name])
    for claim in claims:
        symbol, operator, literal = claim.groups()
        literal = literal.replace(',', '.')
        number = float(literal)
        decimals = len(literal.lower().split('e')[0].split('.')[1]) if '.' in literal else 0
        exponent = int(literal.lower().split('e')[1]) if 'e' in literal.lower() else 0
        tolerance = .500001 * 10. ** (exponent - decimals)
        valid = any((v < number if operator == '<' else math.isclose(v, number, rel_tol=1e-7, abs_tol=tolerance)) for v in values[symbol.lower()])
        if symbol.lower() == 'p' and operator == '=' and number == 0:
            valid = False  # No presentar p = 0.000, incluso si hubo underflow de float64.
        if not valid:
            raise PlanningError('response_content', 'La explicación incluye una cifra inferencial que no coincide con los resultados guardados. Usa solo valores calculados y su redondeo correcto.')
