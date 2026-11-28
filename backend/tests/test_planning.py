import copy
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.chat import AssistantReply
from app.services.gemini import validate_reply
from app.services.methodology import available_analyses
from app.services.profiling import inspect_file
from test_chat_api import api as api, new, turn, reply  # Fixture HTTP con repositorio/proveedor controlados.

FILE_ID = '20000000-0000-0000-0000-000000000001'
DATA = (Path(__file__).parent / 'fixtures/penguins.csv').read_bytes()


def penguins():
    return [{'id': FILE_ID, 'original_name': 'penguins.csv', 'file_role': 'dataset',
             'metadata': inspect_file('penguins.csv', DATA, 'dataset', Settings())}]


def variable(column, role='outcome'):
    return {'file_id': FILE_ID, 'sheet': 'tabla', 'column': column, 'role': role}


def base_plan(procedure='descriptive', **kwargs):
    result = {'title': 'Explorar las medidas', 'objective': 'Conocer las características morfológicas',
            'variables': [variable('body_mass_g')], 'procedure': procedure, 'method': 'Resúmenes descriptivos',
            'justification': 'Hay medidas cuantitativas disponibles.', 'requirements': ['Revisar observaciones válidas'],
            'limitations': ['No inferir causalidad; considerar heterogeneidad de varianzas'],
            'expected_outputs': ['Tabla de resultados al ejecutar en Sesión 03'], **kwargs}

    if 'objective' not in kwargs:
        result['objective'] += ' (' + ', '.join(v['column'] for v in result['variables'] if v['role'] in ('outcome', 'predictor')) + ')'
    return result


def alternatives():
    quantitative = [variable('body_mass_g'), variable('flipper_length_mm')]
    grouped = [variable('body_mass_g'), variable('species', 'group')]
    return [base_plan(), base_plan('group_comparison', variables=grouped, method='Comparación entre especies; ANOVA condicionado al diseño y supuestos'),
            base_plan('correlation', variables=quantitative, method='Asociación sin causalidad; elegir Pearson/Spearman según distribución'),
            base_plan('integral', variables=quantitative + [variable('species', 'group')], method='Exploración, comparación y asociación pertinentes', components=[
                {'procedure': 'descriptive', 'method': 'Resúmenes', 'variables': quantitative},
                {'procedure': 'group_comparison', 'method': 'Comparación entre especies', 'variables': grouped},
                {'procedure': 'correlation', 'method': 'Relación entre medidas', 'variables': quantitative}])]


def welch_plan(all_species=False):
    selection = {'variable': variable('species', 'description'), 'values': ['Adelie', 'Chinstrap', 'Gentoo'] if all_species else ['Adelie']}
    return base_plan('group_comparison', title='Masa corporal entre sexos', method='t de Welch para dos muestras independientes',
        variables=[variable('body_mass_g'), variable('sex', 'group'), variable('species', 'description')], comparison={
            'design': 'independent', 'groups': ['male', 'female'],
            'filters': [] if all_species else [selection], 'strata': selection if all_species else None,
            'independence': 'Verificar con el diseño que cada fila sea un individuo distinto; no deducirlo solo del archivo.',
            'valid_observations': 'Usar filas válidas para masa, sexo y especie; informar n por grupo y exclusiones en ejecución.',
            'missing_data': 'Excluir del cálculo solo ausencias en variables necesarias y etiquetas no seleccionadas; no borrar filas originales.',
            'outliers': 'Revisar valores atípicos por grupo y su influencia sin eliminarlos automáticamente.',
            'normality': 'Revisar gráficos Q-Q y distribución por grupo con su tamaño muestral; Shapiro no será único criterio.',
            'variance_assumption': 'unequal_allowed',
            'effect_size': {'name': 'cohen_d', 'standardizer': 'pooled_sd',
                'definition': 'd=(mean1-mean2)/s_p; s_p=sqrt(((n1-1)*s1^2+(n2-1)*s2^2)/(n1+n2-2)), SD combinada ponderada.',
                'correction': 'No aplica corrección por sesgo para esta d; considerar g de Hedges como alternativa.',
                'confidence_interval': 'Estimar IC por remuestreo o método adecuado en ejecución y documentarlo.'},
            'purpose': 'exploratory', 'multiplicity': 'holm' if all_species else 'none',
            'multiplicity_reason': 'Varios contrastes exploratorios por especie: considerar Holm sin convertirlo en regla universal.' if all_species else 'Un solo contraste entre dos sexos en Adelie.'})


def validated(plan, context=None):
    return validate_reply(AssistantReply.model_validate(reply(proposals=[plan], suggested_stage='proposal')), penguins(), {'project_type': 'general'}, context)


def scope(mode='single'):
    return {'comparison_scope': {'file_id': FILE_ID, 'sheet': 'tabla', 'column': 'species', 'mode': mode,
                                  'values': ['Adelie', 'Chinstrap', 'Gentoo'] if mode == 'all' else ['Adelie']}}


def test_recommendation_viability_and_four_distinct_options_with_integral():
    assert set(available_analyses(penguins())) == {'descriptive', 'group_comparison', 'correlation', 'integral'}
    context = {'recommendations_requested': True, 'available_analyses': available_analyses(penguins())}
    result = AssistantReply.model_validate(reply(proposals=alternatives(), suggested_stage='proposal'))
    validate_reply(result, penguins(), {'project_type': 'general'}, context)
    result.proposals = result.proposals[:1]
    with pytest.raises(ValueError, match='alternativas'):
        validate_reply(result, penguins(), {'project_type': 'general'}, context)


def test_optional_questions_do_not_block_viable_general_plans_but_essential_ones_do():
    result = AssistantReply.model_validate(reply(proposals=alternatives(), questions=['¿Cuál opción prefieres?'], clarification_required=False))
    context = {'recommendations_requested': True, 'available_analyses': available_analyses(penguins())}
    validate_reply(result, penguins(), {'project_type': 'general'}, context)
    result.clarification_required = True
    with pytest.raises(ValueError, match='preguntas esenciales'):
        validate_reply(result, penguins(), {'project_type': 'general'}, context)
    # La metodología desconocida de tesis sí puede justificar preguntas antes de proponer.
    validate_reply(AssistantReply.model_validate(reply(questions=['¿Cuál es el diseño?'], clarification_required=True)), penguins(), {'project_type': 'thesis'}, context)


@pytest.mark.parametrize('kind', ['missing_component', 'arbitrary_component', 'categorical_correlation', 'invented_variable', 'temporal_outcome'])
def test_reject_infeasible_or_arbitrary_integral_components(kind):
    plan = alternatives()[-1]
    if kind == 'missing_component': plan['components'] = []
    elif kind == 'arbitrary_component': plan['components'][1]['procedure'] = 'inferential'
    elif kind == 'categorical_correlation': plan['components'][2]['variables'] = [variable('species', 'description'), variable('species', 'description')]
    elif kind == 'invented_variable': plan['components'][0]['variables'][0]['column'] = 'inexistente'
    else: plan['components'][1]['variables'][0] = variable('year'); plan['variables'].append(variable('year'))
    with pytest.raises(ValueError): validated(plan)


def test_welch_single_species_and_all_species_with_effect_definition():
    result = validated(welch_plan(), scope())
    assert result.proposals[0].comparison.effect_size.standardizer == 'pooled_sd'
    assert result.proposals[0].comparison.variance_assumption == 'unequal_allowed'
    result = validated(welch_plan(True), scope('all'))
    assert result.proposals[0].comparison.multiplicity == 'holm'
    assert len(result.proposals[0].comparison.strata.values) == 3


@pytest.mark.parametrize('kind', ['hedges', 'average_variance', 'glass'])
def test_effect_size_alternatives_are_defined_without_computing_them(kind):
    plan = welch_plan()
    effect = plan['comparison']['effect_size']
    if kind == 'hedges':
        effect.update(name='hedges_g', definition='g=J(df)*(mean1-mean2)/s_p, desviación combinada ponderada.',
                      correction='J(df) aproximadamente 1-3/(4*df-1), df=n1+n2-2; corrección por sesgo.')
    elif kind == 'average_variance':
        effect.update(standardizer='average_variance_sd', definition='(mean1-mean2)/sqrt((s1^2+s2^2)/2), raíz del promedio de varianzas.')
    else:
        effect.update(name='glass_delta', standardizer='reference_group_sd', definition='(mean_male-mean_female)/SD_female; female es el grupo de referencia.')
    if kind == 'hedges':
        validated(plan, scope())
    else:
        with pytest.raises(ValueError, match='no está implementado'):
            validated(plan, scope())


def test_constant_variables_are_not_correlation_recommendations():
    files = penguins()
    for column in files[0]['metadata']['profile']['columns']:
        if column['physical_type'] == 'numeric': column['min'] = column['max'] = 1
    assert 'correlation' not in available_analyses(files)
    with pytest.raises(ValueError):
        validate_reply(AssistantReply.model_validate(reply(proposals=[alternatives()[2]])), files, {'project_type': 'general'})


@pytest.mark.parametrize('issue', ['missing_details', 'paired', 'unknown_design', 'equal_variances', 'wrong_group', 'wrong_species', 'silent_strata', 'normality_only', 'effect_undefined', 'hedges_no_correction', 'single_holm', 'confirmatory_pending'])
def test_essential_welch_decisions_cannot_be_treated_as_confirmed(issue):
    plan = welch_plan()
    c = plan['comparison']
    context = scope()
    if issue == 'missing_details': plan['comparison'] = None
    elif issue == 'paired': c['design'] = 'paired'
    elif issue == 'unknown_design': c['design'] = 'unknown'
    elif issue == 'equal_variances': c['variance_assumption'] = 'equal_required'
    elif issue == 'wrong_group': c['groups'] = ['male', 'inventado']
    elif issue == 'wrong_species': c['filters'][0]['values'] = ['Gentoo']
    elif issue == 'silent_strata': plan = welch_plan(True)
    elif issue == 'normality_only': c['normality'] = 'Aplicar Shapiro y decidir automáticamente.'
    elif issue == 'effect_undefined': c['effect_size'].update(name='cohen_d', standardizer='none')
    elif issue == 'hedges_no_correction': c['effect_size'].update(name='hedges_g', correction='No aplica')
    elif issue == 'single_holm': c['multiplicity'] = 'holm'
    else: plan = welch_plan(True); context = scope('all'); plan['comparison'].update(purpose='confirmatory', multiplicity='pending')
    with pytest.raises(ValueError): validated(plan, context)


def attach_penguins(client, path):
    response = client.post(path + '/files', files={'file': ('penguins.csv', DATA, 'text/csv')})
    assert response.status_code == 201
    return response.json()['id']


def replace_file_ids(value, file_id):
    if isinstance(value, dict): return {k: file_id if k == 'file_id' else replace_file_ids(v, file_id) for k, v in value.items()}
    if isinstance(value, list): return [replace_file_ids(v, file_id) for v in value]
    return value


def test_system_actions_cannot_become_goal_but_explicit_exploration_can(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    attach_penguins(client, path)
    provider.replies.append(reply(detected_goal='Comprender los archivos adjuntos', suggested_title='Comprender archivos'))
    assert turn(client, path, action='files_ready').status_code == 200
    detail = client.get(path).json()
    assert detail['conversation']['primary_goal'] is None
    assert detail['conversation']['title'] == 'Exploración de archivos'
    assert detail['conversation']['stage_data']['title_provisional'] is True
    context = provider.contexts[0][0]
    assert context['turn']['kind'] == 'action'
    assert context['history'][-1]['kind'] == 'action' and context['history'][-1]['role'] == 'system'
    assert context['goal_evidence'] == []
    provider.replies.append(reply(detected_goal='Explorar las medidas', suggested_title='Exploración morfológica'))
    assert turn(client, path, content='Quiero explorar este dataset para comprenderlo.').status_code == 200
    assert client.get(path).json()['conversation']['primary_goal'] == 'Explorar las medidas'
    assert client.get(path).json()['conversation']['title'] == 'Exploración morfológica'
    client.patch(path, json={'title': 'Mi título manual'})
    provider.replies.append(reply(suggested_title='Otro título', goal_change=True, goal_change_reason='No debería cambiar por una aclaración', detected_goal='Otra finalidad'))
    assert turn(client, path, content='¿Puedes explicar qué significa Welch?').status_code == 200
    state = client.get(path).json()['conversation']
    assert state['title'] == 'Mi título manual' and not state['stage_data']['goal_change']


def test_explicit_goal_is_not_lost_when_model_does_not_summarize_it(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    attach_penguins(client, path)
    provider.replies.append(reply(detected_goal=None, suggested_title='Exploración'))
    request = 'Quiero explorar este dataset para comprenderlo.'
    assert turn(client, path, content=request).status_code == 200
    assert client.get(path).json()['conversation']['primary_goal'] == request


@pytest.mark.parametrize('answer', ['No', 'Continuar', 'No necesito agregar nada'])
def test_reuse_short_no_goes_to_goal_without_gemini_or_previous_goal(answer, api):
    client, store, provider = api
    old = new(client, store)
    turn(client, old, action='instrument_no')
    fid = attach_penguins(client, old)
    store.data['conversations'][0]['primary_goal'] = 'Objetivo anterior'
    old_messages = client.get(old).json()['messages']
    path = new(client, store)
    assert turn(client, path, action='reuse').status_code == 200
    assert turn(client, path, content=answer).status_code == 200
    detail = client.get(path).json()
    assert detail['conversation']['current_stage'] == 'goal'
    assert detail['conversation']['primary_goal'] is None
    assert 'penguins.csv' in detail['messages'][-1]['content']
    assert fid not in detail['messages'][-1]['content']
    assert 'Hola' not in detail['messages'][-1]['content']
    assert not provider.contexts
    assert len(store.objects) == 1 and detail['files'][0]['id'] == fid
    assert client.get(old).json()['messages'] == old_messages


@pytest.mark.parametrize('answer', ['Adelie; las observaciones son individuos diferentes.', 'No todas, solo Adelie; son individuos distintos.'])
def test_welch_ambiguous_scope_is_deterministic_then_selected_species_is_persisted(api, answer):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    fid = attach_penguins(client, path)
    request = 'Quiero comparar la masa corporal entre machos y hembras de una misma especie. Evalúa Welch y el efecto.'
    assert turn(client, path, content=request).status_code == 200
    detail = client.get(path).json()
    assert detail['conversation']['current_stage'] == 'clarification'
    assert 'una especie específica' in detail['messages'][-1]['content']
    assert detail['conversation']['title'] != 'Nueva conversación'
    assert detail['conversation']['stage_data']['title_provisional'] is True
    assert not detail['proposals'] and not provider.contexts
    provider.replies.append(reply(proposals=[replace_file_ids(welch_plan(), fid)], suggested_stage='proposal'))
    assert turn(client, path, content=answer).status_code == 200
    detail = client.get(path).json()
    assert detail['conversation']['stage_data']['comparison_scope']['values'] == ['Adelie']
    assert len(detail['proposals']) == 1
    proposal = detail['proposals'][0]
    assert client.patch(path + '/proposals/' + proposal['id'], json={'status': 'accepted'}).status_code == 200
    assert client.get(path).json()['proposals'][0]['analysis_plan']['comparison']['filters'][0]['values'] == ['Adelie']


def test_multiple_recommendations_can_select_one_without_deciding_others(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    fid = attach_penguins(client, path)
    provider.replies.extend([reply(proposals=[replace_file_ids(base_plan(), fid)]),
                             reply(proposals=replace_file_ids(alternatives(), fid), suggested_stage='proposal', detected_goal='Explorar morfología')])
    assert turn(client, path, content='No conozco el dataset. Recomiéndame los análisis más apropiados y alternativas.').status_code == 200
    detail = client.get(path).json()
    assert len(detail['proposals']) == 4
    assert provider.contexts[1][1]  # Una sola propuesta se corrigió, sin producir plantillas ficticias.
    choice = detail['proposals'][2]['id']
    assert client.patch(path + '/proposals/' + choice, json={'status': 'accepted'}).status_code == 200
    assert [p['status'] for p in client.get(path).json()['proposals']] == ['proposed', 'proposed', 'accepted', 'proposed']


def test_human_text_uses_names_and_keeps_internal_references(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    fid = attach_penguins(client, path)
    provider.replies.append(reply(response=f'¡Hola! Soy tu asistente estadístico. Revisé {fid}; las medidas ya son numéricas.',
                                  questions=[f'¿Qué deseas analizar de {fid}?']))
    assert turn(client, path, action='files_ready').status_code == 200
    content = client.get(path).json()['messages'][-1]
    assert content['content'].startswith('Revisé penguins.csv')
    assert fid not in content['content'] and 'Hola' not in content['content']
    assert 'penguins.csv' in content['metadata']['questions'][0]


def test_reuse_yes_allows_information_then_deterministic_continue(api):
    client, store, provider = api
    old = new(client, store)
    turn(client, old, action='instrument_no')
    attach_penguins(client, old)
    path = new(client, store)
    turn(client, path, action='reuse')
    assert turn(client, path, content='Sí').status_code == 200
    assert 'información adicional' in client.get(path).json()['messages'][-1]['content']
    assert turn(client, path, content='Continuar').status_code == 200
    assert client.get(path).json()['conversation']['current_stage'] == 'goal'
    assert not provider.contexts


def test_accepted_legacy_proposals_are_not_rewritten_or_reinterpreted(api):
    client, store, provider = api
    path = new(client, store)
    old = {'id': str(uuid4()), 'conversation_id': path.split('/')[-1], 'title': 'Plan anterior', 'objective': 'Objetivo anterior',
           'status': 'accepted', 'analysis_plan': {'schema_version': 1, 'method': 'Welch anterior sin nuevos campos'}}
    store.data['analysis_proposals'].append(copy.deepcopy(old))
    assert client.patch(path + '/proposals/' + old['id'], json={'status': 'accepted'}).status_code == 200
    assert store.data['analysis_proposals'] == [old]
    assert not provider.contexts


def test_missing_title_uses_real_goal_then_accepted_plan_without_extra_calls(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    fid = attach_penguins(client, path)
    provider.replies.append(reply(detected_goal=None, suggested_title=None,
                                  proposals=replace_file_ids(alternatives(), fid)))
    assert turn(client, path, content='No conozco el dataset, recomiéndame alternativas para analizarlo.').status_code == 200
    detail = client.get(path).json()
    assert detail['conversation']['title'] == 'Exploración estadística de los datos'
    assert detail['conversation']['stage_data']['title_provisional'] is True
    chosen = detail['proposals'][-1]
    assert client.patch(path + '/proposals/' + chosen['id'], json={'status': 'accepted'}).status_code == 200
    state = client.get(path).json()['conversation']
    assert state['title'] == chosen['title']
    assert state['stage_data']['title_provisional'] is False
    assert len(provider.contexts) == 1
    assert client.patch(path + '/proposals/' + chosen['id'], json={'status': 'accepted'}).status_code == 200
    assert client.get(path).json()['conversation'] == state


def test_fallback_and_acceptance_preserve_manual_titles(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    fid = attach_penguins(client, path)
    client.patch(path, json={'title': 'Mi título personalizado'})
    provider.replies.append(reply(detected_goal='Explorar medidas', suggested_title=None,
                                  proposals=[replace_file_ids(base_plan(), fid)]))
    assert turn(client, path, content='Quiero explorar las medidas.').status_code == 200
    detail = client.get(path).json()
    assert client.patch(path + '/proposals/' + detail['proposals'][0]['id'], json={'status': 'accepted'}).status_code == 200
    assert client.get(path).json()['conversation']['title'] == 'Mi título personalizado'


def test_titles_are_compact_and_action_labels_are_not_final_titles():
    from app.services.titles import automatic_title
    title, provisional = automatic_title({'title': 'Nueva conversación'}, 'Comprender los archivos adjuntos', 'Comparar ' + 'mediciones ' * 30)
    assert len(title) <= 80 and title.startswith('Comparar') and provisional
    assert automatic_title({'title': 'Un título útil'}, 'Otro título', 'Explorar')[0] is None


@pytest.mark.parametrize('text', [
    'Los individuos son distintos, garantizando independencia.',
    'Independencia confirmada por tener una fila por individuo.',
    'Los registros son de individuos diferentes.',
    'Independencia verificada; verificar otros supuestos después.',
])
def test_distinct_rows_do_not_confirm_independence(text):
    plan = welch_plan()
    plan['comparison']['independence'] = text
    with pytest.raises(ValueError, match='independencia|Independencia'):
        validated(plan, scope())


def test_independence_pending_does_not_block_exploration_and_evidence_is_user_only():
    from app.services.independence import user_independence_evidence
    validated(welch_plan(), scope())
    sufficient = 'Muestreo aleatorio individual, una sola medición por individuo, sin pareamiento ni conglomerados.'
    assert not user_independence_evidence([{'role': 'assistant', 'content': sufficient}])
    assert not user_independence_evidence([{'role': 'user', 'content': 'Son individuos distintos.'}])
    assert not user_independence_evidence([{'role': 'user', 'content': 'No hubo ' + sufficient}])
    evidence = user_independence_evidence([{'role': 'user', 'content': sufficient}])
    assert evidence
    assert not user_independence_evidence([{'role': 'user', 'content': 'Me equivoqué, hay mediciones repetidas.'}], evidence)
    plan = welch_plan()
    plan['comparison']['independence'] = 'Independencia informada por el usuario según muestreo y diseño, no deducida del perfil.'
    validated(plan, {**scope(), 'independence_evidence': evidence})


@pytest.mark.parametrize('correction', [
    'J(df_Welch); df_Welch = Welch-Satterthwaite.',
    'J(df_Welch), aunque n1+n2-2 se usa en la SD combinada.',
    'J(df) para corregir sesgo, grados de libertad pendientes.',
])
def test_pooled_hedges_requires_its_own_degrees_of_freedom(correction):
    plan = welch_plan()
    plan['comparison']['effect_size'].update(name='hedges_g', correction=correction)
    with pytest.raises(ValueError, match='Hedges usa'):
        validated(plan, scope())


def test_hedges_and_welch_df_are_distinguished_and_ci_is_retained():
    plan = welch_plan()
    plan['comparison']['effect_size'].update(name='hedges_g',
        correction='J(ν_H)≈1−3/(4ν_H−1), ν_H=n₁+n₂−2. Los gl Welch–Satterthwaite pertenecen solo al contraste.')
    result = validated(plan, scope())
    assert result.proposals[0].comparison.effect_size.confidence_interval


@pytest.mark.parametrize('kind', ['objective', 'method', 'component', 'unused'])
def test_objective_method_and_component_variables_must_agree(kind):
    plan = base_plan()
    if kind == 'objective': plan['objective'] = 'Analizar body_mass_g y bill_length_mm'
    elif kind == 'method': plan['method'] = 'Calcular descriptivos de bill_length_mm'
    else:
        plan = alternatives()[-1]
        if kind == 'component': plan['components'][0]['method'] = 'Resumir bill_length_mm'
        else: plan['variables'].append(variable('bill_length_mm'))
    with pytest.raises(ValueError, match='variables|variable|declarada'):
        validated(plan)


def test_incoherent_proposal_cannot_be_accepted(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    fid = attach_penguins(client, path)
    plan = replace_file_ids(base_plan(objective='Analizar body_mass_g y bill_length_mm'), fid)
    proposal_id = str(uuid4())
    store.data['analysis_proposals'].append({'id': proposal_id, 'conversation_id': path.split('/')[-1], 'status': 'proposed', 'analysis_plan': plan})
    assert client.patch(path + '/proposals/' + proposal_id, json={'status': 'accepted'}).status_code == 422
    assert store.data['analysis_proposals'][0]['status'] == 'proposed'


def test_new_objectives_must_bind_human_labels_to_canonical_columns():
    plan = base_plan(objective='Estudiar masa corporal y dimensiones del pico')
    with pytest.raises(ValueError, match='nombre exacto'):
        validated(plan, {'canonical_objectives': True})
    plan['objective'] = 'Estudiar masa corporal (body_mass_g) y dimensiones del pico (bill_length_mm)'
    with pytest.raises(ValueError, match='no está declarada'):
        validated(plan, {'canonical_objectives': True})
    plan['variables'].append(variable('bill_length_mm'))
    validated(plan, {'canonical_objectives': True})


def test_guarantee_in_assistant_prose_is_rejected_even_with_pending_plan():
    result = AssistantReply.model_validate(reply(response='Son individuos distintos, garantizando la independencia.', proposals=[welch_plan()]))
    with pytest.raises(ValueError, match='No garantizar'):
        validate_reply(result, penguins(), {'project_type': 'general'}, scope())
