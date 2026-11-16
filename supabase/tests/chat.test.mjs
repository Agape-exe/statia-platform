// PostgreSQL real en WASM con Auth/Storage emulados; no usa Supabase remoto.
import { PGlite } from '@electric-sql/pglite'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const a = '00000000-0000-0000-0000-000000000001'
const b = '00000000-0000-0000-0000-000000000002'
const projectA = '10000000-0000-0000-0000-000000000001'
const projectA2 = '10000000-0000-0000-0000-000000000002'
const projectB = '10000000-0000-0000-0000-000000000003'
const fileA = '20000000-0000-0000-0000-000000000001'
const requestId = '30000000-0000-0000-0000-000000000001'

test('chat: migraciones, RLS, integridad, idempotencia, planes y reutilización sin copiar objetos', async () => {
  const db = new PGlite()
  const q = async (sql, params = []) => (await db.query(sql, params)).rows
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
    for (const name of ['202611150001_projects.sql', '202611150002_chat.sql', '202611150003_chat_titles.sql', '202611160005_chat_timeline.sql'])
      await db.exec(await readFile(new URL(`../migrations/${name}`, import.meta.url), 'utf8'))
    assert.equal((await q('select public from storage.buckets'))[0].public, false)
    assert.equal((await q("select has_function_privilege('anon','public.decide_proposal(uuid,uuid,text)','execute') as allowed"))[0].allowed, false)
    assert.equal((await q("select has_function_privilege('authenticated','public.decide_proposal(uuid,uuid,text)','execute') as allowed"))[0].allowed, true)
    assert.equal((await q("select prosecdef from pg_proc where oid='public.decide_proposal(uuid,uuid,text)'::regprocedure"))[0].prosecdef, false)
    await db.exec(`set role authenticated; set request.jwt.claim.sub='${a}';`)
    await q("insert into public.projects(id,user_id,name,project_type) values ($1,$2,'General A','general'),($3,$2,'Tesis A','thesis')", [projectA, a, projectA2])
    const cid = (await q('select public.create_conversation($1) as id', [projectA]))[0].id
    assert.equal((await q('select current_stage from public.conversations where id=$1', [cid]))[0].current_stage, 'instrument')
    const welcome = await q('select * from public.messages where conversation_id=$1 order by position', [cid])
    assert.equal(welcome.length, 2)
    assert.match(welcome[0].content, /Hola/)
    await q("update public.conversations set title='Mi conversación',title_manual=true where id=$1", [cid])
    const payload = { display: 'No tengo instrumento', action: 'instrument_no' }
    const begin = () => q('select public.begin_chat_turn($1,$2,$3) as status', [cid, requestId, JSON.stringify(payload)])
    assert.equal((await begin())[0].status, 'started')
    assert.equal((await begin())[0].status, 'busy')
    await q('select public.fail_chat_turn($1,$2)', [cid, requestId])
    assert.equal((await begin())[0].status, 'started')
    assert.equal((await q("select * from public.messages where role='user'")).length, 1)
    const result = { stage: 'upload_dataset', content: 'Adjunta datasets.', message_type: 'file_request', title: 'Título automático', metadata: {} }
    await q('select public.finish_chat_turn($1,$2,$3)', [cid, requestId, JSON.stringify(result)])
    assert.equal((await begin())[0].status, 'completed')
    assert.equal((await q('select title from public.conversations where id=$1', [cid]))[0].title, 'Mi conversación')
    assert.equal((await q('select public.begin_chat_turn($1,$2,$3) as status', [cid, requestId, JSON.stringify({ display: 'Otro' })]))[0].status, 'mismatch')

    const path = `${a}/${projectA}/${fileA}/datos.csv`
    await q('insert into storage.objects(bucket_id,name) values ($1,$2)', ['project-files', path])
    await q("insert into public.project_files(id,project_id,uploaded_by,original_name,storage_path,file_type,file_role,file_size) values($1,$2,$3,'datos.csv',$4,'csv','dataset',20)", [fileA, projectA, a, path])
    await q('insert into public.conversation_files(conversation_id,file_id,project_id) values($1,$2,$3)', [cid, fileA, projectA])
    const reused = (await q('select public.create_conversation($1) as id', [projectA]))[0].id
    const reuseState = (await q('select * from public.conversations where id=$1', [reused]))[0]
    assert.equal(reuseState.current_stage, 'reuse')
    assert.deepEqual(reuseState.stage_data.reuse_file_ids, [fileA])
    await q('insert into public.conversation_files(conversation_id,file_id,project_id) values($1,$2,$3)', [reused, fileA, projectA])
    assert.equal((await q('select * from storage.objects')).length, 1)
    assert.equal((await q('select * from public.project_files')).length, 1)
    const other = (await q('select public.create_conversation($1) as id', [projectA2]))[0].id
    await assert.rejects(q('insert into public.conversation_files(conversation_id,file_id,project_id) values($1,$2,$3)', [other, fileA, projectA2]))
    await assert.rejects(q('update public.conversations set project_id=$1 where id=$2', [projectA2, cid]))

    const request2 = '30000000-0000-0000-0000-000000000002'
    await q('select public.begin_chat_turn($1,$2,$3)', [cid, request2, JSON.stringify({ display: 'Explorar' })])
    // La finalización inválida se revierte completa: ni mensaje exitoso ni etapa parcial.
    const before = (await q('select * from public.messages')).length
    await assert.rejects(q('select public.finish_chat_turn($1,$2,$3)', [cid, request2, JSON.stringify({ stage: 'invalid', content: 'No guardar', message_type: 'text' })]))
    assert.equal((await q('select * from public.messages')).length, before)
    const plan = { title: 'Exploración', objective: 'Describir', schema_version: 1, variables: [] }
    await q('select public.finish_chat_turn($1,$2,$3)', [cid, request2, JSON.stringify({ stage: 'proposal', content: 'Confirma el plan', message_type: 'proposal', proposals: [plan] })])
    const proposal = (await q('select id from public.analysis_proposals where conversation_id=$1', [cid]))[0].id
    const linkedMessage = (await q('select m.content from public.analysis_proposals p join public.messages m on m.id=p.source_message_id and m.conversation_id=p.conversation_id where p.id=$1', [proposal]))[0]
    assert.equal(linkedMessage.content, 'Confirma el plan')
    await q("select public.decide_proposal($1,$2,'accepted')", [cid, proposal])
    await q("select public.decide_proposal($1,$2,'accepted')", [cid, proposal])
    assert.equal((await q('select status from public.analysis_proposals where id=$1', [proposal]))[0].status, 'accepted')
    assert.equal((await q('select current_stage from public.conversations where id=$1', [cid]))[0].current_stage, 'ready')
    assert.equal((await q("select count(*)::int as n from public.messages where conversation_id=$1 and content like '%Sesión 03%'", [cid]))[0].n, 0)
    await assert.rejects(q("select public.decide_proposal($1,$2,'rejected')", [cid, proposal]))

    // Aceptación y título forman una sola operación; el plan JSON nunca se reescribe.
    assert.equal((await q('select title from public.conversations where id=$1', [cid]))[0].title, 'Mi conversación')
    for (const [originalTitle, provisional] of [['Nueva conversación', false], ['Exploración provisional', true]]) {
      const titleChat = (await q('select public.create_conversation($1) as id', [projectA]))[0].id
      await q("update public.conversations set title=$2,stage_data=$3 where id=$1", [titleChat, originalTitle, JSON.stringify({title_provisional:provisional})])
      const acceptedPlan = {title:'Análisis integral de mediciones', objective:'Explorar medidas y sus relaciones', schema_version:1}
      const planId = (await q("insert into public.analysis_proposals(conversation_id,title,objective,analysis_plan) values($1,$2,$3,$4) returning id", [titleChat, acceptedPlan.title, acceptedPlan.objective, JSON.stringify(acceptedPlan)]))[0].id
      await q("select public.decide_proposal($1,$2,'accepted')", [titleChat, planId])
      const state = (await q('select title,primary_goal,stage_data from public.conversations where id=$1', [titleChat]))[0]
      assert.equal(state.title, acceptedPlan.title)
      assert.equal(state.primary_goal, acceptedPlan.objective)
      assert.equal(state.stage_data.title_provisional, false)
      assert.deepEqual((await q('select analysis_plan from public.analysis_proposals where id=$1', [planId]))[0].analysis_plan, acceptedPlan)
      const count = (await q('select id from public.messages where conversation_id=$1', [titleChat])).length
      await q("update public.conversations set title='Mi renombrado',title_manual=true where id=$1", [titleChat])
      await q("select public.decide_proposal($1,$2,'accepted')", [titleChat, planId])
      assert.equal((await q('select title from public.conversations where id=$1', [titleChat]))[0].title, 'Mi renombrado')
      assert.equal((await q('select id from public.messages where conversation_id=$1', [titleChat])).length, count)
    }

    await db.exec(`set request.jwt.claim.sub='${b}';`)
    await q("insert into public.projects(id,user_id,name,project_type) values($1,$2,'General B','general')", [projectB, b])
    const cb = (await q('select public.create_conversation($1) as id', [projectB]))[0].id
    for (const table of ['conversations', 'project_files', 'messages', 'analysis_proposals', 'conversation_files', 'chat_requests']) {
      const visible = await q(`select * from public.${table}`)
      if (table === 'conversations') assert.deepEqual(visible.map(r => r.id), [cb])
      else if (table === 'messages') assert.equal(visible.length, 2)
      else assert.equal(visible.length, 0)
    }
    for (const [table, key, id] of [['conversations','id',cid],['messages','conversation_id',cid],['analysis_proposals','id',proposal],['project_files','id',fileA]]) {
      assert.equal((await q(`delete from public.${table} where ${key}=$1 returning *`, [id])).length, 0)
    }
    for (const [table, assignment, key, id] of [['conversations',"title='Intrusión'",'id',cid],['messages',"content='Intrusión'",'conversation_id',cid],
      ['analysis_proposals',"status='rejected'",'id',proposal],['project_files',"original_name='robo.csv'",'id',fileA]]) {
      assert.equal((await q(`update public.${table} set ${assignment} where ${key}=$1 returning *`, [id])).length, 0)
    }
    await assert.rejects(q("insert into public.analysis_proposals(conversation_id,title,objective,analysis_plan) values($1,'Intrusión','Objetivo','{}')", [cid]))
    await assert.rejects(q('select public.create_conversation($1)', [projectA]))
    await assert.rejects(q("insert into public.messages(conversation_id,role,content) values($1,'user','Intrusión')", [cid]))
    await assert.rejects(q('insert into public.conversation_files(conversation_id,file_id,project_id) values($1,$2,$3)', [cb, fileA, projectB]))
    assert.equal((await q('select * from storage.objects')).length, 0)
    assert.equal((await q('delete from storage.objects where name=$1 returning *', [path])).length, 0)
    await assert.rejects(q('insert into storage.objects(bucket_id,name) values ($1,$2)', ['project-files', `${b}/${projectA}/${fileA}/robo.csv`]))
    await assert.rejects(q('insert into storage.objects(bucket_id,name) values ($1,$2)', ['project-files', path]))
    await db.exec('reset role; set role anon;')
    await assert.rejects(q('select * from public.messages'))
    await assert.rejects(q('select public.create_conversation($1)', [projectA]))
    await db.exec(`reset role; set role authenticated; set request.jwt.claim.sub='${a}';`)
    await q('delete from public.conversations where id=$1', [cid])
    assert.equal((await q('select * from public.messages where conversation_id=$1', [cid])).length, 0)
    assert.equal((await q('select * from public.analysis_proposals where conversation_id=$1', [cid])).length, 0)
    assert.equal((await q('select * from public.project_files')).length, 1)
  } finally { await db.close() }
})
