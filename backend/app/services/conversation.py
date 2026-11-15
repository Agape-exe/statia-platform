from fastapi import HTTPException

from app.models.chat import AssistantReply
from app.services.gemini import build_context, validate_reply

ACTION_LABELS = {
    'reuse': 'Reutilizar archivos', 'new_files': 'Cargar archivos nuevos', 'instrument_yes': 'Sí, utilicé un instrumento',
    'instrument_no': 'No tengo instrumento', 'instruments_done': 'Continuar con los datasets',
    'files_ready': 'Comprender los archivos adjuntos', 'keep_goal': 'Continuar con la finalidad actual',
}


async def linked_files(store, conversation):
    links = await store.rows('conversation_files', {'conversation_id': conversation['id']})
    if not links:
        return []
    return await store.rows('project_files', {'project_id': conversation['project_id'], 'id': [link['file_id'] for link in links]}, order='created_at.desc')


def static_result(conversation, stage, content, *, link_ids=None):
    return {'stage': stage, 'content': content, 'message_type': 'question', 'stage_data': conversation.get('stage_data', {}),
            'link_file_ids': link_ids or [], 'proposals': [], 'metadata': {}}


async def process_turn(store, project, conversation, turn, files, provider, settings):
    stage = conversation['current_stage']
    action = turn.action
    normalized = turn.content.strip().lower().strip('.!¿?')
    if action == 'message' and stage == 'instrument':
        if normalized in ('sí', 'si', 'sí tengo', 'si tengo'):
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
        return static_result(conversation, 'understanding' if any(f['file_role'] == 'dataset' for f in selected + files) else 'upload_dataset',
                             'Los archivos quedaron asociados sin duplicarlos. ¿Necesitas añadir o actualizar información? Puedes adjuntar más archivos o solicitar su comprensión.',
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
    if action == 'keep_goal':
        if not conversation.get('stage_data', {}).get('goal_change'):
            raise HTTPException(409, 'No hay un cambio de finalidad pendiente.')
        return {**static_result(conversation, stage, 'Conservamos la finalidad actual. Escribe tu siguiente pregunta o crea otra conversación cuando lo necesites.'),
                'stage_data': {**conversation.get('stage_data', {}), 'goal_change': None}}
    messages = await store.rows('messages', {'conversation_id': conversation['id']}, order='position.desc', limit=30)
    messages.reverse()
    context = build_context(project, conversation, messages, files, turn, settings)
    # Un único intento de corrección semántica; sin bucles de herramientas.
    reply = await provider.generate(context)
    try:
        validate_reply(reply, files, project)
    except ValueError as exc:
        reply = await provider.generate(context, str(exc))
        try:
            validate_reply(reply, files, project)
        except ValueError:
            raise HTTPException(502, 'Gemini propuso variables o métodos incompatibles con los archivos. No se guardó una propuesta inválida; puedes reintentar.') from None
    return reply_result(reply, conversation)


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
    # El modelo solo sugiere; la aplicación decide las transiciones y nunca acepta planes.
    if reply.proposals:
        stage, kind = 'proposal', 'proposal'
    elif reply.questions:
        stage, kind = 'clarification', 'question'
    else:
        stage, kind = ('goal' if reply.suggested_stage == 'proposal' else reply.suggested_stage), 'dataset_summary'
    return {'stage': stage, 'content': reply.response, 'message_type': kind, 'stage_data': data,
            'goal': reply.detected_goal, 'title': reply.suggested_title, 'metadata': metadata,
            'proposals': [p.model_dump(mode='json') for p in reply.proposals]}
