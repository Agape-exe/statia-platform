from fastapi import HTTPException
import re
from pydantic import ValidationError

from app.models.chat import AssistantReply
from app.services.gemini import build_context
from app.services.conversation_text import ACTION_LABELS as ACTION_LABELS, normalize, statistical_request, humanize_reply, independent_proposal, interaction_mode, proposal_limit, technical_details_requested
from app.services.methodology import levels
from app.services.titles import automatic_title
from app.services.independence import user_independence_evidence
from app.services.planning_errors import FAILURE_DETAILS, PlanningIssue, log_issues
from app.services.planning_validation import Assessment, assess_reply, retain_valid_plans
from app.services.analysis_context import saved_results_context
from app.services.research_context import current_context
from app.services.requested_scope import requested_scope, scope_question, validate_scope_reply


async def linked_files(store, conversation):
    links = await store.rows('conversation_files', {'conversation_id': conversation['id']})
    if not links:
        return []
    return await store.rows('project_files', {'project_id': conversation['project_id'], 'id': [link['file_id'] for link in links]}, order='created_at.desc')


def static_result(conversation, stage, content, *, link_ids=None):
    return {'stage': stage, 'content': content, 'message_type': 'question', 'stage_data': conversation.get('stage_data', {}),
            'link_file_ids': link_ids or [], 'proposals': [], 'metadata': {}}


def comparison_scope(conversation, turn, files):
    """Una decisión de alcance, no un supuesto estadístico a comprobar después."""
    if turn.action != 'message':
        return conversation, None
    text = normalize(turn.content)
    data = dict(conversation.get('stage_data', {}))
    if independent_proposal(turn.content):
        data.pop('comparison_scope', None)
        data.pop('pending_comparison_scope', None)
        conversation = {**conversation, 'stage_data': data}
    pending = data.get('pending_comparison_scope')
    candidate = pending
    if not candidate and statistical_request(turn.content) and re.search(r'macho|hembra|sexos|sexo|male|female', text) and re.search(r'especie|species', text):
        for file in files:
            for column in file['metadata'].get('profile', {}).get('columns', []):
                if normalize(column['name']) in ('species', 'especie', 'especies') and column['unique'] > 1:
                    candidate = {'file_id': file['id'], 'sheet': file['metadata']['selected_sheet'], 'column': column['name'],
                                 'values': sorted(levels(column)), 'request': turn.content[:2000]}
                    break
            if candidate:
                break
    if not candidate:
        return conversation, None
    all_species = bool(re.search(r'\btodas\b|cada especie|por especie', text))
    chosen = [value for value in candidate['values'] if normalize(value) in text]
    if len(chosen) == 1 and re.search(r'\bsolo\b|unicamente|no todas|no quiero todas', text):
        all_species = False
    if all_species or len(chosen) == 1:
        data['comparison_scope'] = {k: candidate[k] for k in ('file_id', 'sheet', 'column')}
        data['comparison_scope'].update(mode='all' if all_species else 'single', values=candidate['values'] if all_species else chosen)
        data['pending_comparison_scope'] = None
        return {**conversation, 'stage_data': data}, None
    data['pending_comparison_scope'] = candidate
    state = {**conversation, 'stage_data': data}
    question = ('¿Deseas analizar una especie específica (' + ', '.join(candidate['values']) +
                ') o hacer comparaciones independientes dentro de todas las especies? Es importante porque define si habrá uno o varios contrastes.')
    result = static_result(state, 'clarification', question)
    if not conversation.get('primary_goal') and statistical_request(candidate['request']):
        result['goal'] = candidate['request']
        result['title'], provisional = automatic_title(conversation, None, result['goal'])
        result['stage_data'] = {**data, 'title_provisional': provisional}
    return state, result


async def process_turn(store, project, conversation, turn, files, provider, settings):
    from app.services.execution_preparation import bind_descriptive_scope, descriptive_request, normalized_preparation, preparation_turn, preparation_message_route, result_discussion
    preparation = normalized_preparation(conversation.get('stage_data', {}).get('execution_preparation'))
    alternative = await descriptive_request(store, conversation, turn) if turn.action == 'request_descriptive' else None
    route = preparation_message_route(turn, preparation)
    if not alternative and route == 'execution':
        return await preparation_turn(store, project, conversation, turn, settings)
    if not alternative and route == 'ambiguous':
        return static_result(conversation, conversation['current_stage'], '¿Quieres responder a la aclaración pendiente o hacer una consulta sobre tus resultados o metodología? Puedes seguir preguntando sin resolver ahora la preparación.')
    if alternative:
        conversation = {**conversation, 'stage_data': {**conversation.get('stage_data', {}), 'execution_preparation': preparation}}
        turn = turn.model_copy(update={'action': 'message', 'content': 'Quiero una nueva propuesta exclusivamente descriptiva como alternativa al análisis pendiente, con los mismos archivos, hojas, columnas y alcance aceptado. No cambies ni ejecutes el plan original.'})
    stage = conversation['current_stage']
    action = turn.action
    normalized = normalize(turn.content)
    data = dict(conversation.get('stage_data', {}))
    if data.get('awaiting_reuse_update') and action == 'message':
        no_update = normalized in ('no', 'continuar', 'no gracias', 'no necesito agregar nada', 'no necesito añadir nada', 'no necesito agregar informacion')
        yes_update = normalized in ('si', 'si necesito', 'si quiero agregar informacion')
        data['awaiting_reuse_update'] = False
        conversation = {**conversation, 'stage_data': data}
        names = ', '.join(file.get('original_name', 'archivo de datos') for file in files)
        if no_update:
            if not any(file['file_role'] == 'dataset' for file in files):
                return static_result(conversation, 'upload_dataset', f'Utilizaremos nuevamente {names}. Adjunta ahora los datasets que deseas analizar.')
            return static_result(conversation, 'goal', f'Perfecto, utilizaremos nuevamente {names}. ¿Qué análisis estadístico deseas realizar con estos datos? Si no lo sabes, puedo recomendarte alternativas.')
        if yes_update:
            conversation['stage_data']['awaiting_reuse_update'] = True
            return static_result(conversation, 'understanding', f'Utilizaremos {names}. Puedes escribir la información adicional o adjuntar archivos; después indícanos qué deseas analizar.')
    elif data.get('awaiting_reuse_update') and action in ('files_ready', 'keep_goal'):
        conversation = {**conversation, 'stage_data': {**data, 'awaiting_reuse_update': False}}
    if action == 'message' and stage == 'instrument':
        if normalized in ('si', 'si tengo'):
            action = 'instrument_yes'
        elif normalized in ('no', 'no tengo', 'no tengo instrumento'):
            action = 'instrument_no'
    if action in ('instrument_yes', 'instrument_no'):
        if stage != 'instrument':
            raise HTTPException(409, 'La pregunta sobre instrumentos ya fue respondida. Recarga la conversación.')
        return static_result(conversation, 'upload_instrument' if action == 'instrument_yes' else 'upload_dataset',
                             'Adjunta uno o varios instrumentos PDF o DOCX. Word antiguo .doc requiere conversión a DOCX o PDF. Después podrás continuar con los datasets.' if action == 'instrument_yes'
                             else 'Adjunta uno o varios datasets CSV, XLSX o JSON. No necesitas un instrumento.')
    if action == 'new_files':
        if stage != 'reuse':
            raise HTTPException(409, 'La selección de archivos inicial ya fue resuelta.')
        return static_result(conversation, 'instrument', '¿Tus datos están relacionados con algún instrumento de recolección de información?')
    if action == 'reuse':
        requested = [str(fid) for fid in turn.file_ids] or conversation.get('stage_data', {}).get('reuse_file_ids', [])
        if not requested:
            raise HTTPException(422, 'Selecciona los archivos que deseas reutilizar.')
        existing = await store.rows('project_files', {'project_id': project['id'], 'id': requested})
        selected = [file for file in existing if file['id'] in requested]
        if len({f['id'] for f in selected}) != len(set(requested)):
            raise HTTPException(404, 'Uno de los archivos no pertenece a este proyecto o ya no existe.')
        if len({f['id'] for f in selected + files}) > settings.max_conversation_files:
            raise HTTPException(422, 'Se alcanzó el límite de archivos de la conversación.')
        state = {**conversation, 'stage_data': {**conversation.get('stage_data', {}), 'awaiting_reuse_update': True}}
        names = ', '.join(f.get('original_name', 'archivo de datos') for f in selected)
        return static_result(state, 'understanding' if any(f['file_role'] == 'dataset' for f in selected + files) else 'upload_dataset',
                             f'Utilizaremos nuevamente {names}, sin duplicar los archivos. ¿Necesitas añadir o actualizar información?',
                             link_ids=requested)
    if action == 'instruments_done':
        if stage != 'upload_instrument':
            raise HTTPException(409, 'Esta conversación no está esperando instrumentos.')
        return static_result(conversation, 'upload_dataset', 'Adjunta ahora uno o varios datasets. Puedes completar los instrumentos más adelante si lo necesitas.')
    if stage in ('instrument', 'reuse'):
        raise HTTPException(422, 'Responde primero la pregunta inicial con las opciones disponibles.')
    datasets = [f for f in files if f['file_role'] == 'dataset']
    from app.services.reply_contract import NON_PLANNING, normalize_reply
    mode = interaction_mode(turn)
    explicit_proposal = action == 'message' and proposal_limit(turn.content) is not None
    if action == 'message' and mode in ('planning', 'methodology') and any(f['file_role'] == 'instrument' for f in files) and not statistical_request(turn.content):
        from app.services.instrument_context import codes, search_query
        asks_for_items = re.search(r'^(?:que|cual(?:es)?|identifica|busca|recupera|muestra|lista|indicame) (?:son )?(?:las? |los? )?(?:preguntas|items|enunciados)\b', normalized)
        if asks_for_items or (codes(search_query(turn.content)) and re.search(r'pregunta|codigo|opciones|que dice|que significa|busca|recupera', normalized)):
            mode = 'document'
    if stage == 'upload_instrument' and action == 'message' and mode not in ('document', 'methodology') and not datasets:
        return static_result(conversation, stage, 'Adjunta tus instrumentos o elige «Continuar con los datasets» para seguir.')
    if not datasets and mode not in ('document', 'methodology'):
        raise HTTPException(422, 'Adjunta al menos un dataset antes de solicitar su comprensión.')
    if any(not f['metadata'].get('profile') and not f['metadata'].get('sheet_profiles') for f in datasets):
        raise HTTPException(422, 'Elige una hoja para cada libro XLSX antes de continuar.')
    discusses_results = not explicit_proposal and result_discussion(turn.content)
    conversation, scope_result = (conversation, None) if alternative or discusses_results or mode in NON_PLANNING else comparison_scope(conversation, turn, files)
    if scope_result:
        return scope_result
    if action == 'keep_goal':
        if not conversation.get('stage_data', {}).get('goal_change'):
            raise HTTPException(409, 'No hay un cambio de finalidad pendiente.')
        return {**static_result(conversation, stage, 'Conservamos la finalidad actual. Escribe tu siguiente pregunta o crea otra conversación cuando lo necesites.'),
                'stage_data': {**conversation.get('stage_data', {}), 'goal_change': None}}
    messages = await store.rows('messages', {'conversation_id': conversation['id']}, order='position.desc', limit=30)
    messages.reverse()
    # Reconstruir procedencia desde solicitudes ya persistidas, sin cambiar el esquema SQL.
    request_ids = [m.get('metadata', {}).get('request_id') for m in messages if m.get('metadata', {}).get('request_id')]
    if request_ids:
        requests = await store.rows('chat_requests', {'conversation_id': conversation['id'], 'request_id': request_ids})
        actions = {r['request_id']: r['payload'].get('action', 'message') for r in requests}
        messages = [{**m, 'metadata': {**m.get('metadata', {}), 'turn_action': actions[m['metadata']['request_id']]}}
                    if m.get('metadata', {}).get('request_id') in actions else m for m in messages]
    data = dict(conversation.get('stage_data', {}))
    data['independence_evidence'] = user_independence_evidence(messages, data.get('independence_evidence'))
    from app.services.variable_types import bind_confirmations, capture_confirmations
    try:
        confirmations = capture_confirmations(turn.content if turn.action == 'message' else '', files, data.get('confirmed_variable_types', []))
        if confirmations or 'confirmed_variable_types' in data:
            data['confirmed_variable_types'] = confirmations
    except ValueError as exc:
        return static_result(conversation, 'clarification', str(exc))
    analysis_results = await saved_results_context(store, conversation, turn.content)
    discussion = not explicit_proposal and mode not in ('document', 'understanding') and bool(analysis_results) and turn.action == 'message' and (discusses_results or not statistical_request(turn.content))
    plans_allowed = not (alternative or discussion or mode in NON_PLANNING or discusses_results)
    scope = requested_scope(conversation, messages, turn, files) if plans_allowed else None
    if scope:
        data['requested_scope'] = scope
    elif plans_allowed and independent_proposal(turn.content):
        data.pop('requested_scope', None)
    conversation = {**conversation, 'stage_data': data}
    if scope:
        import logging
        logging.getLogger(__name__).info(
            'Planning scope version=%s products=%s excluded=%s constraints=%s unresolved=%s route=%s',
            scope['recognizer_version'], ','.join(scope['products']), ','.join(scope.get('excluded_products', [])),
            ','.join(scope.get('constraints', [])), scope['unresolved'],
            'scope_clarification' if scope['unresolved'] else 'provider')
    if scope and scope['unresolved']:
        result = reply_result(scope_question(scope), conversation, files=files, scope=scope)
        result['metadata']['interaction_mode'] = mode
        return result
    research = await current_context(store, project)
    context = build_context(project, conversation, messages, files, turn, settings, analysis_results, research)
    context['interaction_mode'] = mode
    if mode in NON_PLANNING:
        context['recommendations_requested'] = False
    context['technical_details'] = technical_details_requested(turn.content)
    if scope:
        # Compromisos del usuario, separados del texto generado por el proveedor.
        context['requested_scope'] = scope
        import json
        if len(json.dumps(context, ensure_ascii=False)) > settings.gemini_context_chars:
            raise HTTPException(413, 'El contexto con los productos solicitados supera el límite del proveedor. El alcance se conserva; reduce el contexto antes de reintentar.')
    if discussion:
        from app.services.analysis_context import safe_text
        context['files'] = [{k: f[k] for k in ('file_id', 'file_name', 'role', 'sheets', 'selected_sheet') if k in f} | {'columns': [{k: c[k] for k in ('name', 'physical_type', 'statistical_type') if k in c} for c in f.get('columns', [])]} for f in context['files']]
        context['result_discussion'] = True
        context['recommendations_requested'] = False
        context['preparation_pending'] = {'proposal_id': preparation.get('proposal_id'), 'status': preparation.get('result', {}).get('status'), 'questions': [{'prompt': safe_text(q['prompt'])[:300], 'status': q.get('status'), 'limitation': safe_text(q.get('limitation', ''))[:450]} for q in preparation.get('result', {}).get('clarifications', [])[:8]]}
        import json
        if len(json.dumps(context, ensure_ascii=False)) > settings.gemini_context_chars:
            raise HTTPException(413, 'El contexto de resultados supera el límite configurado. Identifica una ejecución o una tabla concreta; tus resultados y aclaraciones se conservan.')
    if alternative:
        context['execution_alternative'] = alternative
        context['recommendations_requested'] = False
        import json
        if len(json.dumps(context, ensure_ascii=False)) > settings.gemini_context_chars:
            raise HTTPException(413, 'El contexto de la alternativa supera el límite del proveedor. El análisis original y tus respuestas se conservan.')
    if mode == 'document' and not any(f.get('instrument', {}).get('fragments_shared') for f in context['files']):
        if not any(f['file_role'] == 'instrument' for f in files):
            content = 'No hay instrumentos asociados a esta conversación. Adjunta un PDF o DOCX para consultar su contenido.'
        elif not turn.share_instrument_text:
            content = 'El instrumento está asociado, pero su texto no está autorizado para el proveedor. Elige «Permitir consultar fragmentos» en la autorización del instrumento y vuelve a enviar tu consulta. No he consultado su contenido.'
        elif not any(f.get('instrument', {}).get('fragments_available', 0) for f in context['files']):
            content = 'No se recuperó texto de los instrumentos asociados. Revisa el original y las advertencias de extracción. Puede contener imágenes o una estructura no accesible; no hay OCR disponible. No se envió contenido documental al proveedor.'
        else:
            content = 'No encontré la información solicitada en los fragmentos recuperables de los instrumentos asociados. Sí hay texto disponible, pero esta búsqueda no encontró coincidencias verificables. Prueba con el código, una frase del original o el encabezado de la sección. Revisa las advertencias si la extracción es parcial; esto no demuestra que la información no exista en el original. No se envió esta consulta al proveedor.'
        result = static_result(conversation, stage, content)
        result['metadata'] = {'interaction_mode': mode, 'research_context_revision': research['revision'] if research else None}
        result['metadata']['instrument_retrieval'] = [
            {'file_id': f['file_id'], **{key: value for key, value in f['instrument'].items() if key != 'fragments_shared'}}
            for f in context['files'] if 'instrument' in f]
        return result
    import json
    context_limit = settings.gemini_context_chars - min(4000, settings.gemini_context_chars // 5)
    while len(json.dumps(context, ensure_ascii=False)) > context_limit and len(context['history']) > 1:
        context['history'].pop(0)
    if len(json.dumps(context, ensure_ascii=False)) > context_limit:
        raise HTTPException(413, 'El contexto indispensable supera el presupuesto del proveedor y su corrección acotada. Reduce archivos o identifica una consulta más concreta; se conserva tu solicitud.')
    async def generate(correction=None):
        try:
            return await provider.generate(context, correction)
        except HTTPException as exc:
            if alternative:
                raise HTTPException(exc.status_code, 'No se pudo generar la propuesta descriptiva en este momento. El análisis original y tus respuestas se conservan. ' + str(exc.detail), headers=exc.headers) from None
            raise
    # Dos generaciones como máximo; cada alternativa se evalúa por separado.
    reply = await generate()
    validation_history = []
    partial = False
    for attempt in range(2):
        invalid_positions = reply._invalid_plan_positions
        try:
            reply = normalize_reply(reply, mode)
            if alternative:
                reply = bind_descriptive_scope(reply, alternative)
            if discussion and (reply.proposals or reply.goal_change):
                raise ValueError('Esta consulta interpreta resultados guardados o revisa metodología del mismo análisis. Responde sin propuestas nuevas ni cambio de finalidad y sin exigir resolver aclaraciones pendientes.')
            if scope and 'posthoc' in scope.get('excluded_products', []):
                for proposed in reply.proposals:
                    steps = proposed.components if proposed.procedure == 'integral' else [proposed]
                    if any(step.procedure == 'group_comparison' for step in steps) and 'Sin comparaciones post hoc' not in proposed.expected_outputs:
                        proposed.expected_outputs.append('Sin comparaciones post hoc')
            reply = bind_confirmations(reply, data.get('confirmed_variable_types', []), files)
            from app.services.interpretation_guards import result_ids, validate_explanation
            from app.services.instrument_context import uses_thematic_evidence, validate_document_claims
            validate_document_claims(reply.response, context)
            if uses_thematic_evidence(context):
                reply = reply.model_copy(update={'questions': [], 'warnings': [], 'context_summary': None})
            validate_explanation(reply.response, context)
            reply = humanize_reply(reply, files, result_ids(context) if context['technical_details'] else ())
            assessment = assess_reply(reply, files, project, context, invalid_positions)
        except (ValidationError, ValueError) as exc:
            # Conservar la corrección acotada si la normalización deja contenido inválido.
            assessment = Assessment([], [PlanningIssue.from_error(exc) if isinstance(exc, ValueError) and not isinstance(exc, ValidationError) else PlanningIssue('internal_contract',
                                    'La respuesta debe conservar contenido sustantivo válido después de retirar el saludo.')], False)
        if not assessment.issues:
            break
        log_issues(assessment.issues, attempt + 1)
        validation_history.append({'attempt': attempt + 1, 'issues': [issue.safe_metadata() for issue in assessment.issues]})
        if attempt:
            retained = retain_valid_plans(reply, assessment, files, project, context)
            if retained:
                reply, partial = retained, True
                break
            if scope and not scope.get('constraints') and any(issue.category in ('requested_scope', 'output_scope', 'output_capability') and
                             (not explicit_proposal or issue.plan_index is not None) for issue in assessment.issues):
                reply = scope_question(scope, provider_failed=True)
                break
            type_problems = list(dict.fromkeys(issue.message for issue in assessment.issues if issue.category == 'variable_type'))
            if mode in NON_PLANNING:
                detail = 'El proveedor no pudo responder con evidencia suficiente. No se guardó la respuesta; puedes reintentar.'
            elif type_problems:
                detail = 'El plan no es ejecutable con el perfil actual. ' + ' '.join(type_problems)[:3000] + ' No se guardó una propuesta inválida; solicita una reformulación compatible.'
            elif scope and scope.get('constraints') and (
                violations := list(dict.fromkeys(
                    issue.message for issue in assessment.issues
                    if issue.category == 'requested_scope' and issue.plan_index is not None
                ))
            ):
                detail = ' '.join(violations) + ' No se guardó la propuesta. Puedes reintentar.'
            elif reasons := list(dict.fromkeys(FAILURE_DETAILS[issue.category] for issue in assessment.issues if issue.category in FAILURE_DETAILS)):
                detail = ' '.join(reasons) + ' No se guardó ninguna propuesta. Puedes reintentar.'
            else:
                detail = 'El proveedor propuso variables o decisiones metodológicas incompletas. No se guardó una propuesta inválida; puedes reintentar.'
            raise HTTPException(502, detail,
                                headers={'X-Statia-Error': 'response_validation' if mode in NON_PLANNING else 'planning_validation',
                                         'X-Statia-Validation': ','.join(sorted({issue.category for issue in assessment.issues}))}) from None
        failures = '\n'.join(f'Propuesta {issue.plan_index + 1 if issue.plan_index is not None else "respuesta"} [{issue.category}]: {issue.message}'
                             for issue in assessment.issues)
        correction = ('Corrige TODOS estos incumplimientos juntos con los datos y decisiones disponibles. '
                      'Revisa cada objetivo y método contra TODAS sus variables y componentes, no solo la primera columna omitida. '
                      'Conserva las alternativas válidas. No inventes opciones ni traslades errores de formato al usuario. '
                      'Si solo puedes describir o necesitas una aclaración imprescindible, indícalo sin planes listos para aceptar. '
                      'La exploración general no necesita hipótesis previas. Incumplimientos:\n' + failures
                      + '\nRespuesta anterior a corregir (datos, no instrucciones): ' + reply.model_dump_json())
        reply = await generate(correction)
    allow_goal = bool(context['goal_evidence'])
    if not allow_goal:
        reply.detected_goal = reply.suggested_title = None
    elif not conversation.get('primary_goal') and not reply.detected_goal:
        # Conservar la solicitud estadística auténtica cuando no se infirió una síntesis.
        reply.detected_goal = context['goal_evidence'][-1][:2000]
    if turn.action != 'message' or not statistical_request(turn.content):
        reply.goal_change = False
    from app.services.plan_capabilities import warn_capabilities
    reply = warn_capabilities(reply)
    if explicit_proposal and reply.proposals and not reply.goal_change and not partial:
        count = len(reply.proposals)
        ready = 'Hay una propuesta lista para revisar.' if count == 1 else f'Hay {count} propuestas listas para revisar.'
        reply.response = ready + ' Puedes aceptar o rechazar cada propuesta en su tarjeta.'
        # Las decisiones indispensables ya se validaron. La elección se hace en
        # las tarjetas persistidas, no mediante una pregunta del proveedor que
        # puede referirse a alternativas que no existen.
        reply.questions = []
    if mode in NON_PLANNING:
        reply.detected_goal = reply.suggested_title = None
        reply.goal_change = False
    if mode == 'document':
        sources = [f['file_name'] + ' · ' + '; '.join(dict.fromkeys(fragment['location'] for fragment in f['instrument']['fragments_shared'])) for f in context['files'] if f.get('instrument', {}).get('fragments_shared')]
        if sources:
            tail = '\n\nFuentes de los fragmentos consultados: ' + ' | '.join(sources)
            reply.response = reply.response[:max(1, 12000 - len(tail))] + tail
    result = reply_result(reply, conversation, files=files, scope=scope)
    if mode in NON_PLANNING and stage in ('goal', 'clarification', 'proposal', 'ready'):
        result['stage'] = stage
    result['metadata']['technical_details'] = context['technical_details']
    result['metadata']['interaction_mode'] = mode
    result['metadata']['instrument_retrieval'] = [
        {'file_id': f['file_id'], **{key: value for key, value in f['instrument'].items() if key != 'fragments_shared'},
         'locations_shared': [fragment['location'] for fragment in f['instrument']['fragments_shared']]}
        for f in context['files'] if 'instrument' in f]
    if research:
        result['metadata']['research_context_revision'] = research['revision']
    if discussion:
        result['stage'] = conversation['current_stage']
        result['goal'] = result['title'] = None
        result['stage_data'] = dict(conversation.get('stage_data', {}))
    if alternative:
        result['goal'] = result['title'] = None
        result['metadata']['execution_alternative_source'] = alternative['source_proposal_id']
    if analysis_results and not reply.proposals and not reply.goal_change:
        result['stage'] = conversation['current_stage']
        result['goal'] = None
        result['title'] = None
    if validation_history:
        result['metadata']['planning_validation'] = {'partial': partial, 'attempts': validation_history}
    return result


def reply_result(reply: AssistantReply, conversation, *, files=None, scope=...):
    scope = conversation.get('stage_data', {}).get('requested_scope') if scope is ... else scope
    validate_scope_reply(reply, scope, files)
    data = {**conversation.get('stage_data', {})}
    if reply.context_summary:
        data['context_summary'] = reply.context_summary
    metadata = reply.model_dump(mode='json')
    if reply.goal_change and conversation.get('primary_goal'):
        data['goal_change'] = {'goal': reply.detected_goal, 'reason': reply.goal_change_reason, 'title': reply.suggested_title}
        return {'stage': conversation['current_stage'], 'content': reply.response, 'message_type': 'confirmation',
                'stage_data': data, 'metadata': metadata, 'proposals': []}
    data['goal_change'] = None
    title, provisional = automatic_title(conversation, reply.suggested_title, conversation.get('primary_goal') or reply.detected_goal)
    data['title_provisional'] = provisional
    # El modelo solo sugiere; la aplicación decide las transiciones y nunca acepta planes.
    if reply.proposals:
        metadata['requested_scope'] = scope
        data['canonical_objectives'] = True
        stage, kind = 'proposal', 'proposal'
    elif reply.questions:
        stage, kind = 'clarification', 'question'
    else:
        stage, kind = ('goal' if reply.suggested_stage == 'proposal' else reply.suggested_stage), 'dataset_summary'
    return {'stage': stage, 'content': reply.response, 'message_type': kind, 'stage_data': data,
            'goal': reply.detected_goal, 'title': title, 'metadata': metadata,
            'proposals': [p.model_dump(mode='json') for p in reply.proposals]}
