// PostgreSQL local con RLS real; auth.uid() emulado, sin Supabase remoto.
import { PGlite } from '@electric-sql/pglite'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import assert from 'node:assert/strict'

test('Contexto exclusivo de tesis: RLS, contrato, revisión y cascada', async () => {
  const db = new PGlite()
  const a = '00000000-0000-0000-0000-000000000001'
  const b = '00000000-0000-0000-0000-000000000002'
  const thesis = '10000000-0000-0000-0000-000000000001'
  const general = '10000000-0000-0000-0000-000000000002'
  const other = '10000000-0000-0000-0000-000000000003'
  const doc = { schema_version: 1, research_title: 'Investigación A', hypotheses: [], additional_fields: { enfoque: null } }
  try {
    await db.exec(`create role anon; create role authenticated;
      create schema auth; create table auth.users(id uuid primary key);
      create function auth.uid() returns uuid language sql stable as
      $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
      grant usage on schema public,auth to authenticated,anon;
      insert into auth.users values ('${a}'),('${b}');`)
    for (const file of ['202611150001_projects.sql', '202611160006_research_context.sql']) {
      await db.exec(await readFile(new URL(`../migrations/${file}`, import.meta.url), 'utf8'))
    }
    await db.exec(`set role authenticated; set request.jwt.claim.sub='${a}';`)
    await db.query(`insert into public.projects(id,user_id,name,project_type) values ($1,$2,'Tesis','thesis'),($3,$2,'General','general'),($4,$2,'Otra tesis','thesis')`, [thesis, a, general, other])
    const save = (project, document, revision) => db.query('select public.save_research_context($1,$2::jsonb,$3) as saved', [project, JSON.stringify(document), revision])
    assert.equal((await save(thesis, doc, 0)).rows[0].saved.revision, 1)
    await assert.rejects(save(thesis, { ...doc, research_title: 'Obsoleto' }, 0))
    assert.equal((await db.query('select document from public.research_contexts')).rows[0].document.research_title, doc.research_title)
    assert.equal((await save(thesis, { ...doc, research_title: null }, 1)).rows[0].saved.revision, 2)
    for (const invalid of [{schema_version: true}, {schema_version:1, variables:[1]}, {schema_version:1, extra:'x'}, {schema_version:1, hypotheses:null}, {schema_version:1, research_title:'x'.repeat(2001)}]) {
      await assert.rejects(save(thesis, invalid, 2))
    }
    await assert.rejects(save(general, doc, 0))
    await assert.rejects(db.query('insert into public.research_contexts(project_id,document) values($1,$2)', [general, JSON.stringify(doc)]))
    await assert.rejects(db.query('update public.research_contexts set project_id=$1 where project_id=$2', [other, thesis]))
    await db.exec(`set request.jwt.claim.sub='${b}';`)
    assert.equal((await db.query('select * from public.research_contexts')).rows.length, 0)
    await assert.rejects(save(thesis, doc, 2))
    await assert.rejects(db.query('insert into public.research_contexts(project_id,document) values($1,$2)', [other, JSON.stringify(doc)]))
    assert.equal((await db.query('update public.research_contexts set document=$1 where project_id=$2 returning *', [JSON.stringify(doc), thesis])).rows.length, 0)
    await assert.rejects(db.query('delete from public.research_contexts where project_id=$1', [thesis]))
    await db.exec('reset role; set role anon;')
    await assert.rejects(db.query('select * from public.research_contexts'))
    await assert.rejects(save(thesis, doc, 0))
    await db.exec(`reset role; set role authenticated; set request.jwt.claim.sub='${a}';`)
    await db.query('delete from public.projects where id=$1', [thesis])
    assert.equal((await db.query('select * from public.research_contexts')).rows.length, 0)
  } finally { await db.close() }
})
