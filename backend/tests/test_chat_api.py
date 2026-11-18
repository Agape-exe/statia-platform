"""Contrato HTTP y orquestación con repositorio/proveedor controlados; sin servicios remotos."""
import copy
import io
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.core.auth import Identity, authenticated
from app.core.config import Settings
from app.main import create_app
from app.models.chat import AssistantReply
from app.services.gemini import GeminiProvider


class MemoryStore:
    def __init__(self):
        self.user_id = str(uuid4())
        self.project_id = str(uuid4())
        self.data = {name: [] for name in ('projects', 'conversations', 'messages', 'project_files', 'conversation_files', 'analysis_proposals', 'chat_requests', 'analysis_runs', 'analysis_artifacts', 'research_contexts')}
        self.data['projects'] = [{'id': self.project_id, 'user_id': self.user_id, 'project_type': 'general'}]
        self.objects = {}
        self.fail_link = False

    async def rows(self, table, filters=None, order=None, limit=None, select='*'):
        def matches(row, k, v):
            return row.get(k) in v if isinstance(v, list) else row.get(k) < v[1] if isinstance(v, tuple) else row.get(k) == v
        rows = [copy.deepcopy(row) for row in self.data[table] if all(matches(row, k, v) for k, v in (filters or {}).items())]
        if order:
            key = order.split('.')[0]
            rows.sort(key=lambda row: row.get(key, 0), reverse='.desc' in order)
        return rows[:limit] if limit else rows

    async def one(self, table, filters):
        rows = await self.rows(table, filters)
        if not rows:
            raise HTTPException(404, 'El recurso no existe o no tienes acceso.')
        return rows[0]

    async def insert(self, table, data):
        if table == 'conversation_files' and self.fail_link:
            raise HTTPException(502, 'Falló la asociación.')
        row = {'id': str(uuid4()), 'created_at': len(self.data[table]), 'position': len(self.data[table]), **copy.deepcopy(data)}
        self.data[table].append(row)
        return [copy.deepcopy(row)]

    async def update(self, table, filters, data):
        result = []
        for row in self.data[table]:
            if all(row.get(k) == v for k, v in filters.items()):
                row.update(copy.deepcopy(data))
                result.append(copy.deepcopy(row))
        return result

    async def delete(self, table, filters):
        self.data[table] = [row for row in self.data[table] if not all(row.get(k) == v for k, v in filters.items())]

    async def upload(self, path, data, mime):
        self.objects[path] = data

    async def remove_object(self, path):
        self.objects.pop(path, None)

    async def download(self, path):
        return self.objects[path]

    async def rpc(self, name, data):
        if name == 'provider_rollback_safety':
            return 1
        cid = data.get('p_conversation')
        if name == 'create_provider_conversation':
            created = await self.rpc('create_conversation', data)
            await self.update('conversations', {'id': created}, {'assistant_provider': data['p_provider']})
            return created
        if name == 'select_conversation_provider':
            c = next(row for row in self.data['conversations'] if row['id'] == cid)
            if c.get('active_request_id') or c.get('assistant_provider', 'gemini') != data['p_expected']:
                raise HTTPException(409, 'Conversación ocupada o selección cambiada.')
            if c.get('assistant_provider', 'gemini') != data['p_provider']:
                await self.insert('messages', {'conversation_id': cid, 'role': 'system', 'content': 'Proveedor seleccionado.',
                    'message_type': 'event', 'metadata': {'event': 'provider_selected', 'provider': data['p_provider']}})
            c['assistant_provider'] = data['p_provider']
            return
        if name == 'begin_provider_chat_turn':
            c = next(row for row in self.data['conversations'] if row['id'] == cid)
            previous = next((r for r in self.data['chat_requests'] if r['request_id'] == data['p_request'] and r['conversation_id'] == cid), None)
            if previous and previous['payload'] != data['p_payload']:
                return 'mismatch'
            if previous and previous['status'] == 'completed':
                return 'completed'
            if c.get('assistant_provider', 'gemini') != data['p_provider'] or previous and (
                previous.get('provider', 'gemini') != data['p_provider'] or previous.get('model') not in (None, data['p_model'])):
                return 'provider_changed'
            status = await self.rpc('begin_chat_turn', data)
            if status == 'started':
                await self.update('chat_requests', {'conversation_id': cid, 'request_id': data['p_request']},
                                  {'provider': data['p_provider'], 'model': data['p_model']})
            return status
        if name == 'create_conversation':
            prior = [c for c in self.data['conversations'] if c['project_id'] == data['p_project']]
            links = [f['file_id'] for f in self.data['conversation_files'] if prior and f['conversation_id'] == prior[-1]['id']]
            c = (await self.insert('conversations', {'project_id': data['p_project'], 'title': 'Nueva conversación', 'primary_goal': None,
                'current_stage': 'reuse' if links else 'instrument', 'stage_data': {'reuse_file_ids': links}, 'active_request_id': None}))[0]
            if data.get('p_source'):
                source = await self.one('conversations', {'id': data['p_source']})
                change = source['stage_data']['goal_change']
                await self.update('conversations', {'id': c['id']}, {'primary_goal': change['goal'], 'title': change.get('title') or c['title']})
            for content in ('Hola, soy tu asistente estadístico.', '¿Deseas reutilizar archivos?' if links else '¿Utilizaste un instrumento?'):
                await self.insert('messages', {'conversation_id': c['id'], 'role': 'assistant', 'content': content, 'message_type': 'question', 'metadata': {}})
            return c['id']
        c = next(row for row in self.data['conversations'] if row['id'] == cid)
        if name == 'begin_chat_turn':
            previous = next((r for r in self.data['chat_requests'] if r['request_id'] == data['p_request'] and r['conversation_id'] == cid), None)
            if previous and previous['payload'] != data['p_payload']:
                return 'mismatch'
            if previous and previous['status'] == 'completed':
                return 'completed'
            if c['active_request_id']:
                return 'busy'
            if not previous:
                await self.insert('chat_requests', {'conversation_id': cid, 'request_id': data['p_request'], 'payload': data['p_payload'], 'status': 'pending'})
                await self.insert('messages', {'conversation_id': cid, 'role': 'user', 'content': data['p_payload']['display'], 'message_type': 'text', 'metadata': {'request_id': data['p_request']}})
            c['active_request_id'] = data['p_request']
            return 'started'
        if name == 'finish_chat_turn':
            result = data['p_result']
            c['current_stage'] = result['stage']
            c['stage_data'] = result.get('stage_data', c['stage_data'])
            c['primary_goal'] = c['primary_goal'] or result.get('goal')
            if not c.get('title_manual'):
                c['title'] = result.get('title') or c['title']
            c['active_request_id'] = None
            await self.insert('messages', {'conversation_id': cid, 'role': 'assistant', 'content': result['content'], 'message_type': result['message_type'], 'metadata': result.get('metadata', {})})
            for plan in result.get('proposals', []):
                await self.insert('analysis_proposals', {'conversation_id': cid, 'title': plan['title'], 'objective': plan['objective'], 'analysis_plan': plan, 'status': 'proposed'})
            for fid in result.get('link_file_ids', []):
                await self.insert('conversation_files', {'conversation_id': cid, 'file_id': fid, 'project_id': c['project_id']})
            await self.update('chat_requests', {'conversation_id': cid, 'request_id': data['p_request']}, {'status': 'completed'})
        elif name == 'fail_chat_turn':
            c['active_request_id'] = None
            await self.update('chat_requests', {'conversation_id': cid, 'request_id': data['p_request']}, {'status': 'failed'})
        elif name == 'decide_proposal':
            proposal = await self.one('analysis_proposals', {'id': data['p_proposal']})
            if proposal['status'] == data['p_status']:
                return
            await self.update('analysis_proposals', {'id': data['p_proposal']}, {'status': data['p_status']})
            c['current_stage'] = 'ready' if data['p_status'] == 'accepted' else 'goal'
            if data['p_status'] == 'accepted' and not c.get('title_manual') and (c['stage_data'].get('title_provisional') or c['title'] == 'Nueva conversación'):
                from app.services.titles import compact_title
                c['title'] = compact_title(proposal['title'])
                c['primary_goal'] = c['primary_goal'] or proposal['objective']
                c['stage_data']['title_provisional'] = False


class ControlledProvider:
    def __init__(self):
        self.replies = []
        self.contexts = []

    async def generate(self, context, correction=None):
        self.contexts.append((copy.deepcopy(context), correction))
        result = self.replies.pop(0)
        if isinstance(result, Exception):
            raise result
        return AssistantReply.model_validate(result)


@pytest.fixture
def api():
    settings = Settings(_env_file=None)
    app = create_app(settings)
    store, provider = MemoryStore(), ControlledProvider()
    app.dependency_overrides[authenticated] = lambda: Identity(store.user_id, store)
    app.state.provider = provider
    with TestClient(app) as client:
        yield client, store, provider


def new(client, store):
    response = client.post(f'/projects/{store.project_id}/conversations', json={})
    assert response.status_code == 201
    return f'/projects/{store.project_id}/conversations/{response.json()["id"]}'


def turn(client, path, *, action='message', content='', request_id=None, **kwargs):
    return client.post(path + '/turns', json={'request_id': request_id or str(uuid4()), 'action': action, 'content': content, **kwargs})


def reply(**kwargs):
    return {'response': 'Comprendí las mediciones disponibles.', 'suggested_stage': 'clarification', **kwargs}


def plan(fid, thesis=False):
    return {'title': 'Describir las mediciones', 'objective': 'Conocer la distribución de las notas (nota)',
            'variables': [{'file_id': fid, 'sheet': 'tabla', 'column': 'nota', 'role': 'outcome'}],
            'procedure': 'descriptive', 'method': 'Resúmenes descriptivos y frecuencias',
            'justification': 'Hay una medición numérica disponible.', 'requirements': ['Confirmar el significado de nota'],
            'limitations': ['No permite inferir causalidad'], 'expected_outputs': ['Tabla descriptiva'], 'methodology_confirmed': thesis}


def attach_dataset(client, path):
    response = client.post(path + '/files', files={'file': ('datos.csv', b'estudiante_id,grupo,nota\n1,A,10\n2,B,15\n', 'text/csv')}, data={'file_role': 'dataset'})
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_general_flow_persistence_goal_plan_acceptance_and_replay(api):
    client, store, provider = api
    path = new(client, store)
    assert len(client.get(path).json()['messages']) == 2
    assert turn(client, path, action='instrument_no').status_code == 200
    fid = attach_dataset(client, path)
    provider.replies.append(reply(questions=['¿Conoces el dataset y deseas añadir información?']))
    assert turn(client, path, action='files_ready').status_code == 200
    assert client.get(path).json()['conversation']['current_stage'] == 'clarification'
    provider.replies.append(reply(detected_goal='Explorar las notas', suggested_title='Exploración de notas', proposals=[plan(fid)], confirmation_required=True, suggested_stage='proposal'))
    request_id = str(uuid4())
    response = turn(client, path, content='No lo conozco, propón una exploración.', request_id=request_id)
    assert response.status_code == 200, response.text
    detail = client.get(path).json()
    assert detail['conversation']['primary_goal'] == 'Explorar las notas'
    assert detail['conversation']['title'] == 'Exploración de notas'
    proposal = detail['proposals'][0]
    assert proposal['status'] == 'proposed'
    assert turn(client, path, content='No lo conozco, propón una exploración.', request_id=request_id).json()['replayed']
    assert len(client.get(path).json()['messages']) == len(detail['messages'])
    accepted = client.patch(path + '/proposals/' + proposal['id'], json={'status': 'accepted'})
    assert accepted.status_code == 200
    detail = client.get(path).json()
    assert detail['conversation']['current_stage'] == 'ready'
    assert detail['proposals'][0]['status'] == 'accepted'
    assert len(provider.contexts) == 2
    assert provider.contexts[0][0]['project_mode'] == 'general'


def test_thesis_instrument_clarifications_proposal_and_rejection(api):
    client, store, provider = api
    store.data['projects'][0]['project_type'] = 'thesis'
    path = new(client, store)
    assert turn(client, path, action='instrument_yes').status_code == 200
    writer, out = PdfWriter(), io.BytesIO()
    writer.add_blank_page(width=100, height=100)
    writer.write(out)
    assert client.post(path + '/files', files={'file': ('instrumento.pdf', out.getvalue(), 'application/pdf')}, data={'file_role': 'instrument'}).status_code == 201
    assert turn(client, path, action='instruments_done').status_code == 200
    fid = attach_dataset(client, path)
    provider.replies.append(reply(questions=['¿Cuál es el diseño y qué representa la nota?']))
    assert turn(client, path, action='files_ready').status_code == 200
    provider.replies.append(reply(detected_goal='Describir rendimiento', proposals=[plan(fid, True)], suggested_stage='proposal'))
    assert turn(client, path, content='Es un estudio descriptivo; nota es el puntaje de mi instrumento.').status_code == 200
    detail = client.get(path).json()
    assert len(detail['files']) == 2
    assert provider.contexts[-1][0]['project_mode'] == 'thesis'
    assert provider.contexts[-1][0]['research_context'] is None
    assert client.patch(path + '/proposals/' + detail['proposals'][0]['id'], json={'status': 'rejected'}).status_code == 200
    assert client.get(path).json()['conversation']['current_stage'] == 'goal'


def test_reuse_and_goal_change_preserve_original(api):
    client, store, provider = api
    first = new(client, store)
    turn(client, first, action='instrument_no')
    fid = attach_dataset(client, first)
    second = new(client, store)
    assert client.get(second).json()['conversation']['current_stage'] == 'reuse'
    assert turn(client, second, action='reuse').status_code == 200
    assert len(store.objects) == 1
    assert client.get(second).json()['files'][0]['id'] == fid
    cid = second.split('/')[-1]
    awaitable_update = next(c for c in store.data['conversations'] if c['id'] == cid)
    awaitable_update['primary_goal'] = 'Describir notas'
    provider.replies.append(reply(goal_change=True, goal_change_reason='El nuevo objetivo estudia otro fenómeno.', detected_goal='Comparar ingresos', suggested_title='Ingresos'))
    assert turn(client, second, content='Ahora quiero investigar ingresos laborales.').status_code == 200
    detail = client.get(second).json()
    assert detail['conversation']['primary_goal'] == 'Describir notas'
    assert detail['conversation']['stage_data']['goal_change']['goal'] == 'Comparar ingresos'
    assert len(store.data['conversations']) == 2  # Nunca crear chats silenciosamente.
    created = client.post(f'/projects/{store.project_id}/conversations', json={'source_conversation_id': cid})
    assert created.status_code == 201
    assert created.json()['primary_goal'] == 'Comparar ingresos'
    assert client.get(second).json()['conversation']['primary_goal'] == 'Describir notas'
    assert turn(client, second, action='keep_goal').status_code == 200
    assert client.get(second).json()['conversation']['stage_data']['goal_change'] is None


def test_failed_provider_preserves_user_history_and_retries_without_duplicate(api):
    client, store, _ = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    attach_dataset(client, path)
    client.app.state.provider = GeminiProvider(Settings(_env_file=None, gemini_api_key=''))
    rid = str(uuid4())
    before = len(client.get(path).json()['messages'])
    response = turn(client, path, action='files_ready', request_id=rid)
    assert response.status_code == 503
    assert 'habilitar Gemini' in response.json()['detail']
    detail = client.get(path).json()
    assert len(detail['messages']) == before + 1
    assert detail['messages'][-1]['role'] == 'user'
    assert detail['retry_turn']['request_id'] == rid
    response = turn(client, path, action='files_ready', request_id=rid)
    assert response.status_code == 503
    assert len(client.get(path).json()['messages']) == before + 1


@pytest.mark.parametrize('failure', ['schema_400', 'invalid_json', 'incomplete_proposal'])
def test_structured_failure_never_persists_plan_and_retry_is_idempotent(api, monkeypatch, failure):
    import json
    from google.genai import errors
    from test_gemini import SDKDouble
    client, store, _ = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    fid = attach_dataset(client, path)
    result = {'schema_400': errors.APIError(400, {'error': {'message': 'Unknown name "additional_properties" at generation_config.response_schema'}}),
              'invalid_json': '{"response":',
              'incomplete_proposal': '{"response":"Plan","suggested_stage":"proposal","proposals":[{"title":"Incompleto"}]}'}[failure]
    sdk = SDKDouble([result, json.dumps(reply(proposals=[plan(fid)], suggested_stage='proposal'))])
    monkeypatch.setattr('app.services.gemini.genai.Client', lambda **kwargs: sdk)
    client.app.state.provider = GeminiProvider(Settings(_env_file=None, gemini_api_key='clave-ficticia'))
    rid = str(uuid4())
    before = client.get(path).json()
    response = turn(client, path, action='files_ready', request_id=rid)
    assert response.status_code == 502
    assert response.headers['X-Statia-Error'] == ('gemini_schema' if failure == 'schema_400' else 'gemini_invalid_response')
    failed = client.get(path).json()
    assert not failed['proposals']
    assert len(failed['messages']) == len(before['messages']) + 1
    assert failed['messages'][-1]['role'] == 'user'
    assert failed['retry_turn']['request_id'] == rid
    assert turn(client, path, action='files_ready', request_id=rid).status_code == 200
    completed = client.get(path).json()
    assert len(completed['proposals']) == 1
    assert len(completed['messages']) == len(before['messages']) + 2
    assert turn(client, path, action='files_ready', request_id=rid).json()['replayed']
    assert len(client.get(path).json()['messages']) == len(completed['messages'])
    assert len(sdk.calls) == 2


def test_invalid_columns_correct_once_and_never_persist_invalid_plan(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    fid = attach_dataset(client, path)
    invalid_plan = plan(fid)
    invalid_plan['variables'][0]['column'] = 'inexistente'
    provider.replies.extend([reply(proposals=[invalid_plan]), reply(proposals=[invalid_plan])])
    response = turn(client, path, action='files_ready')
    assert response.status_code == 502
    assert not client.get(path).json()['proposals']
    assert 'Columna inexistente' in provider.contexts[1][1]


def test_project_isolation_rename_delete_reuse_validation_and_compensation(api):
    client, store, _ = api
    path = new(client, store)
    assert client.patch(path, json={'title': 'Título propio'}).json()['title'] == 'Título propio'
    other_project = str(uuid4())
    store.data['projects'].append({'id': other_project, 'user_id': str(uuid4()), 'project_type': 'general'})
    assert client.get(path.replace(store.project_id, other_project)).status_code == 404
    assert client.get(f'/projects/{other_project}/conversations').status_code == 404
    assert turn(client, path, action='reuse', file_ids=[str(uuid4())]).status_code == 404
    store.fail_link = True
    response = client.post(path + '/files', files={'file': ('datos.csv', b'a\n1', 'text/csv')})
    assert response.status_code == 502
    assert not store.objects and not store.data['project_files']
    assert client.delete(path).status_code == 204
    assert client.get(path).status_code == 404


def test_auth_required_and_client_cannot_assign_identity():
    client = TestClient(create_app(Settings(_env_file=None)))
    assert client.get(f'/projects/{uuid4()}/conversations').status_code == 401
    assert client.get(f'/projects/{uuid4()}/conversations', headers={'Authorization': 'Bearer inventado'}).status_code == 503


def test_paged_history_and_acceptance_revalidates_stored_columns(api):
    client, store, provider = api
    path = new(client, store)
    turn(client, path, action='instrument_no')
    fid = attach_dataset(client, path)
    provider.replies.append(reply(proposals=[plan(fid)], suggested_stage='proposal'))
    assert turn(client, path, action='files_ready').status_code == 200
    proposal = store.data['analysis_proposals'][0]
    proposal['analysis_plan']['variables'][0]['column'] = 'columna_borrada'
    assert client.patch(path + '/proposals/' + proposal['id'], json={'status': 'accepted'}).status_code == 422
    cid = path.split('/')[-1]
    for index in range(110):
        store.data['messages'].append({'id': str(uuid4()), 'conversation_id': cid, 'role': 'user', 'content': str(index),
                                       'message_type': 'text', 'metadata': {}, 'position': 1000 + index})
    detail = client.get(path).json()
    assert len(detail['messages']) == 100 and detail['has_more_messages']
    previous = client.get(path + '/messages', params={'before': detail['messages'][0]['position']}).json()
    positions = [m['position'] for m in previous['messages'] + detail['messages']]
    assert positions == sorted(set(positions))


def test_upload_limits_same_names_download_and_xlsx_selection(api):
    from test_profiling import xlsx
    client, store, _ = api
    path = new(client, store)
    first = attach_dataset(client, path)
    second = attach_dataset(client, path)
    assert first != second and len(store.objects) == 2
    root = f'/projects/{store.project_id}/files/'
    assert client.get(root + first + '/download').content.startswith(b'estudiante_id')
    assert client.get(root + first + '/profile').json()['profile']['row_count'] == 2
    workbook = client.post(path + '/files', files={'file': ('libro.xlsx', xlsx(True))}).json()
    assert workbook['metadata']['needs_sheet_selection']
    selected = client.put(root + workbook['id'] + '/sheet', json={'title': 'Mediciones'})
    assert selected.status_code == 200
    assert selected.json()['metadata']['selected_sheet'] == 'Mediciones'
    assert client.put(root + workbook['id'] + '/sheet', json={'title': 'Instrumento'}).status_code == 409
    client.app.state.settings.max_file_bytes = 1024
    assert client.post(path + '/files', files={'file': ('grande.csv', b'a' * 1025)}).status_code == 413
