// Puente exclusivamente local para reproducir el backend histórico contra PostgreSQL WASM.
// No conecta a Supabase: Auth/REST emulados, RPC/RLS/transacciones ejecutados por PGlite.
import { PGlite } from '@electric-sql/pglite'
import { readFile } from 'node:fs/promises'
import { createServer } from 'node:http'

const db = new PGlite()
const objects = new Map()
const errors = []
const a = '00000000-0000-0000-0000-000000000001'
const b = '00000000-0000-0000-0000-000000000002'
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
  grant execute on function auth.uid(),storage.foldername(text) to authenticated,anon;
  grant select,insert,delete on storage.objects to authenticated;
  insert into auth.users values ('${a}'),('${b}');
`)
const migrations = ['202611150001_projects.sql','202611150002_chat.sql','202611150003_chat_titles.sql',
  '202611150004_analysis_results.sql','202611160005_chat_timeline.sql','202611160006_research_context.sql',
  '202611170007_assistant_providers.sql']
if (process.argv[2] === '008') migrations.push('202611170008_provider_rollback_guard.sql')
for (const name of migrations)
  await db.exec(await readFile(new URL(`../../migrations/${name}`,import.meta.url),'utf8'))

function identifier(name) {
  if (!/^[a-z_][a-z_0-9]*$/.test(name)) throw new Error('Identificador de prueba inválido')
  return '"' + name + '"'
}
function value(v) { return v !== null && typeof v === 'object' ? JSON.stringify(v) : v }
function selectedField(field) {
  if (!field.includes(':')) return identifier(field)
  const [alias,expression]=field.split(':')
  const match=/^([a-z_][a-z_0-9]*)(->>|->)([a-z_][a-z_0-9]*)$/.exec(expression)
  if (!match) throw new Error('Proyección JSON de prueba no soportada')
  return `${identifier(match[1])}${match[2]}'${match[3]}' as ${identifier(alias)}`
}
async function execute(req,res) {
  const user = req.headers.authorization === 'Bearer synthetic-b' ? b : a
  if (!['Bearer synthetic-a','Bearer synthetic-b'].includes(req.headers.authorization)) {
    res.writeHead(401,{'Content-Type':'application/json'}); res.end('{}'); return
  }
  await db.exec(`reset role; set role authenticated; set request.jwt.claim.sub='${user}';`)
  const chunks = []
  for await (const chunk of req) chunks.push(chunk)
  const raw = Buffer.concat(chunks).toString('utf8')
  const body = raw ? JSON.parse(raw) : {}
  const url = new URL(req.url,'http://127.0.0.1')
  let result
  if (url.pathname === '/auth/v1/user') result = {id:user}
  else if (url.pathname === '/test/query') result = (await db.query(body.sql,body.params || [])).rows
  else if (url.pathname === '/test/errors') result = errors
  else if (url.pathname === '/test/put-object') {
    await db.query("insert into storage.objects(bucket_id,name) values('project-files',$1)",[body.path])
    objects.set(body.path,Buffer.from(body.data,'base64'));result={stored:true}
  } else if (url.pathname.startsWith('/storage/v1/object/authenticated/project-files/')) {
    const path=decodeURIComponent(url.pathname.slice('/storage/v1/object/authenticated/project-files/'.length))
    const visible=(await db.query("select name from storage.objects where bucket_id='project-files' and name=$1",[path])).rows
    if (!visible.length || !objects.has(path)) {
      res.writeHead(403,{'Content-Type':'application/json'});res.end('{}');return
    }
    res.writeHead(200,{'Content-Type':'text/csv'});res.end(objects.get(path));return
  }
  else if (url.pathname.startsWith('/rest/v1/rpc/')) {
    const name = identifier(url.pathname.split('/').at(-1))
    const args = Object.entries(body)
    const params = args.map(([k],i) => identifier(k) + ' => $' + (i+1) + '::' +
      (['p_payload','p_result','p_specification','p_plan'].includes(k) ? 'jsonb' :
        ['p_conversation','p_request','p_project','p_source','p_proposal','p_run','p_token'].includes(k) ? 'uuid' : 'text'))
    result = (await db.query(`select public.${name}(${params.join(',')}) as value`,args.map(([,v])=>value(v)))).rows[0].value
  } else if (url.pathname.startsWith('/rest/v1/')) {
    const table = identifier(url.pathname.split('/').at(-1))
    const params = []
    const where = []
    for (const [key,filter] of url.searchParams) {
      if (['select','order','limit','offset'].includes(key)) continue
      const column = identifier(key)
      if (filter.startsWith('in.(')) {
        const items = filter.slice(4,-1).split(',')
        where.push(`${column} in (${items.map(v=>{params.push(v);return '$'+params.length}).join(',')})`)
      } else {
        const dot = filter.indexOf('.')
        const operator = {eq:'=',lt:'<'}[filter.slice(0,dot)]
        if (!operator) throw new Error('Operador de prueba no soportado')
        params.push(filter.slice(dot+1)); where.push(`${column}${operator}$${params.length}`)
      }
    }
    if (req.method === 'GET') {
      const select = url.searchParams.get('select') || '*'
      let sql = `select ${select === '*' ? '*' : select.split(',').map(selectedField).join(',')} from public.${table}`
      if (where.length) sql += ' where ' + where.join(' and ')
      if (url.searchParams.has('order')) {
        sql += ' order by ' + url.searchParams.get('order').split(',').map(part=>{
          const [key,direction]=part.split('.')
          return identifier(key)+(direction==='desc' ? ' desc' : ' asc')
        }).join(',')
      }
      if (url.searchParams.has('limit')) { params.push(Number(url.searchParams.get('limit')));sql += ' limit $'+params.length }
      if (url.searchParams.has('offset')) { params.push(Number(url.searchParams.get('offset')));sql += ' offset $'+params.length }
      result = (await db.query(sql,params)).rows
    } else if (req.method === 'POST') {
      const keys=Object.keys(body)
      result = (await db.query(`insert into public.${table}(${keys.map(identifier).join(',')}) values(${keys.map((_,i)=>'$'+(i+1)).join(',')}) returning *`,Object.values(body).map(value))).rows
    } else if (req.method === 'PATCH') {
      const keys=Object.keys(body), offset=params.length
      const assignments=keys.map((k,i)=>identifier(k)+'=$'+(offset+i+1))
      result=(await db.query(`update public.${table} set ${assignments.join(',')} where ${where.join(' and ')} returning *`,[...params,...Object.values(body).map(value)])).rows
    } else throw new Error('Método no soportado')
  } else throw new Error('Ruta de prueba desconocida')
  res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(result))
}
let queue=Promise.resolve()
const server=createServer((req,res)=>{
  queue=queue.then(()=>execute(req,res)).catch(error=>{
    errors.push({path:new URL(req.url,'http://127.0.0.1').pathname,code:error.code || 'XX000'})
    res.writeHead(400,{'Content-Type':'application/json'});
    // No cuerpos SQL ni datos: solo el código para que el cliente histórico lo clasifique.
    res.end(JSON.stringify({code:error.code || 'XX000'}))
  })
})
server.listen(0,'127.0.0.1',()=>process.stdout.write(JSON.stringify({port:server.address().port})+'\n'))
