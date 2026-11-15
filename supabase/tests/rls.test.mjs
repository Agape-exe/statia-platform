// PostgreSQL local en WASM; emula solo auth.uid() y auth.users, sin Supabase remoto.
import { PGlite } from '@electric-sql/pglite'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import assert from 'node:assert/strict'

test('migración, CRUD, RLS entre dos usuarios e inmutabilidad', async () => {
  const db = new PGlite()
  try {
    await db.exec(`
      create role anon;
      create role authenticated;
      create schema auth;
      create table auth.users (id uuid primary key);
      create function auth.uid() returns uuid language sql stable as
        $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
      grant usage on schema public, auth to authenticated, anon;
      grant execute on function auth.uid() to authenticated, anon;
      insert into auth.users values
        ('00000000-0000-0000-0000-000000000001'),
        ('00000000-0000-0000-0000-000000000002');
    `)
    await db.exec(await readFile(new URL('../migrations/202611150001_projects.sql', import.meta.url), 'utf8'))
    const a = '00000000-0000-0000-0000-000000000001'
    const b = '00000000-0000-0000-0000-000000000002'
    const id = '10000000-0000-0000-0000-000000000001'
    await db.exec(`set role authenticated; set request.jwt.claim.sub = '${a}';`)
    await db.query('insert into public.projects(id,user_id,name,project_type) values ($1,$2,$3,$4)', [id, a, 'Tesis A', 'thesis'])
    assert.equal((await db.query('select * from public.projects')).rows.length, 1)
    const before = (await db.query('select updated_at from public.projects')).rows[0].updated_at
    await db.query("update public.projects set name = 'Tesis editada', description = 'Descripción' where id=$1", [id])
    const edited = (await db.query('select * from public.projects')).rows[0]
    assert.equal(edited.name, 'Tesis editada')
    assert.ok(new Date(edited.updated_at) >= new Date(before))
    await assert.rejects(db.query('update public.projects set user_id=$1 where id=$2', [b, id]))
    await assert.rejects(db.query("update public.projects set project_type='general' where id=$1", [id]))
    await assert.rejects(db.query("insert into public.projects(user_id,name,project_type) values ($1,'  ','thesis')", [a]))
    await assert.rejects(db.query("insert into public.projects(user_id,name,project_type) values ($1,'Prueba','invalid')", [a]))
    await assert.rejects(db.query("insert into public.projects(user_id,name,project_type,description) values ($1,'Prueba','general',$2)", [a, 'x'.repeat(2001)]))
    await db.exec(`set request.jwt.claim.sub = '${b}';`)
    assert.equal((await db.query('select * from public.projects where id=$1', [id])).rows.length, 0)
    assert.equal((await db.query("update public.projects set name='Intrusión' where id=$1 returning id", [id])).rows.length, 0)
    assert.equal((await db.query('delete from public.projects where id=$1 returning id', [id])).rows.length, 0)
    await assert.rejects(db.query("insert into public.projects(user_id,name,project_type) values ($1,'Intrusión','general')", [a]))
    await db.exec('reset role; set role anon;')
    await assert.rejects(db.query('select * from public.projects'))
    await db.exec(`reset role; set role authenticated; set request.jwt.claim.sub = '${a}';`)
    assert.equal((await db.query('delete from public.projects where id=$1 returning id', [id])).rows.length, 1)
    assert.equal((await db.query('select * from public.projects')).rows.length, 0)
  } finally { await db.close() }
})
