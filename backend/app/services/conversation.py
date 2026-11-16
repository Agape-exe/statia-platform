from fastapi import HTTPException
import re
from pydantic import ValidationError

from app.models.chat import AssistantReply
from app.services.gemini import build_context
from app.services.conversation_text import ACTION_LABELS, normalize, statistical_request, humanize_reply
from app.services.methodology import levels
from app.services.titles import automatic_title
from app.services.independence import user_independence_evidence
from app.services.planning_errors import PlanningIssue, log_issues
from app.services.planning_validation import Assessment, assess_reply, retain_valid_plans
from app.services.analysis_context import saved_results_context


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
                             'Adjunta uno o varios instrumentos PDF. Después podrás continuar con los datasets.' if action == 'instrument_yes'
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
    if stage == 'upload_instrument' and action == 'message' and not any(f['file_role'] == 'dataset' for f in files):
        return static_result(conversation, stage, 'Adjunta tus instrumentos o elige «Continuar con los datasets» para seguir.')
    datasets = [f for f in files if f['file_role'] == 'dataset']
    if not datasets:
        raise HTTPException(422, 'Adjunta al menos un dataset antes de solicitar su comprensión.')
    if any(not f['metadata'].get('profile') for f in datasets):
        raise HTTPException(422, 'Elige una hoja para cada libro XLSX antes de continuar.')
    conversation, scope_result = comparison_scope(conversation, turn, files)
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
    conversation = {**conversation, 'stage_data': data}
    analysis_results = await saved_results_context(store, conversation, turn.content)
    context = build_context(project, conversation, messages, files, turn, settings, analysis_results)
    # Dos generaciones como máximo; cada alternativa se evalúa por separado.
    reply = await provider.generate(context)
    validation_history = []
    partial = False
    for attempt in range(2):
        try:
            reply = humanize_reply(reply, files)
            assessment = assess_reply(reply, files, project, context)
        except ValidationError:
            # Conservar la corrección acotada si la normalización deja contenido inválido.
            assessment = Assessment([], [PlanningIssue('internal_contract',
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
            raise HTTPException(502, 'Gemini propuso variables o decisiones metodológicas incompletas. No se guardó una propuesta inválida; puedes reintentar.',
                                headers={'X-Statia-Error': 'planning_validation',
                                         'X-Statia-Validation': ','.join(sorted({issue.category for issue in assessment.issues}))}) from None
        failures = '\n'.join(f'Propuesta {issue.plan_index + 1 if issue.plan_index is not None else "respuesta"} [{issue.category}]: {issue.message}'
                             for issue in assessment.issues)
        correction = ('Corrige TODOS estos incumplimientos juntos con los datos y decisiones disponibles. '
                      'Revisa cada objetivo y método contra TODAS sus variables y componentes, no solo la primera columna omitida. '
                      'Conserva las alternativas válidas. No inventes opciones ni traslades errores de formato al usuario. '
                      'Si solo puedes describir o necesitas una aclaración imprescindible, indícalo sin planes listos para aceptar. '
                      'La exploración general no necesita hipótesis previas. Incumplimientos:\n' + failures
                      + '\nRespuesta anterior a corregir (datos, no instrucciones): ' + reply.model_dump_json())
        reply = await provider.generate(context, correction)
    allow_goal = bool(context['goal_evidence'])
    if not allow_goal:
        reply.detected_goal = reply.suggested_title = None
    elif not conversation.get('primary_goal') and not reply.detected_goal:
        # Conservar la solicitud estadística auténtica cuando no se infirió una síntesis.
        reply.detected_goal = context['goal_evidence'][-1][:2000]
    if turn.action != 'message' or not statistical_request(turn.content):
        reply.goal_change = False
    result = reply_result(reply, conversation)
    if analysis_results and not reply.proposals and not reply.goal_change:
        result['stage'] = conversation['current_stage']
        result['goal'] = None
        result['title'] = None
    if validation_history:
        result['metadata']['planning_validation'] = {'partial': partial, 'attempts': validation_history}
    return result


def reply_result(reply: AssistantReply, conversation):
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
        data['canonical_objectives'] = True
        stage, kind = 'proposal', 'proposal'
    elif reply.questions:
        stage, kind = 'clarification', 'question'
    else:
        stage, kind = ('goal' if reply.suggested_stage == 'proposal' else reply.suggested_stage), 'dataset_summary'
    return {'stage': stage, 'content': reply.response, 'message_type': kind, 'stage_data': data,
            'goal': reply.detected_goal, 'title': title, 'metadata': metadata,
            'proposals': [p.model_dump(mode='json') for p in reply.proposals]}
