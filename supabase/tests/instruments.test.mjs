// PostgreSQL/RLS real en WASM; Auth y Storage emulados, sin servicios remotos.
import { PGlite } from '@electric-sql/pglite'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import assert from 'node:assert/strict'

test('DOCX: migración aditiva, roles, bucket privado, reutilización y aislamiento', async () => {
  const db = new PGlite()
  const q = async (sql, args = []) => (await db.query(sql, args)).rows
  const a = '00000000-0000-4000-8000-000000000001'
  const b = '00000000-0000-4000-8000-000000000002'
  const projects = ['10000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000002']
  const mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
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
    for (const name of ['202611150001_projects.sql', '202611150002_chat.sql'])
      await db.exec(await readFile(new URL(`../migrations/${name}`, import.meta.url), 'utf8'))
    const before = (await q("select * from storage.buckets where id='project-files'"))[0]
    await db.exec(await readFile(new URL('../migrations/202611200009_instrument_docx.sql', import.meta.url), 'utf8'))
    const after = (await q("select * from storage.buckets where id='project-files'"))[0]
    assert.equal(after.public, false)
    assert.equal(after.file_size_limit, before.file_size_limit)
    assert.deepEqual(after.allowed_mime_types, [...before.allowed_mime_types, mime])
    await db.exec(`set role authenticated; set request.jwt.claim.sub='${a}';`)
    for (const [index, type] of ['general', 'thesis'].entries()) {
      const project = projects[index]
      await q('insert into public.projects(id,user_id,name,project_type) values($1,$2,$3,$4)', [project, a, `Proyecto ${type}`, type])
      const c1 = (await q('select public.create_conversation($1) as id', [project]))[0].id
      for (const [format, suffix] of [['docx', '1'], ['pdf', '2']]) {
        const fid = `20000000-0000-4000-8000-0000000000${index}${suffix}`
        const path = `${a}/${project}/${fid}/escala.${format}`
        await q("insert into storage.objects(bucket_id,name) values('project-files',$1)", [path])
        await q('insert into public.project_files(id,project_id,uploaded_by,original_name,storage_path,file_type,file_role,file_size) values($1,$2,$3,$4,$5,$6,$7,100)', [fid, project, a, `escala.${format}`, path, format, 'instrument'])
        await assert.rejects(q("update public.project_files set file_role='dataset' where id=$1", [fid]))
        await q('insert into public.conversation_files(conversation_id,file_id,project_id) values($1,$2,$3)', [c1, fid, project])
        const c2 = (await q('select public.create_conversation($1) as id', [project]))[0].id
        await q('insert into public.conversation_files(conversation_id,file_id,project_id) values($1,$2,$3)', [c2, fid, project])
      }
    }
    assert.equal((await q('select * from storage.objects')).length, 4)
    assert.equal((await q('select * from public.conversation_files')).length, 8)
    await assert.rejects(q("update public.project_files set file_type='doc'"))
    await db.exec(`set request.jwt.claim.sub='${b}';`)
    assert.equal((await q('select * from public.project_files')).length, 0)
    assert.equal((await q('select * from storage.objects')).length, 0)
    assert.equal((await q("update public.project_files set original_name='intrusion.docx' returning *")).length, 0)
    await db.exec('reset role; set role anon;')
    await assert.rejects(q('select * from public.project_files'))
  } finally { await db.close() }
})
