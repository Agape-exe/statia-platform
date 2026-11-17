-- Solo lectura. Ejecutar manualmente en el proyecto REAL después de instalar 007 y 008.
-- No contiene datos de usuarios. SQL Editor no demuestra por sí mismo RLS por usuario.
select public.provider_rollback_safety() as proteccion_008; -- Debe devolver 1.

select p.proname, pg_get_function_identity_arguments(p.oid) as argumentos,
    p.prosecdef as security_definer, p.proconfig,
    has_function_privilege('authenticated',p.oid,'execute') as authenticated_puede_ejecutar,
    has_function_privilege('anon',p.oid,'execute') as anon_puede_ejecutar,
    md5(pg_get_functiondef(p.oid)) as hash_definicion
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where n.nspname='public' and p.proname in (
    'begin_chat_turn','begin_provider_chat_turn','finish_chat_turn',
    'provider_rollback_safety','protect_chat_request_binding'
)
order by p.proname;
-- Las cinco funciones: definer=false, authenticated=true, anon=false, search_path vacío.

select c.relname, c.relrowsecurity
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relname in ('conversations','messages','chat_requests');
-- Las tres tablas deben conservar RLS habilitado.

select tablename, policyname, roles, cmd
from pg_policies where schemaname='public'
    and tablename in ('conversations','messages','chat_requests')
order by tablename,policyname;

select t.tgname,t.tgenabled
from pg_trigger t join pg_class c on c.oid=t.tgrelid
join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and t.tgname in ('conversation_provider_guard','chat_request_binding_guard');
-- Ambos triggers deben existir y estar habilitados.
