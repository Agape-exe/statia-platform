import hashlib
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import ValidationError

from app.core.auth import CurrentUser
from app.models.chat import AssistantReply, ConversationCreate, Decision, FileRows, Plan, ProviderChange, Rename, Turn
from app.services.providers import catalog, check_available, require_rollback_safety, session_for
from app.services.plan_capabilities import descriptive_warnings
from app.services.gemini import validate_reply
from app.services.conversation import ACTION_LABELS, linked_files, process_turn
from app.services.profiling import MIMES, inspect_file, safe_name
from app.services.execution_preparation import EXECUTION_ACTIONS, normalized_preparation

router = APIRouter(prefix='/projects/{project_id}', tags=['Asistente'])


async def project_for(identity, project_id):
    return await identity.store.one('projects', {'id': str(project_id), 'user_id': identity.user_id})


async def conversation_for(identity, project_id, conversation_id):
    await project_for(identity, project_id)
    conversation = await identity.store.one('conversations', {'id': str(conversation_id), 'project_id': str(project_id)})
    if conversation.get('active_request_id') and conversation.get('active_since'):
        started = datetime.fromisoformat(conversation['active_since'].replace('Z', '+00:00'))
        if started < datetime.now(timezone.utc) - timedelta(seconds=180):
            await identity.store.rpc('fail_chat_turn', {'p_conversation': str(conversation_id), 'p_request': conversation['active_request_id']})
            conversation = await identity.store.one('conversations', {'id': str(conversation_id), 'project_id': str(project_id)})
    return conversation


@router.get('/conversations', summary='Listar conversaciones del proyecto')
async def list_conversations(project_id: UUID, user: CurrentUser):
    await project_for(user, project_id)
    return await user.store.rows('conversations', {'project_id': str(project_id)}, order='updated_at.desc')


@router.post('/conversations', status_code=201, summary='Crear conversación con bienvenida y etapa inicial')
async def create_conversation(project_id: UUID, body: ConversationCreate, user: CurrentUser, request: Request):
    await project_for(user, project_id)
    if body.source_conversation_id:
        source = await conversation_for(user, project_id, body.source_conversation_id)
        if not source.get('stage_data', {}).get('goal_change'):
            raise HTTPException(409, 'No hay una nueva finalidad pendiente en la conversación de origen.')
    if body.provider != 'gemini':
        check_available(body.provider, request.app.state)
        await require_rollback_safety(user.store, body.provider)
    cid = await user.store.rpc('create_provider_conversation', {'p_project': str(project_id),
        'p_source': str(body.source_conversation_id) if body.source_conversation_id else None, 'p_provider': body.provider})
    return await user.store.one('conversations', {'id': cid})


@router.get('/assistant-providers', summary='Informar los destinatarios de datos y su disponibilidad')
async def assistant_providers(project_id: UUID, user: CurrentUser, request: Request):
    await project_for(user, project_id)
    return catalog(request.app.state)


@router.patch('/conversations/{conversation_id}/provider', summary='Cambiar explícitamente el destinatario de próximos turnos')
async def change_provider(project_id: UUID, conversation_id: UUID, body: ProviderChange, user: CurrentUser, request: Request):
    await conversation_for(user, project_id, conversation_id)
    check_available(body.provider, request.app.state)
    await require_rollback_safety(user.store, body.provider)
    await user.store.rpc('select_conversation_provider', {'p_conversation': str(conversation_id),
        'p_provider': body.provider, 'p_expected': body.expected_provider})
    return await user.store.one('conversations', {'id': str(conversation_id)})


@router.get('/conversations/{conversation_id}', summary='Recuperar conversación, mensajes, archivos y propuestas')
async def get_conversation(project_id: UUID, conversation_id: UUID, user: CurrentUser):
    conversation = await conversation_for(user, project_id, conversation_id)
    if conversation.get('stage_data', {}).get('execution_preparation'):
        conversation = {**conversation, 'stage_data': {**conversation['stage_data'], 'execution_preparation': normalized_preparation(conversation['stage_data']['execution_preparation'])}}
    messages = await user.store.rows('messages', {'conversation_id': str(conversation_id)}, order='position.desc', limit=100)
    messages.reverse()
    await attach_run_events(user.store, conversation_id, messages)
    preparation_run = None
    request_id = (conversation.get('stage_data', {}).get('execution_preparation') or {}).get('result', {}).get('request_id')
    if request_id:
        runs = await user.store.rows('analysis_runs', {'conversation_id': str(conversation_id), 'request_id': request_id}, select='id,request_id,status')
        preparation_run = next((r for r in runs if r['status'] in ('completed', 'partial') or r.get('result') is not None), None)
        if preparation_run:
            preparation_run = {k: preparation_run[k] for k in ('id', 'request_id', 'status')}
    proposals = await user.store.rows('analysis_proposals', {'conversation_id': str(conversation_id)}, order='created_at.asc')
    latest = await user.store.rows('analysis_runs', {'conversation_id': str(conversation_id), 'project_id': str(project_id)}, order='created_at.desc', limit=1, select='id,proposal_id,status')
    latest_run = {k: latest[0][k] for k in ('id', 'proposal_id', 'status')} if latest else None
    turns = await user.store.rows('chat_requests', {'conversation_id': str(conversation_id)}, order='created_at.desc', limit=1)
    retry = None
    if turns and turns[0]['status'] == 'failed':
        retry = {key: value for key, value in turns[0]['payload'].items() if key != 'display'}
        retry['request_id'] = turns[0]['request_id']
    return {'conversation': conversation, 'messages': messages, 'files': await linked_files(user.store, conversation), 'proposals': proposals,
            'retry_turn': retry, 'has_more_messages': len(messages) == 100, 'preparation_run': preparation_run, 'latest_analysis_run': latest_run}


@router.get('/conversations/{conversation_id}/messages', summary='Recuperar historial anterior por posición, sin perder mensajes antiguos')
async def earlier_messages(project_id: UUID, conversation_id: UUID, user: CurrentUser,
                           before: Annotated[int, Query(gt=0)]):
    await conversation_for(user, project_id, conversation_id)
    messages = await user.store.rows('messages', {'conversation_id': str(conversation_id), 'position': ('lt', before)}, order='position.desc', limit=100)
    messages.reverse()
    await attach_run_events(user.store, conversation_id, messages)
    return {'messages': messages, 'has_more_messages': len(messages) == 100}


async def attach_run_events(store, conversation_id, messages):
    ids = [m.get('metadata', {}).get('analysis_run_id') for m in messages if m.get('metadata', {}).get('analysis_run_id')]
    if not ids:
        return
    runs = await store.rows('analysis_runs', {'conversation_id': str(conversation_id), 'id': ids}, select='id,proposal_id,request_id,status')
    by_id = {r['id']: r for r in runs}
    for message in messages:
        run = by_id.get(message.get('metadata', {}).get('analysis_run_id'))
        if run:
            message['metadata'] = {**message['metadata'], 'proposal_id': run['proposal_id'], 'execution_request_id': run['request_id'], 'execution_status': run['status']}


@router.patch('/conversations/{conversation_id}', summary='Renombrar sin sobrescritura automática posterior')
async def rename_conversation(project_id: UUID, conversation_id: UUID, body: Rename, user: CurrentUser):
    await conversation_for(user, project_id, conversation_id)
    return (await user.store.update('conversations', {'id': str(conversation_id)}, {'title': body.title, 'title_manual': True}))[0]


@router.delete('/conversations/{conversation_id}', status_code=204, summary='Eliminar conversación conservando archivos reutilizables del proyecto')
async def delete_conversation(project_id: UUID, conversation_id: UUID, user: CurrentUser):
    conversation = await conversation_for(user, project_id, conversation_id)
    if conversation.get('active_request_id'):
        raise HTTPException(409, 'Espera a que termine el turno antes de eliminar la conversación.')
    await user.store.delete('conversations', {'id': str(conversation_id)})


@router.post('/conversations/{conversation_id}/turns', summary='Persistir y procesar un turno idempotente o una acción del flujo')
async def send_turn(project_id: UUID, conversation_id: UUID, body: Turn, user: CurrentUser, request: Request):
    conversation = await conversation_for(user, project_id, conversation_id)
    if body.action == 'message' and not body.content:
        raise HTTPException(422, 'Escribe un mensaje.')
    payload = body.model_dump(mode='json', exclude={'request_id'}, exclude_none=True)
    execution_labels = EXECUTION_ACTIONS
    payload['display'] = body.content or execution_labels.get(body.action) or ACTION_LABELS[body.action]
    params = {'p_conversation': str(conversation_id), 'p_request': str(body.request_id)}
    selected = conversation.get('assistant_provider', 'gemini')
    await require_rollback_safety(user.store, selected)
    provider = session_for(selected, request.app.state)
    started = await user.store.rpc('begin_provider_chat_turn', {**params, 'p_payload': payload,
        'p_provider': selected, 'p_model': provider.trace['model']})
    if started == 'completed':
        return {'status': 'completed', 'replayed': True}
    if started == 'provider_changed':
        raise HTTPException(409, 'El proveedor cambió o este reintento pertenece a otra configuración. Recarga y envía una nueva solicitud explícita.')
    if started in ('busy', 'mismatch'):
        raise HTTPException(409, 'Ya hay una respuesta en curso. Espera y recarga.' if started == 'busy' else 'La clave de reintento pertenece a otro mensaje.')
    try:
        conversation = await conversation_for(user, project_id, conversation_id)
        files = await linked_files(user.store, conversation)
        project = await project_for(user, project_id)
        # Tiempo total menor que la concesión durable de 180 segundos.
        async with asyncio.timeout(150):
            preparation = normalized_preparation(conversation.get('stage_data', {}).get('execution_preparation'))
            from app.services.execution_preparation import preparation_message_route
            preparing = preparation_message_route(body, preparation) == 'execution' and (body.action in ('prepare_execution', 'clarify_execution', 'review_execution') or bool(preparation.get('result', {}).get('questions')))
            if preparing:
                if request.app.state.analysis_lock.locked():
                    raise HTTPException(409, 'El motor está ocupado. Reintenta la misma solicitud en un momento.')
                async with request.app.state.analysis_lock:
                    result = await process_turn(user.store, project, conversation, body, files, provider, request.app.state.settings)
            else:
                result = await process_turn(user.store, project, conversation, body, files, provider, request.app.state.settings)
        result.setdefault('metadata', {})['selected_provider'] = selected
        result['metadata']['generation'] = provider.trace if provider.calls else {'source': 'deterministic'}
        await user.store.rpc('finish_chat_turn', {**params, 'p_result': result})
    except BaseException as exc:
        try:
            await asyncio.shield(user.store.rpc('fail_chat_turn', params))
        except Exception:
            logging.getLogger(__name__).warning('No se pudo liberar el turno; expirará su concesión.')
        if isinstance(exc, TimeoutError):
            raise HTTPException(504, 'La consulta tardó demasiado. Tu mensaje se conservó; puedes reintentar.') from None
        raise
    return {'status': 'completed', 'replayed': False}


@router.patch('/conversations/{conversation_id}/proposals/{proposal_id}', summary='Aceptar o rechazar un plan, sin ejecutar estadísticas')
async def decide(project_id: UUID, conversation_id: UUID, proposal_id: UUID, body: Decision, user: CurrentUser):
    conversation = await conversation_for(user, project_id, conversation_id)
    proposal = await user.store.one('analysis_proposals', {'id': str(proposal_id), 'conversation_id': str(conversation_id)})
    # Replay de una decisión histórica: no transiciona a ready ni reinterpreta su contrato.
    # Preparación/ejecución revalidan obligatoriamente productos, incluso si ya fue aceptada.
    if proposal['status'] == body.status:
        return {'status': body.status}
    if body.status == 'accepted':
        try:
            plan = Plan.model_validate(proposal['analysis_plan'])
            files = await linked_files(user.store, conversation)
            validate_reply(AssistantReply(response='Validación del plan', suggested_stage='proposal', proposals=[plan]),
                           files, await project_for(user, project_id), conversation.get('stage_data', {}))
            from app.services.requested_scope import validate_plan_scope
            validate_plan_scope(plan, conversation.get('stage_data', {}).get('requested_scope'), files)
        except (ValidationError, ValueError) as exc:
            from app.services.planning_errors import PlanningError
            if isinstance(exc, PlanningError) and exc.category in ('output_scope', 'output_capability', 'requested_scope', 'variable_type'):
                raise HTTPException(422, str(exc), headers={'X-Statia-Error': exc.category}) from None
            raise HTTPException(422, 'El plan ya no es válido para los archivos actuales. Solicita una propuesta nueva.') from None
    if proposal['status'] != body.status:
        await user.store.rpc('decide_proposal', {'p_conversation': str(conversation_id), 'p_proposal': str(proposal_id), 'p_status': body.status})
    return {'status': body.status, 'warnings': descriptive_warnings(plan) if body.status == 'accepted' else []}


@router.get('/files', summary='Listar archivos disponibles para reutilización')
async def list_files(project_id: UUID, user: CurrentUser):
    await project_for(user, project_id)
    files = await user.store.rows('project_files', {'project_id': str(project_id)}, order='created_at.desc',
                                 select='id,original_name,file_type,file_role,file_size,created_at')
    return [{**file, 'metadata': {'sheets': []}} for file in files]


@router.post('/conversations/{conversation_id}/files', status_code=201, summary='Inspeccionar, subir a bucket privado y asociar archivo')
async def upload_file(project_id: UUID, conversation_id: UUID, request: Request, user: CurrentUser,
                      file: Annotated[UploadFile, File()], file_role: Annotated[str, Form()] = 'dataset'):
    async with request.app.state.file_upload_lock:
        return await upload_project_file(project_id, conversation_id, request, user, file, file_role)


async def upload_project_file(project_id, conversation_id, request, user, file, file_role):
    conversation = await conversation_for(user, project_id, conversation_id)
    if file_role not in ('dataset', 'instrument'):
        raise HTTPException(422, 'El rol debe ser dataset o instrument.')
    if conversation.get('active_request_id'):
        raise HTTPException(409, 'Espera a que termine la respuesta antes de adjuntar archivos.')
    settings = request.app.state.settings
    files = await linked_files(user.store, conversation)
    name = (file.filename or 'archivo')[:240]
    async with request.app.state.profile_lock:
        data = await file.read(settings.max_file_bytes + 1)
        await file.close()
        metadata = await asyncio.to_thread(inspect_file, name, data, file_role, settings)
    digest = hashlib.sha256(data).hexdigest()
    existing = await user.store.rows('project_files', {'project_id': str(project_id)})
    match = next((f for f in existing if f['file_role'] == file_role and f['file_type'] == metadata['file_type']
                  and f.get('metadata', {}).get('content_sha256') == digest
                  # Un libro perfilado puede necesitar otra hoja: conservar la posibilidad de nueva referencia.
                  and not (f['file_type'] == 'xlsx' and f.get('metadata', {}).get('profile'))), None)
    linked = {f['id'] for f in files}
    if match and match['id'] in linked:
        return match
    if len(files) >= settings.max_conversation_files:
        raise HTTPException(422, 'Se alcanzó el límite de archivos de la conversación.')
    if match:
        await user.store.insert('conversation_files', {'conversation_id': str(conversation_id), 'file_id': match['id'], 'project_id': str(project_id)})
        return match
    metadata['content_sha256'] = digest
    fid = str(uuid4())
    path = f'{user.user_id}/{project_id}/{fid}/{safe_name(name)}'
    await user.store.upload(path, data, MIMES[metadata['file_type']])
    record = {'id': fid, 'project_id': str(project_id), 'uploaded_by': user.user_id, 'original_name': name,
              'storage_path': path, 'file_type': metadata['file_type'], 'file_role': file_role, 'file_size': len(data), 'metadata': metadata}
    try:
        saved = (await user.store.insert('project_files', record))[0]
        await user.store.insert('conversation_files', {'conversation_id': str(conversation_id), 'file_id': fid, 'project_id': str(project_id)})
    except Exception:
        # Compensación: jamás registrar como disponible una subida que falló.
        try:
            await user.store.delete('project_files', {'id': fid})
            await user.store.remove_object(path)
        except Exception:
            logging.getLogger(__name__).warning('La compensación de una subida requiere revisar objetos huérfanos del bucket.')
        raise
    return saved


@router.put('/files/{file_id}/sheet', summary='Elegir la hoja del XLSX y generar su perfil')
async def select_sheet(project_id: UUID, file_id: UUID, body: Rename, request: Request, user: CurrentUser):
    await project_for(user, project_id)
    file = await user.store.one('project_files', {'id': str(file_id), 'project_id': str(project_id)})
    if file['file_type'] != 'xlsx':
        raise HTTPException(422, 'Solo los libros XLSX permiten seleccionar hojas.')
    # Congelar el perfil usado por planes: otra hoja se adjunta como nueva referencia.
    if file['metadata'].get('profile'):
        raise HTTPException(409, 'La hoja ya fue perfilada. Adjunta el libro de nuevo para trabajar con otra hoja sin alterar planes previos.')
    data = await user.store.download(file['storage_path'])
    async with request.app.state.profile_lock:
        metadata = await asyncio.to_thread(inspect_file, file['original_name'], data, 'dataset', request.app.state.settings, body.title)
    if file['metadata'].get('content_sha256'):
        metadata['content_sha256'] = file['metadata']['content_sha256']
    return (await user.store.update('project_files', {'id': str(file_id)}, {'metadata': metadata}))[0]


@router.get('/files/{file_id}/profile', summary='Consultar perfil descriptivo o metadatos del instrumento')
async def get_profile(project_id: UUID, file_id: UUID, user: CurrentUser):
    await project_for(user, project_id)
    return (await user.store.one('project_files', {'id': str(file_id), 'project_id': str(project_id)}))['metadata']


@router.get('/files/{file_id}/rows', response_model=FileRows, summary='Consultar una página de registros originales, sin enviar datos a IA')
async def get_rows(project_id: UUID, file_id: UUID, request: Request, user: CurrentUser, response: Response,
                   offset: int = Query(default=0, ge=0, le=20000), limit: int = Query(default=50, ge=1, le=100)):
    from app.services.data_preview import preview_rows
    await project_for(user, project_id)
    file = await user.store.one('project_files', {'id': str(file_id), 'project_id': str(project_id)})
    if file['file_role'] != 'dataset':
        raise HTTPException(422, 'Los instrumentos PDF se consultan desde sus metadatos.')
    settings = request.app.state.settings
    async with request.app.state.profile_lock:
        data = await user.store.download(file['storage_path'], max_bytes=settings.max_file_bytes)
        page = await asyncio.to_thread(preview_rows, file, data, settings, offset, limit)
    response.headers['Cache-Control'] = 'no-store'
    return page


@router.get('/files/{file_id}/download', summary='Descargar original con autorización del propietario y RLS')
async def download_file(project_id: UUID, file_id: UUID, user: CurrentUser):
    await project_for(user, project_id)
    file = await user.store.one('project_files', {'id': str(file_id), 'project_id': str(project_id)})
    return Response(await user.store.download(file['storage_path']), media_type=MIMES[file['file_type']],
                    headers={'Content-Disposition': f'attachment; filename="{safe_name(file["original_name"])}"', 'Cache-Control': 'no-store'})
