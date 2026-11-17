// PostgreSQL WASM, Auth/Storage emulados. Sin claves, red ni modificaciones remotas.
import { PGlite } from '@electric-sql/pglite'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import assert from 'node:assert/strict'

test('proveedores: migración aditiva, RLS, procedencia, bloqueo, reintento y compatibilidad', async () => {
  const db = new PGlite()
  const q = async (sql, args = []) => (await db.query(sql, args)).rows
  const a = '00000000-0000-0000-0000-000000000001'
  const b = '00000000-0000-0000-0000-000000000002'
  const project = '10000000-0000-0000-0000-000000000001'
  const legacyRequest = '30000000-0000-0000-0000-000000000001'
  const request = '30000000-0000-0000-0000-000000000002'
  const failed = '30000000-0000-0000-0000-000000000003'
  try {
    await db.exec(`
      create role anon; create role authenticated;
      create schema auth; create table auth.users(id uuid primary key);
      create function auth.uid() returns uuid language sql stable as
      $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
      create schema storage;
      create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
      create table storage.objects(id uuid default gen_random_uuid(),bucket_id text,name text);
      alter table storage.objects enable row level security;
      create function storage.foldername(text) returns text[] language sql immutable as
      $$ select (string_to_array($1,'/'))[1:array_length(string_to_array($1,'/'),1)-1] $$;
      grant usage on schema public,auth,storage to authenticated,anon;
      grant execute on function auth.uid(), storage.foldername(text) to authenticated,anon;
      grant select,insert,delete on storage.objects to authenticated;
      insert into auth.users values ('${a}'),('${b}');
    `)
    for (const name of ['202611150001_projects.sql', '202611150002_chat.sql', '202611150003_chat_titles.sql',
      '202611150004_analysis_results.sql', '202611160005_chat_timeline.sql', '202611160006_research_context.sql'])
      await db.exec(await readFile(new URL(`../migrations/${name}`, import.meta.url), 'utf8'))
    await db.exec(`set role authenticated; set request.jwt.claim.sub='${a}';`)
    await q("insert into public.projects(id,user_id,name,project_type) values($1,$2,'Proyecto sintético','general')", [project, a])
    const cid = (await q('select public.create_conversation($1) as id', [project]))[0].id
    const payload = {display: 'Describe las medidas', action: 'message'}
    await q('select public.begin_chat_turn($1,$2,$3)', [cid, legacyRequest, JSON.stringify(payload)])
    await q('select public.finish_chat_turn($1,$2,$3)', [cid, legacyRequest, JSON.stringify({
      stage: 'proposal', content: 'Respuesta histórica', message_type: 'text', metadata: { historical: true },
      proposals: [{title: 'Plan histórico', objective: 'Describir', variables: []}]
    })])
    const historical = await q('select * from public.messages where conversation_id=$1 order by position', [cid])
    const proposals = await q('select * from public.analysis_proposals where conversation_id=$1', [cid])
    await db.exec('reset role')
    await db.exec(await readFile(new URL('../migrations/202611170007_assistant_providers.sql', import.meta.url), 'utf8'))
    assert.deepEqual(await q('select * from public.messages where conversation_id=$1 order by position', [cid]), historical)
    assert.deepEqual(await q('select * from public.analysis_proposals where conversation_id=$1', [cid]), proposals)
    const signatures = ['select_conversation_provider(uuid,text,text)', 'create_provider_conversation(uuid,uuid,text)',
      'begin_provider_chat_turn(uuid,uuid,jsonb,text,text)']
    for (const name of signatures) {
      assert.equal((await q('select prosecdef from pg_proc where oid=$1::regprocedure', ['public.' + name]))[0].prosecdef, false)
      assert.equal((await q("select has_function_privilege('anon',$1,'execute') as ok", ['public.' + name]))[0].ok, false)
    }
    await db.exec(`set role authenticated; set request.jwt.claim.sub='${a}';`)
    assert.equal((await q('select assistant_provider from public.conversations where id=$1', [cid]))[0].assistant_provider, 'gemini')
    assert.deepEqual((await q('select provider,model from public.chat_requests where request_id=$1', [legacyRequest]))[0], {provider: 'gemini', model: null})
    const begin = async (rid = request, provider = 'openai', model = 'gpt-6.1-terra', body = payload) =>
      (await q('select public.begin_provider_chat_turn($1,$2,$3,$4,$5) as status', [cid, rid, JSON.stringify(body), provider, model]))[0].status
    assert.equal(await begin(legacyRequest), 'completed')
    assert.equal(await begin(), 'provider_changed')
    await assert.rejects(q("select public.select_conversation_provider($1,'unknown','gemini')", [cid]))
    await q("select public.select_conversation_provider($1,'openai','gemini')", [cid])
    const events = await q("select * from public.messages where metadata->>'event'='provider_selected'")
    assert.equal(events.length, 1)
    assert.equal(events[0].metadata.provider, 'openai')
    await q("select public.select_conversation_provider($1,'openai','openai')", [cid])
    assert.equal((await q("select * from public.messages where metadata->>'event'='provider_selected'")).length, 1)
    await assert.rejects(q("select public.select_conversation_provider($1,'gemini','gemini')", [cid]))
    await assert.rejects(begin(request, 'openai', 'modelo-arbitrario'))
    assert.equal(await begin(), 'started')
    assert.equal(await begin(), 'busy')
    assert.deepEqual((await q('select provider,model from public.chat_requests where request_id=$1', [request]))[0], {provider: 'openai', model: 'gpt-6.1-terra'})
    await assert.rejects(q("select public.select_conversation_provider($1,'gemini','openai')", [cid]))
    // También proteger la escritura REST directa bajo RLS.
    await assert.rejects(q("update public.conversations set assistant_provider='gemini' where id=$1", [cid]))
    await q('select public.fail_chat_turn($1,$2)', [cid, request])
    assert.equal(await begin(), 'started')
    assert.equal((await q("select * from public.messages where metadata->>'request_id'=$1", [request])).length, 1)
    const result = {stage: 'goal', content: 'Respuesta Terra', message_type: 'text', metadata: {generation: {provider: 'openai', model: 'gpt-6.1-terra'}}}
    await q('select public.finish_chat_turn($1,$2,$3)', [cid, request, JSON.stringify(result)])
    const afterTerra = await q('select * from public.messages where conversation_id=$1 order by position', [cid])
    assert.equal(await begin(failed), 'started')
    await q('select public.fail_chat_turn($1,$2)', [cid, failed])
    await q("select public.select_conversation_provider($1,'gemini','openai')", [cid])
    assert.equal(await begin(failed, 'gemini', 'gemini-test'), 'provider_changed')
    assert.equal(await begin(), 'completed')
    assert.equal(await begin(request, 'openai', 'gpt-6.1-terra', {display: 'Otro mensaje'}), 'mismatch')
    assert.deepEqual((await q('select * from public.messages where conversation_id=$1 order by position', [cid])).slice(0, afterTerra.length), afterTerra)
    assert.deepEqual(await q('select * from public.analysis_proposals where conversation_id=$1', [cid]), proposals)
    // El bloqueo de una ejecución Python también impide cambiar destinatario.
    await q("update public.analysis_proposals set status='accepted' where id=$1", [proposals[0].id])
    const run = (await q('select public.begin_analysis_run($1,$2,$3,$4,$5) as value', [cid, proposals[0].id,
      '40000000-0000-0000-0000-000000000001', JSON.stringify({decisions_confirmed: true}), JSON.stringify(proposals[0].analysis_plan)]))[0].value
    await assert.rejects(q("select public.select_conversation_provider($1,'openai','gemini')", [cid]))
    assert.equal(await begin('30000000-0000-0000-0000-000000000004', 'gemini', 'gemini-test'), 'busy')
    assert.ok(run)
    // Contratos previos siguen disponibles; creación explícita y default no heredan selección.
    const defaultId = (await q('select public.create_provider_conversation($1) as id', [project]))[0].id
    assert.equal((await q('select assistant_provider from public.conversations where id=$1', [defaultId]))[0].assistant_provider, 'gemini')
    const explicit = (await q("select public.create_provider_conversation($1,null,'openai') as id", [project]))[0].id
    assert.equal((await q('select assistant_provider from public.conversations where id=$1', [explicit]))[0].assistant_provider, 'openai')
    await db.exec(`set request.jwt.claim.sub='${b}'`)
    assert.equal((await q('select * from public.conversations where id=$1', [cid])).length, 0)
    assert.equal((await q('select * from public.chat_requests where conversation_id=$1', [cid])).length, 0)
    await assert.rejects(q("select public.select_conversation_provider($1,'openai','gemini')", [cid]))
    await assert.rejects(begin())
    await assert.rejects(q("select public.create_provider_conversation($1,null,'openai')", [project]))
    assert.equal((await q("update public.conversations set assistant_provider='openai' where id=$1 returning id", [cid])).length, 0)
  } finally {
    await db.close()
  }
})
