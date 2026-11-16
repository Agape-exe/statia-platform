// PostgreSQL real WASM; Auth y catálogo de Storage emulados. No acredita Supabase remoto.
import { PGlite } from '@electric-sql/pglite'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import assert from 'node:assert/strict'

test('resultados: migración, RLS, integridad, concesiones, transacción e idempotencia', async () => {
  const db = new PGlite()
  const q = async (sql, params = []) => (await db.query(sql, params)).rows
  const a = '00000000-0000-0000-0000-000000000001'
  const b = '00000000-0000-0000-0000-000000000002'
  const project = '10000000-0000-0000-0000-000000000001'
  const project2 = '10000000-0000-0000-0000-000000000002'
  const request = '20000000-0000-0000-0000-000000000001'
  const request2 = '20000000-0000-0000-0000-000000000002'
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
    for (const name of ['202611150001_projects.sql', '202611150002_chat.sql', '202611150003_chat_titles.sql', '202611150004_analysis_results.sql', '202611160005_chat_timeline.sql'])
      await db.exec(await readFile(new URL(`../migrations/${name}`, import.meta.url), 'utf8'))
    assert.equal((await q("select public from storage.buckets where id='analysis-results'"))[0].public, false)
    assert.equal((await q("select has_function_privilege('anon','public.finish_analysis_run(uuid,uuid,jsonb,jsonb)','execute') as allowed"))[0].allowed, false)
    assert.equal((await q("select prosecdef from pg_proc where oid='public.finish_analysis_run(uuid,uuid,jsonb,jsonb)'::regprocedure"))[0].prosecdef, false)
    await db.exec(`set role authenticated; set request.jwt.claim.sub='${a}';`)
    await q("insert into public.projects(id,user_id,name,project_type) values ($1,$2,'A','general'),($3,$2,'A2','general')", [project, a, project2])
    const cid = (await q('select public.create_conversation($1) as id', [project]))[0].id
    const cid2 = (await q('select public.create_conversation($1) as id', [project2]))[0].id
    const plan = { schema_version: 1, title: 'Describir mediciones', objective: 'Describir valores', variables: [] }
    const proposal = (await q("insert into public.analysis_proposals(conversation_id,title,objective,analysis_plan) values ($1,$2,$3,$4) returning id", [cid, plan.title, plan.objective, JSON.stringify(plan)]))[0].id
    const spec = { schema_version: 1, decisions_confirmed: true }
    const begin = async (specification = spec, rid = request) => (await q('select public.begin_analysis_run($1,$2,$3,$4,$5) as result', [cid, proposal, rid, JSON.stringify(specification), JSON.stringify(plan)]))[0].result
    await assert.rejects(begin())
    await q("select public.decide_proposal($1,$2,'accepted')", [cid, proposal])
    const started = await begin()
    assert.equal(started.status, 'started')
    assert.equal((await begin()).status, 'busy')
    assert.equal((await begin({ ...spec, changed: true })).status, 'mismatch')
    assert.equal((await begin(spec, request2)).status, 'busy')
    assert.equal((await q('select public.begin_chat_turn($1,$2,$3) as status', [cid, request2, JSON.stringify({display:'Pregunta', action:'message'})]))[0].status, 'busy')
    await assert.rejects(q('update public.analysis_runs set project_id=$1 where id=$2', [project2, started.run_id]))
    await assert.rejects(q('update public.analysis_runs set conversation_id=$1 where id=$2', [cid2, started.run_id]))
    const path = `${a}/${project}/${started.run_id}/${started.lease_token}/resultados_analisis.zip`
    const artifact = { name: 'resultados_analisis.zip', storage_path: path, mime_type: 'application/zip', size_bytes: 100, sha256: 'a'.repeat(64) }
    const result = { schema_version: 1, run_id: started.run_id, project_id: project, conversation_id: cid, proposal_id: proposal,
      status: 'completed', specification: spec, plan_snapshot: plan, summary: 'Resultado calculado; puedes preguntar por él.' }
    const finish = () => q('select public.finish_analysis_run($1,$2,$3,$4)', [started.run_id, started.lease_token, JSON.stringify(result), JSON.stringify([artifact])])
    await assert.rejects(finish()) // Falta objeto; no hay metadatos ni completado parcial.
    assert.equal((await q('select status from public.analysis_runs'))[0].status, 'running')
    assert.equal((await q('select * from public.analysis_artifacts')).length, 0)
    await assert.rejects(q('insert into storage.objects(bucket_id,name) values($1,$2)', ['analysis-results', `${a}/${project}/${started.run_id}/${request}/fuera.png`]))
    await q('insert into storage.objects(bucket_id,name) values($1,$2)', ['analysis-results', path])
    await finish()
    assert.equal((await begin()).status, 'replayed')
    assert.equal((await q('select * from public.analysis_runs')).length, 1)
    assert.equal((await q("select * from public.messages where metadata ? 'analysis_run_id'")).length, 1)
    assert.equal((await q('select current_stage from public.conversations where id=$1', [cid]))[0].current_stage, 'ready')
    await assert.rejects(q('update public.analysis_artifacts set run_id=$1', [request]))
    await assert.rejects(q("update public.analysis_runs set status='completed',result=null where id=$1", [started.run_id]))

    await db.exec(`set request.jwt.claim.sub='${b}';`)
    assert.equal((await q('select * from public.analysis_runs')).length, 0)
    assert.equal((await q('select * from public.analysis_artifacts')).length, 0)
    assert.equal((await q("select * from storage.objects where bucket_id='analysis-results'")).length, 0)
    await assert.rejects(q('insert into storage.objects(bucket_id,name) values($1,$2)', ['analysis-results', path + '.intrusion']))
    await assert.rejects(begin())
    await assert.rejects(finish())
    assert.equal((await q("update public.analysis_runs set error='Intrusión' returning id")).length, 0)

    await db.exec(`set request.jwt.claim.sub='${a}';`)
    const second = await begin(spec, request2)
    await q("update public.analysis_runs set started_at=now()-interval '181 seconds' where id=$1", [second.run_id])
    const restarted = await begin(spec, request2)
    assert.equal(restarted.run_id, second.run_id)
    assert.notEqual(restarted.lease_token, second.lease_token)
    await q('select public.fail_analysis_run($1,$2,$3)', [second.run_id, second.lease_token, 'Concesión antigua'])
    assert.equal((await q('select status from public.analysis_runs where id=$1', [second.run_id]))[0].status, 'running')
    await q('select public.fail_analysis_run($1,$2,$3)', [restarted.run_id, restarted.lease_token, 'Error controlado'])
    assert.equal((await q('select status from public.analysis_runs where id=$1', [second.run_id]))[0].status, 'failed')
    await q('select public.begin_chat_turn($1,$2,$3)', [cid, request2, JSON.stringify({display:'Pregunta', action:'message'})])
    assert.equal((await begin(spec, request2)).status, 'busy')
    // La preparación usa JSONB/RPC existentes; no requiere otra migración.
    const preparation = { proposal_id: proposal, answers: { 'pregunta-con-hash': 'missing' },
      result: { schema_version: 1, status: 'NEEDS_CLARIFICATION', specification: null,
        questions: [{ id: 'pregunta-con-hash', prompt: '¿Qué significa este marcador?' }] } }
    const preparedTurn = { stage: 'ready', content: 'Aclaremos el marcador antes de ejecutar.', message_type: 'question',
      stage_data: { execution_preparation: preparation }, metadata: { execution_preparation: preparation.result }, proposals: [] }
    await q('select public.finish_chat_turn($1,$2,$3)', [cid, request2, JSON.stringify(preparedTurn)])
    const messagesBeforeReplay = (await q('select id from public.messages where conversation_id=$1', [cid])).length
    assert.equal((await q('select public.begin_chat_turn($1,$2,$3) as status', [cid, request2, JSON.stringify({display:'Pregunta', action:'message'})]))[0].status, 'completed')
    assert.equal((await q('select id from public.messages where conversation_id=$1', [cid])).length, messagesBeforeReplay)
    assert.deepEqual((await q('select stage_data from public.conversations where id=$1', [cid]))[0].stage_data.execution_preparation, preparation)
    assert.deepEqual((await q('select analysis_plan from public.analysis_proposals where id=$1', [proposal]))[0].analysis_plan, plan)
    const answerRequest = '20000000-0000-0000-0000-000000000003'
    const answerPayload = { action: 'clarify_execution', proposal_id: proposal, question_id: 'pregunta-con-hash', answer: 'missing', display: 'Es información faltante' }
    assert.equal((await q('select public.begin_chat_turn($1,$2,$3) as status', [cid, answerRequest, JSON.stringify(answerPayload)]))[0].status, 'started')
    assert.equal((await begin(spec, answerRequest)).status, 'busy')
    await q('select public.finish_chat_turn($1,$2,$3)', [cid, answerRequest, JSON.stringify(preparedTurn)])
    assert.equal((await q('select public.begin_chat_turn($1,$2,$3) as status', [cid, answerRequest, JSON.stringify(answerPayload)]))[0].status, 'completed')
    // Unknown es una respuesta persistida, no otra pregunta sin contestar.
    const unknownRequest = '20000000-0000-0000-0000-000000000004'
    const unknownPayload = { action: 'clarify_execution', proposal_id: proposal, question_id: 'diseno-estable', answer: 'unknown', display: 'No lo sé' }
    const uncertain = { ...preparation, answers: { ...preparation.answers, 'diseno-estable': 'unknown' },
      result: { schema_version: 1, status: 'BLOCKED_UNCERTAINTY', questions: [], fingerprint: 'b'.repeat(64),
        clarifications: [{ id: 'pregunta-con-hash', status: 'answered', answer: 'missing' }, { id: 'diseno-estable', status: 'unknown', answer: 'unknown' }] } }
    assert.equal((await q('select public.begin_chat_turn($1,$2,$3) as status', [cid, unknownRequest, JSON.stringify(unknownPayload)]))[0].status, 'started')
    await q('select public.finish_chat_turn($1,$2,$3)', [cid, unknownRequest, JSON.stringify({ ...preparedTurn, content: 'La información sigue siendo desconocida.', stage_data: {execution_preparation: uncertain}, metadata: {execution_preparation: uncertain.result} })])
    const afterUnknown = (await q('select id from public.messages where conversation_id=$1', [cid])).length
    assert.equal((await q('select public.begin_chat_turn($1,$2,$3) as status', [cid, unknownRequest, JSON.stringify(unknownPayload)]))[0].status, 'completed')
    assert.equal((await q('select id from public.messages where conversation_id=$1', [cid])).length, afterUnknown)
    assert.deepEqual((await q('select stage_data from public.conversations where id=$1', [cid]))[0].stage_data.execution_preparation, uncertain)
    const reviewRequest = '20000000-0000-0000-0000-000000000005'
    await q('select public.begin_chat_turn($1,$2,$3)', [cid, reviewRequest, JSON.stringify({action:'review_execution', question_id:'diseno-estable', display:'Revisar respuesta'})])
    const reviewing = { ...uncertain, review_question_id:'diseno-estable', result: {...uncertain.result, status:'NEEDS_CLARIFICATION', questions:[{id:'diseno-estable'}]} }
    await q('select public.finish_chat_turn($1,$2,$3)', [cid, reviewRequest, JSON.stringify({...preparedTurn, content:'Revisión solicitada explícitamente.', stage_data:{execution_preparation:reviewing}})])
    const persistedReview = (await q('select stage_data from public.conversations where id=$1', [cid]))[0].stage_data.execution_preparation
    assert.equal(persistedReview.answers['pregunta-con-hash'], 'missing')
    assert.equal(persistedReview.answers['diseno-estable'], 'unknown')
    assert.equal(persistedReview.result.questions[0].id, 'diseno-estable')
    assert.deepEqual((await q('select analysis_plan from public.analysis_proposals where id=$1', [proposal]))[0].analysis_plan, plan)
    await db.exec(`set request.jwt.claim.sub='${b}';`)
    assert.equal((await q('select stage_data from public.conversations where id=$1', [cid])).length, 0)
    assert.equal((await q('select * from public.messages where conversation_id=$1', [cid])).length, 0)
  } finally { await db.close() }
})
