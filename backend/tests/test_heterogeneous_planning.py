"""Regresiones públicas y sintéticas; las pruebas no llaman a Gemini ni a Supabase remoto."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.models.chat import AssistantReply, Turn
from app.services.gemini import build_context, validate_reply
from app.services.methodology import available_analyses
from app.services.planning_errors import PlanningError
from app.services.planning_validation import assess_reply
from app.services.profiling import inspect_file
from test_chat_api import api, new, turn, reply

FIXTURES = Path(__file__).parent / 'fixtures'
FILE_ID = '20000000-0000-0000-0000-000000000001'
REQUEST = 'Comprende el dataset, identifica tipos de variables, valores faltantes y columnas redundantes, y recomiéndame varias alternativas estadísticas, incluida una integral. No conozco estos datos.'
CAPTURE = json.loads((FIXTURES / 'titanic_planning_failures.json').read_text(encoding='utf-8'))


def public_files():
    return [{'id': FILE_ID, 'file_role': 'dataset', 'original_name': 'titanic.csv',
             'metadata': inspect_file('titanic.csv', (FIXTURES / 'titanic.csv').read_bytes(), 'dataset', Settings(_env_file=None))}]


def context(files, request=REQUEST):
    return build_context({'project_type': 'general'}, {'current_stage': 'goal'},
                         [{'role': 'user', 'content': request}], files,
                         Turn(request_id=uuid4(), content=request), Settings(_env_file=None))


def remap(value, file_id, columns=None):
    if value == FILE_ID: return file_id
    if isinstance(value, list): return [remap(v, file_id, columns) for v in value]
    if isinstance(value, dict):
        return {key: file_id if key == 'file_id' else columns.get(item, item) if key == 'column' and columns
                else remap(item, file_id, columns) for key, item in value.items()}
    if isinstance(value, str) and columns:
        for old, replacement in columns.items(): value = value.replace('`' + old + '`', '`' + replacement + '`')
    return value


def setup_public(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    response = client.post(path + '/files', files={'file': ('titanic.csv', (FIXTURES / 'titanic.csv').read_bytes(), 'text/csv')})
    assert response.status_code == 201
    return client, store, provider, path, response.json()['id']


def synthetic_files():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['row_id', 'flag_code', 'tier_code', 'segment', 'measure_cm', 'cost_usd', 'flag_label', 'segment_label', 'ambiguous'])
    for i in range(30):
        writer.writerow([i+1, i%2, i%3+1, ['A','B','C'][i%3], 'NA' if i==2 else 10+i/10,
                         '' if i==3 else 5+i*2.5, ['no','yes'][i%2], ['Alpha','Beta','Gamma'][i%3], 'mixed' if i%2 else '7'])
    return [{'id': FILE_ID, 'file_role': 'dataset', 'original_name': 'heterogeneo.csv',
             'metadata': inspect_file('heterogeneo.csv', output.getvalue().encode(), 'dataset', Settings(_env_file=None))}]


def plan(variables=None, **changes):
    variables = variables or [{'file_id': FILE_ID, 'sheet': 'tabla', 'column': 'measure_cm', 'role': 'outcome'}]
    return {'title': 'Describir mediciones', 'objective': 'Describir ' + ', '.join('`'+v['column']+'`' for v in variables),
            'variables': variables, 'procedure': 'descriptive', 'method': 'Resúmenes y frecuencias según el tipo de cada variable.',
            'justification': 'Exploración de un archivo heterogéneo.', 'requirements': ['Revisar significado, faltantes y diseño.'],
            'limitations': ['No inferir causalidad.'], 'expected_outputs': ['Tablas descriptivas en Sesión 03.'], **changes}


def test_original_csv_hash_types_missing_and_equivalent_columns_are_preserved():
    data = (FIXTURES / 'titanic.csv').read_bytes()
    assert hashlib.sha256(data).hexdigest() == '81787d320d7f7b03df935e91de8bd19e11d45c5bbcab86ef4d4a76dc91b7d4f2'
    rows = list(csv.DictReader(io.StringIO(data.decode())))
    profile = public_files()[0]['metadata']['profile']
    assert len(rows) == profile['row_count'] == 891
    assert profile['column_count'] == 15 and profile['missing_count'] == 869
    columns = {c['name']: c for c in profile['columns']}
    assert columns['survived']['physical_type'] == 'numeric'
    assert columns['survived']['statistical_type'] == columns['pclass']['statistical_type'] == 'categorical_or_ordinal'
    assert columns['age']['statistical_type'] == columns['fare']['statistical_type'] == 'quantitative'
    assert {name: columns[name]['missing'] for name in ('age','deck','embarked','embark_town')} == {'age':177,'deck':688,'embarked':2,'embark_town':2}
    # Lectura independiente del original: equivalencias conocidas no autorizan eliminar columnas.
    for left, right in [('survived','alive'), ('pclass','class'), ('embarked','embark_town')]:
        mapping = {r[left]: r[right] for r in rows}
        assert len(mapping) == len(set(mapping.values()))
        assert all(mapping[r[left]] == r[right] for r in rows)
        assert left in columns and right in columns


def test_synthetic_binary_ordinal_quantitative_missing_and_redundancy_are_general():
    files = synthetic_files()
    profile = files[0]['metadata']['profile']
    columns = {c['name']: c for c in profile['columns']}
    assert profile['row_count'] == 30 and profile['column_count'] == 9
    assert columns['flag_code']['physical_type'] == 'numeric'
    assert columns['flag_code']['statistical_type'] == columns['tier_code']['statistical_type'] == 'categorical_or_ordinal'
    assert columns['measure_cm']['statistical_type'] == columns['cost_usd']['statistical_type'] == 'quantitative'
    assert columns['measure_cm']['missing_inferred'] == columns['cost_usd']['missing_confirmed'] == 1
    assert columns['ambiguous']['inferred_type'] == 'mixed'
    assert columns['flag_label']['unique'] == columns['flag_code']['unique'] == 2
    assert set(available_analyses(files)) == {'descriptive','correlation','group_comparison','integral'}


@pytest.mark.parametrize('user_text', [
    'No conozco estos datos. Describe tipos, faltantes y redundancias.',
    'Solo necesito comprensión descriptiva, sin propuestas estadísticas.',
    'Recomiéndame más adelante; ahora quiero describir, sin planes.',
])
def test_description_is_valid_without_a_quota_of_plans(user_text):
    files = synthetic_files()
    ctx = context(files, user_text)
    assert ctx['recommendations_requested'] is False
    validate_reply(AssistantReply.model_validate(reply(response='Hay medidas y códigos; las equivalencias deben comprobarse.', proposals=[])), files, {'project_type':'general'}, ctx)


def test_descriptive_http_turn_persists_without_proposals_or_correction(api):
    client, store, provider, path, _ = setup_public(api)
    provider.replies.append(reply(response='El archivo tiene 891 registros y 15 columnas; existen variables cuantitativas y códigos categóricos.', suggested_stage='understanding'))
    assert turn(client, path, content='No conozco estos datos. Describe el dataset, sin propuestas.').status_code == 200
    detail = client.get(path).json()
    assert not detail['proposals'] and len(provider.contexts) == 1
    assert '891' in detail['messages'][-1]['content']


def test_real_captured_failures_identify_omissions_in_both_attempts():
    files = public_files()
    for attempt, expected in [('attempt_1', {'survived','sibsp','parch'}), ('attempt_2', {'sibsp','parch'})]:
        result = assess_reply(AssistantReply.model_validate(CAPTURE[attempt]), files, {'project_type':'general'}, context(files))
        issue = next(i for i in result.issues if i.plan_index == 0)
        assert issue.category == 'objective_variables'
        assert all(column in issue.message for column in expected)
        if attempt == 'attempt_1':
            assert any(i.plan_index == 3 and i.category == 'objective_variables' for i in result.issues)
        else:
            assert len(result.valid_plans) == 3


def test_both_failures_retain_only_valid_final_plans_and_are_idempotent(api, caplog):
    client, store, provider, path, fid = setup_public(api)
    provider.replies.extend(remap([CAPTURE['attempt_1'], CAPTURE['attempt_2']], fid))
    request_id = str(uuid4())
    response = turn(client, path, content=REQUEST, request_id=request_id)
    assert response.status_code == 200
    detail = client.get(path).json()
    assert {p['analysis_plan']['procedure'] for p in detail['proposals']} == {'correlation','group_comparison','integral'}
    assert len(provider.contexts) == 2
    correction = provider.contexts[1][1]
    assert all(column in correction for column in ('survived','sibsp','parch'))
    assert 'Propuesta 1' in correction and 'Propuesta 4' in correction
    message = detail['messages'][-1]
    assert 'Solo se muestran planes validados' in message['content']
    assert message['metadata']['planning_validation']['partial'] is True
    assert len(message['metadata']['planning_validation']['attempts']) == 2
    assert 'attempt=1' in caplog.text and 'attempt=2' in caplog.text and 'category=objective_variables' in caplog.text
    assert all(token not in caplog.text for token in ('survived','sibsp','titanic.csv',fid,REQUEST))
    before = copy.deepcopy(detail['proposals'])
    assert turn(client, path, content=REQUEST, request_id=request_id).json()['replayed']
    assert client.get(path).json()['proposals'] == before
    chosen = next(p for p in before if p['analysis_plan']['procedure'] == 'integral')
    assert client.patch(path+'/proposals/'+chosen['id'], json={'status':'accepted'}).status_code == 200
    saved = next(p for p in client.get(path).json()['proposals'] if p['id'] == chosen['id'])
    assert saved['status'] == 'accepted' and saved['analysis_plan'] == chosen['analysis_plan']


def test_all_invalid_plans_stay_failed_with_safe_diagnostics_and_retry(api, caplog):
    client, store, provider, path, fid = setup_public(api)
    invalid = remap(CAPTURE['attempt_1'], fid)
    for p in invalid['proposals']: p['variables'][0]['column'] = 'private_person@example.test'
    provider.replies.extend([invalid, copy.deepcopy(invalid)])
    request_id = str(uuid4())
    response = turn(client,path,content=REQUEST,request_id=request_id)
    assert response.status_code == 502
    assert response.headers['X-Statia-Error'] == 'planning_validation'
    assert 'column_reference' in response.headers['X-Statia-Validation']
    assert not client.get(path).json()['proposals']
    assert 'private_person' not in caplog.text
    # Corrección válida de la misma solicitud: ningún mensaje duplicado.
    valid = remap(CAPTURE['attempt_2'], fid)
    valid['proposals'] = valid['proposals'][1:]
    provider.replies.append(valid)
    assert turn(client,path,content=REQUEST,request_id=request_id).status_code == 200
    detail = client.get(path).json()
    assert len([m for m in detail['messages'] if m['role']=='user' and m['content']==REQUEST]) == 1
    assert len(detail['proposals']) == 3


def test_essential_clarification_never_salvages_plans_but_question_only_is_allowed(api):
    client, store, provider, path, fid = setup_public(api)
    blocked = remap(CAPTURE['attempt_2'],fid)
    blocked.update(questions=['¿Las mediciones corresponden al diseño informado?'], clarification_required=True)
    provider.replies.extend([blocked, copy.deepcopy(blocked)])
    assert turn(client,path,content=REQUEST).status_code == 502
    assert not client.get(path).json()['proposals']
    provider.replies.append(reply(questions=['¿Qué representa el código ordinal?'], clarification_required=True))
    assert turn(client,path,content=REQUEST).status_code == 200
    assert client.get(path).json()['conversation']['current_stage'] == 'clarification'


def test_categorical_numeric_codes_are_describable_but_not_unconfirmed_measures():
    files = synthetic_files()
    variables = [{'file_id':FILE_ID,'sheet':'tabla','column':c,'role':r} for c,r in [('flag_code','outcome'),('tier_code','group')]]
    validate_reply(AssistantReply.model_validate(reply(proposals=[plan(variables)])),files,{'project_type':'general'},context(files,'Describe códigos'))
    with pytest.raises(PlanningError, match='cuantitativa'):
        validate_reply(AssistantReply.model_validate(reply(proposals=[plan(variables,procedure='group_comparison',method='ANOVA de medias')])),files,{'project_type':'general'})
    variables[1]['role'] = 'predictor'
    with pytest.raises(PlanningError, match='códigos categóricos'):
        validate_reply(AssistantReply.model_validate(reply(proposals=[plan(variables,procedure='correlation',method='Correlación lineal de Pearson')])),files,{'project_type':'general'})


def test_same_validation_is_invariant_under_arbitrary_column_renaming():
    files = public_files()
    names = {c['name']: f'variable_{i:02d}' for i,c in enumerate(files[0]['metadata']['profile']['columns'])}
    renamed = copy.deepcopy(files)
    for column in renamed[0]['metadata']['profile']['columns']: column['name'] = names[column['name']]
    for key in ('attempt_1','attempt_2'):
        original = assess_reply(AssistantReply.model_validate(CAPTURE[key]),files,{'project_type':'general'},context(files))
        translated = assess_reply(AssistantReply.model_validate(remap(CAPTURE[key],FILE_ID,names)),renamed,{'project_type':'general'},context(renamed))
        assert [i.safe_metadata() for i in translated.issues] == [i.safe_metadata() for i in original.issues]
        assert len(translated.valid_plans) == len(original.valid_plans)


@pytest.mark.parametrize('status', [429,503,504])
def test_correction_provider_failure_is_not_hidden_by_partial_plans(api, status):
    client, store, provider, path, fid = setup_public(api)
    provider.replies.extend([remap(CAPTURE['attempt_1'],fid), HTTPException(status,'Fallo controlado del proveedor')])
    response = turn(client,path,content=REQUEST)
    assert response.status_code == status
    assert len(provider.contexts) == 2 and not client.get(path).json()['proposals']


def test_hedges_definition_and_correction_are_validated_together_without_weakening_df():
    from test_planning import welch_plan, penguins, scope
    p = welch_plan()
    effect = p['comparison']['effect_size']
    effect.update(name='hedges_g', definition='g=J(nu_H)*(mean1-mean2)/s_p; SD combinada, nu_H=n1+n2-2.',
                  correction='J(nu_H) aproximadamente 1-3/(4*nu_H-1); los gl de Welch son distintos.')
    validate_reply(AssistantReply.model_validate(reply(proposals=[p])),penguins(),{'project_type':'general'},scope())
    effect['correction'] = 'Usar J(df_Welch) para la corrección; el denominador combinado usa n1+n2-2.'
    with pytest.raises(PlanningError, match='Hedges usa'):
        validate_reply(AssistantReply.model_validate(reply(proposals=[p])),penguins(),{'project_type':'general'},scope())


def test_pending_clarification_without_an_actual_question_is_not_a_valid_reply():
    files = synthetic_files()
    with pytest.raises(PlanningError, match='preguntas esenciales'):
        validate_reply(AssistantReply.model_validate(reply(clarification_required=True)),files,{'project_type':'general'},context(files))


def test_partial_summary_respects_contract_while_full_plan_variables_remain_intact():
    from app.services.planning_validation import Assessment, retain_valid_plans
    from app.services.planning_errors import PlanningIssue
    files = synthetic_files()
    prototype = next(c for c in files[0]['metadata']['profile']['columns'] if c['name']=='measure_cm')
    files[0]['metadata']['profile']['columns'] = [{**prototype, 'name':f'measure_{i:02d}'} for i in range(70)]
    variables = [{'file_id':FILE_ID,'sheet':'tabla','column':c['name'],'role':'outcome'} for c in files[0]['metadata']['profile']['columns']]
    plans = [plan(variables[:40]),plan(variables[30:])]
    response = AssistantReply.model_validate(reply(proposals=plans, context_summary='No persistir prosa descartada'))
    assessment = Assessment(response.proposals,[PlanningIssue('recommendation_coverage','Faltan alternativas')],True)
    retained = retain_valid_plans(response,assessment,files,{'project_type':'general'},context(files))
    assert len(retained.selected_variables) == 60
    assert [len(p.variables) for p in retained.proposals] == [40,40]
    assert retained.context_summary is None and retained.suggested_stage == 'proposal'
    assert len({v.column for p in retained.proposals for v in p.variables}) == 70



def test_categorical_group_is_not_mistaken_for_a_continuous_correlation_measure():
    files = synthetic_files()
    variables = [{'file_id':FILE_ID,'sheet':'tabla','column':c,'role':r} for c,r in
                 [('measure_cm','outcome'),('cost_usd','predictor'),('segment','group')]]
    p = plan(variables, procedure='correlation', method='Correlación de measure_cm y cost_usd por segment; diseño a revisar.')
    validate_reply(AssistantReply.model_validate(reply(proposals=[p])),files,{'project_type':'general'},context(files,'Analizar asociación'))
    p['variables'] = p['variables'][1:]
    p['objective'] = 'Relacionar `cost_usd` con `segment`'
    p['method'] = 'Correlación de `cost_usd` con `segment`'
    with pytest.raises(PlanningError, match='dos variables numéricas'):
        validate_reply(AssistantReply.model_validate(reply(proposals=[p])),files,{'project_type':'general'})



def test_internal_humanization_failure_keeps_one_controlled_correction(api, caplog):
    client, store, provider, path, _ = setup_public(api)
    provider.replies.extend([reply(response='Hola.'),reply(response='Descripción sustantiva del dataset sin planes.',suggested_stage='understanding')])
    assert turn(client,path,content='Describe el dataset, sin propuestas.').status_code == 200
    assert len(provider.contexts) == 2
    detail = client.get(path).json()
    assert not detail['proposals']
    assert detail['messages'][-1]['metadata']['planning_validation']['partial'] is False
    assert 'category=internal_contract' in caplog.text and 'Hola.' not in caplog.text
