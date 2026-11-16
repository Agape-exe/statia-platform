"""Precisión numérica: casos analíticos, fracciones exactas y referencias SciPy independientes del motor.

Tolerancia rtol 1e-10/abs 1e-12 para float64; IC de tablas impresas 1e-6.
Los archivos públicos son fixtures originales existentes, nunca reglas de selección.
"""
import base64
import copy
import csv
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from scipy import stats

from app.core.config import Settings
from app.models.analysis import ExecutionSpec
from app.models.chat import Plan
from app.services.analysis_exports import build_exports, table_csv
from app.services.statistics.engine import calculate
from app.services.statistics.numerics import correlation, holm, mean_summary, one_way, two_groups
from app.services.statistics.preparation import AnalysisError, prepare, validate_spec


def test_descriptive_analytical():
    result = mean_summary([1, 2, 3, 4, 5], .95)
    for name, expected in {'n': 5, 'mean': 3, 'median': 3, 'sd': math.sqrt(2.5), 'variance': 2.5,
                           'min': 1, 'max': 5, 'range': 4, 'q1': 2, 'q3': 4, 'iqr': 2}.items():
        assert result[name] == pytest.approx(expected, rel=1e-10)
    assert result['modes'] == []
    assert result['mean_ci']['low'] == pytest.approx(1.03675684, abs=1e-8)
    assert result['mean_ci']['high'] == pytest.approx(4.96324316, abs=1e-8)
    assert mean_summary([1, 1, 2, 2, 3], .95)['modes'] == [1, 2]
    assert mean_summary([2], .95)['variance'] is None
    assert mean_summary([2, 2], .95)['mean_ci'] is None


@pytest.mark.parametrize('method', ['student_t', 'welch_t'])
def test_two_group_analytical_and_independent_reference(method):
    a, b = [1, 2, 3], [2, 4, 6, 8]
    result = two_groups(a, b, method, .95)
    expected_df = 5 if method == 'student_t' else 216 / 53
    expected_se = math.sqrt(77 / 30) if method == 'student_t' else math.sqrt(2)
    assert result['t'] == pytest.approx(-3 / expected_se, rel=1e-12)
    assert result['df'] == pytest.approx(expected_df, rel=1e-12)
    assert result['cohen_d'] == pytest.approx(-3 / math.sqrt(22 / 5), rel=1e-12)
    exact_j_df5 = 3 * math.sqrt(math.pi) / (4 * math.sqrt(2.5))
    assert result['hedges_J'] == pytest.approx(exact_j_df5, rel=1e-12)
    assert result['hedges_g'] == pytest.approx(exact_j_df5 * result['cohen_d'], rel=1e-12)
    assert result['hedges_df'] == 5  # NO los 216/53 de Welch.
    reference = stats.ttest_ind(a, b, equal_var=method == 'student_t')
    assert result['p'] == pytest.approx(reference.pvalue, rel=1e-12)
    interval = reference.confidence_interval(.95)
    assert result['difference_ci']['low'] == pytest.approx(interval.low, rel=1e-12)
    assert result['difference_ci']['high'] == pytest.approx(interval.high, rel=1e-12)


@pytest.mark.parametrize('method', ['anova', 'welch_anova'])
def test_anova_rational_reference(method):
    groups = [[1, 2, 3], [2, 4, 6, 8], [3, 6, 9, 12, 15]]
    result = one_way(groups, method)
    if method == 'anova':
        assert result['F'] == pytest.approx(10467 / 2688, rel=1e-12)
        assert result['df_within'] == 9
        assert result['eta_squared'] == pytest.approx(1163 / 2507, rel=1e-12)
    else:
        # Reducción racional de la ecuación de Welch para n=(3,4,5), medias=(2,5,9), s²=(1,20/3,45/2).
        assert result['F'] == pytest.approx(4736880 / 795539, rel=1e-12)
        assert result['df_within'] == pytest.approx(473344 / 85523, rel=1e-12)
        assert result['p'] == pytest.approx(.041723446788279044, rel=1e-10)
        assert result['effect_global'] is None
        assert 'eta_squared' not in result
    reference = stats.f_oneway(*groups, equal_var=method == 'anova')
    assert result['F'] == pytest.approx(reference.statistic, rel=1e-12)
    assert result['p'] == pytest.approx(reference.pvalue, rel=1e-12)


def test_correlation_analytical_and_fisher():
    pearson = correlation([1, 2, 3], [1, 2, 4], 'pearson', .95)
    assert pearson['coefficient'] == pytest.approx(math.sqrt(27 / 28), rel=1e-12)
    assert pearson['ci'] is None
    spearman = correlation([1, 2, 3, 4, 5], [1, 3, 2, 5, 4], 'spearman', .95)
    assert spearman['coefficient'] == pytest.approx(.8, rel=1e-12)
    assert spearman['p'] == pytest.approx(.10408803866182788, rel=1e-12)
    x, y = np.arange(10.), np.array([1, 0, 2, 4, 3, 7, 6, 5, 9, 8.])
    result = correlation(x, y, 'pearson', .95)
    z = np.arctanh(result['coefficient'])
    # Cuantil normal 0.975 de tabla, independiente del método confidence_interval de SciPy.
    assert result['ci']['low'] == pytest.approx(np.tanh(z - 1.959963984540054 / math.sqrt(7)), abs=1e-12)
    assert result['ci']['high'] == pytest.approx(np.tanh(z + 1.959963984540054 / math.sqrt(7)), abs=1e-12)


@pytest.mark.parametrize('method', ['student_t', 'welch_t'])
@pytest.mark.parametrize('a,b', [([1], [2, 3]), ([1, 1], [2, 3]), ([], [1, 2])])
def test_invalid_samples(method, a, b):
    with pytest.raises(AnalysisError):
        two_groups(a, b, method, .95)


def test_holm_known_values_and_order():
    assert holm([.01, .04, .03, .2]) == pytest.approx([.04, .09, .09, .2])


def job_for(data=b'cantidad,estrato,otra\n1,A,2\n2,A,4\n3,A,3\n2,B,5\n4,B,7\n6,B,9\n', procedure='group_comparison', methods=None):
    fid = str(uuid4())
    variables = [{'file_id': fid, 'sheet': 'tabla', 'column': column, 'role': role}
                 for column, role in [('cantidad', 'outcome'), ('estrato', 'group'), ('otra', 'predictor')]]
    selected = variables[:2] if procedure == 'group_comparison' else [variables[0], variables[2]]
    plan = {'schema_version': 1, 'title': 'Medidas arbitrarias', 'objective': 'Analizar medidas', 'variables': selected, 'procedure': procedure,
            'method': 'Método por confirmar', 'justification': 'Contrastar medidas válidas', 'requirements': ['Revisar diseño'],
            'limitations': ['Sin causalidad'], 'expected_outputs': ['Tablas y gráficos']}
    decisions = [{'variable': v, 'statistical_type': 'nominal' if v['role'] == 'group' else 'continuous'} for v in selected]
    spec = ExecutionSpec.model_validate({'components': [{'source_index': 0, 'method': (methods or ['welch_t'])[0], 'design': 'independent'}],
                                        'decisions': decisions, 'decisions_confirmed': True}).model_dump(mode='json')
    return {'run_id': str(uuid4()), 'project_id': str(uuid4()), 'conversation_id': str(uuid4()), 'proposal_id': str(uuid4()),
            'plan': plan, 'specification': spec, 'files': [{'id': fid, 'original_name': 'arbitrario.csv', 'file_type': 'csv',
                                                        'metadata': {'selected_sheet': 'tabla'}, 'data': base64.b64encode(data).decode('ascii')}]}


def test_full_engine_exports_precision_and_hashes():
    job = job_for()
    result, charts = calculate(job)
    assert result['status'] == 'completed'
    assert result['components'][0]['statistics']['difference'] == -2
    assert result['files'][0]['sha256'] == hashlib.sha256(base64.b64decode(job['files'][0]['data'])).hexdigest()
    assert charts and all(data.startswith(b'\x89PNG') for data in charts.values())
    json.dumps(result, allow_nan=False)
    exports = build_exports(result, charts)
    with zipfile.ZipFile(io.BytesIO(exports['resultados_analisis.zip'][0])) as archive:
        assert archive.testzip() is None
        assert json.loads(archive.read('resultados.json')) == result
        manifest = json.loads(archive.read('manifiesto.json'))
        for item in manifest['resources']:
            assert hashlib.sha256(archive.read(item['name'])).hexdigest() == item['sha256']
        assert not any('arbitrario.csv' in name for name in archive.namelist())
        assert next(csv.reader(io.StringIO(archive.read('tablas/componente_1_tabla_1.csv').decode('utf-8-sig'))))[0] == 'Variable'


def test_missing_markers_require_decision_and_preserve_original():
    data = b'cantidad,estrato,otra\n1,A,2\n2,A,3\nNA,A,4\n4,B,5\n5,B,7\n6,B,8\n'
    job = job_for(data)
    original = copy.deepcopy(job)
    with pytest.raises(AnalysisError, match='marcador'):
        calculate(job)
    job['specification']['decisions'][0]['missing_markers'] = ['NA']
    result, _ = calculate(job)
    assert result['components'][0]['sample']['excluded_missing'] == 1
    assert job['files'] == original['files']


def test_mixed_values_are_never_silently_dropped():
    job = job_for(b'cantidad,estrato,otra\n1,A,2\nerror,A,3\n3,A,4\n4,B,5\n5,B,7\n6,B,8\n')
    with pytest.raises(AnalysisError, match='no numéricos'):
        calculate(job)


def test_invalid_specs_and_unresolved_method():
    job = job_for()
    plan, spec = Plan.model_validate(job['plan']), ExecutionSpec.model_validate(job['specification'])
    validate_spec(plan, spec)
    for bad in [spec.model_copy(update={'decisions_confirmed': False}), spec.model_copy(update={'components': []}),
                spec.model_copy(update={'decisions': spec.decisions[:1]})]:
        with pytest.raises(AnalysisError):
            validate_spec(plan, bad)
    spec.components[0].method = 'student_t'
    with pytest.raises(AnalysisError, match='igualdad'):
        validate_spec(plan, spec)


def test_ordinal_pearson_rejected_spearman_explicit_order():
    job = job_for(b'cantidad,otra\nbajo,1\nmedio,3\nalto,2\nbajo,2\nmedio,4\nalto,5\n', 'correlation', ['pearson'])
    job['specification']['decisions'][0].update(statistical_type='ordinal', ordinal_order=['bajo', 'medio', 'alto'])
    with pytest.raises(AnalysisError, match='Pearson'):
        calculate(job)
    job['specification']['components'][0]['method'] = 'spearman'
    result, _ = calculate(job)
    assert result['status'] == 'completed'
    assert any('empates' in warning for warning in result['components'][0]['warnings'])


def test_integral_preserves_failed_component_and_reports_partial():
    job = job_for(b'cantidad,estrato,otra\n1,A,2\n1,A,3\n1,A,4\n1,B,5\n1,B,7\n1,B,8\n')
    variables = job['plan']['variables']
    job['plan'].update(procedure='integral', components=[{'procedure': 'descriptive', 'method': 'Descripción', 'variables': variables},
                                                       {'procedure': 'group_comparison', 'method': 'Comparación', 'variables': variables}])
    job['specification']['components'] = [{'source_index': 0, 'method': 'descriptive'}, {'source_index': 1, 'method': 'welch_t', 'design': 'independent'}]
    result, _ = calculate(job)
    assert result['status'] == 'partial'
    assert [c['status'] for c in result['components']] == ['completed', 'failed']
    assert 'varianza nula' in result['components'][1]['error']
    assert '1 de 2' in result['summary']


def test_constant_correlations_and_pairwise_exclusions():
    job = job_for(b'cantidad,otra\n1,2\n2,4\n3,\n4,7\n,8\n', 'correlation', ['pearson'])
    result, _ = calculate(job)
    pair = result['components'][0]['statistics']['pairs'][0]
    assert pair['n'] == 3
    assert pair['excluded_missing'] == 2
    assert pair['ci'] is None
    job['files'][0]['data'] = base64.b64encode(b'cantidad,otra\n1,2\n1,4\n1,6\n').decode('ascii')
    result, charts = calculate(job)
    assert result['status'] == 'failed' and charts == {}
    assert 'Ninguna pareja' in result['components'][0]['error']


def fixture_job(name, columns, family, method, filters=()):
    data = (Path(__file__).parent / 'fixtures' / name).read_bytes()
    job = job_for(data, family, [method])
    fid = job['files'][0]['id']
    variables = [{'file_id': fid, 'sheet': 'tabla', 'column': name, 'role': role} for name, role, _ in columns]
    job['plan']['variables'] = variables
    job['specification']['decisions'] = [{'variable': v, 'statistical_type': kind, 'missing_markers': ['NA']} for v, (_, _, kind) in zip(variables, columns)]
    job['files'][0]['original_name'] = name
    return job


def test_penguins_and_titanic_originals():
    job = fixture_job('penguins.csv', [('bill_length_mm', 'outcome', 'continuous'), ('flipper_length_mm', 'predictor', 'continuous')], 'correlation', 'pearson')
    result, _ = calculate(job)
    pair = result['components'][0]['statistics']['pairs'][0]
    assert pair['n'] == 342
    assert pair['coefficient'] == pytest.approx(.656181340746427, rel=1e-10)
    job = fixture_job('titanic.csv', [('age', 'outcome', 'continuous'), ('fare', 'predictor', 'continuous')], 'correlation', 'pearson')
    result, _ = calculate(job)
    pair = result['components'][0]['statistics']['pairs'][0]
    assert pair['n'] == 714
    assert pair['coefficient'] == pytest.approx(.0960666917690389, rel=1e-10)


def test_csv_formula_protection_keeps_numbers():
    data = table_csv({'columns': ['=celda', 'Medida'], 'rows': [{'=celda': '@texto', 'Medida': -1.25}]})
    assert data.decode('utf-8-sig') == "'=celda,Medida\r\n'@texto,-1.25\r\n"
