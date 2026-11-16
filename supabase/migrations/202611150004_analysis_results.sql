begin;

alter table public.analysis_proposals add constraint proposals_id_conversation_key unique (id, conversation_id);

create table public.analysis_runs (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null,
    conversation_id uuid not null,
    proposal_id uuid not null,
    request_id uuid not null,
    lease_token uuid not null default gen_random_uuid(),
    title text not null check (char_length(title) between 1 and 160),
    specification jsonb not null check (jsonb_typeof(specification) = 'object'),
    plan_snapshot jsonb not null check (jsonb_typeof(plan_snapshot) = 'object'),
    status text not null default 'running' check (status in ('running','completed','partial','failed')),
    result jsonb check (result is null or jsonb_typeof(result) = 'object'),
    error text check (char_length(error) <= 1500),
    artifact_count integer not null default 0 check (artifact_count >= 0),
    created_at timestamptz not null default now(),
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    unique (id, project_id),
    unique (conversation_id, request_id),
    foreign key (conversation_id, project_id) references public.conversations(id, project_id) on delete cascade,
    foreign key (proposal_id, conversation_id) references public.analysis_proposals(id, conversation_id) on delete cascade,
    check ((status = 'running' and finished_at is null and result is null) or
           (status in ('completed','partial') and finished_at is not null and result is not null) or
           (status = 'failed' and finished_at is not null)),
    check (result is null or (result ?& array['status','run_id','project_id','conversation_id','proposal_id','specification','plan_snapshot','summary']
           and result->>'status' = status and result->>'run_id' = id::text
           and result->>'project_id' = project_id::text and result->>'conversation_id' = conversation_id::text
           and result->>'proposal_id' = proposal_id::text))
);
create unique index analysis_one_running_conversation on public.analysis_runs(conversation_id) where status = 'running';
create index analysis_project_created on public.analysis_runs(project_id, created_at desc, id);
create index analysis_conversation_created on public.analysis_runs(conversation_id, created_at desc, id);

create table public.analysis_artifacts (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null,
    project_id uuid not null,
    name text not null check (char_length(name) between 1 and 240 and name !~ '(^/|(^|/)\.\.(/|$)|\\)'),
    storage_path text not null unique,
    mime_type text not null check (mime_type in ('text/csv','image/png','application/json','text/markdown','application/zip')),
    size_bytes bigint not null check (size_bytes > 0 and size_bytes <= 25165824),
    sha256 text not null check (sha256 ~ '^[a-f0-9]{64}$'),
    created_at timestamptz not null default now(),
    foreign key (run_id, project_id) references public.analysis_runs(id, project_id) on delete cascade,
    unique (run_id, name),
    check (storage_path like '%/' || project_id::text || '/' || run_id::text || '/%'
           and storage_path !~ '(^|/)\.\.(/|$)')
);

alter table public.analysis_runs enable row level security;
alter table public.analysis_artifacts enable row level security;
create policy analysis_runs_owner on public.analysis_runs for all to authenticated
using (exists(select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())))
with check (exists(select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())));
create policy analysis_artifacts_owner on public.analysis_artifacts for all to authenticated
using (exists(select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())))
with check (exists(select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())));
revoke all on public.analysis_runs, public.analysis_artifacts from anon, authenticated;
grant select, insert, update, delete on public.analysis_runs, public.analysis_artifacts to authenticated;

create function public.protect_analysis_run() returns trigger language plpgsql set search_path = '' as $$
begin
    if new.id is distinct from old.id or new.project_id is distinct from old.project_id
       or new.conversation_id is distinct from old.conversation_id or new.proposal_id is distinct from old.proposal_id
       or new.request_id is distinct from old.request_id or new.specification is distinct from old.specification
       or new.plan_snapshot is distinct from old.plan_snapshot or new.created_at is distinct from old.created_at then
        raise exception 'La identidad y las decisiones de la ejecución son inmutables';
    end if;
    return new;
end;
$$;
create trigger analysis_run_identity before update on public.analysis_runs for each row execute function public.protect_analysis_run();
create function public.protect_analysis_artifact() returns trigger language plpgsql set search_path = '' as $$
begin
    if new.id is distinct from old.id or new.run_id is distinct from old.run_id or new.project_id is distinct from old.project_id
       or new.storage_path is distinct from old.storage_path or new.name is distinct from old.name then
        raise exception 'La pertenencia y ruta del artefacto son inmutables';
    end if;
    return new;
end;
$$;
create trigger analysis_artifact_parent before update on public.analysis_artifacts for each row execute function public.protect_analysis_artifact();

insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
values ('analysis-results','analysis-results',false,25165824,
        array['text/csv','image/png','application/json','text/markdown','application/zip']);
create policy results_storage_read on storage.objects for select to authenticated
using (bucket_id = 'analysis-results' and (storage.foldername(name))[1] = (select auth.uid())::text
       and exists(select 1 from public.analysis_runs r where r.project_id::text = (storage.foldername(name))[2]
                  and r.id::text = (storage.foldername(name))[3]));
create policy results_storage_insert on storage.objects for insert to authenticated
with check (bucket_id = 'analysis-results' and (storage.foldername(name))[1] = (select auth.uid())::text
       and name !~ '(^|/)\.\.(/|$)'
       and exists(select 1 from public.analysis_runs r where r.project_id::text = (storage.foldername(name))[2]
                  and r.id::text = (storage.foldername(name))[3] and r.lease_token::text = (storage.foldername(name))[4]
                  and r.status = 'running'));
create policy results_storage_delete on storage.objects for delete to authenticated
using (bucket_id = 'analysis-results' and (storage.foldername(name))[1] = (select auth.uid())::text);

create function public.begin_analysis_run(p_conversation uuid, p_proposal uuid, p_request uuid, p_specification jsonb, p_plan jsonb)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare c public.conversations; p public.analysis_proposals; r public.analysis_runs;
begin
    select * into c from public.conversations where id = p_conversation for update;
    if not found then raise exception 'Conversación no disponible'; end if;
    select * into p from public.analysis_proposals where id = p_proposal and conversation_id = c.id;
    if not found or p.status <> 'accepted' or p.analysis_plan <> p_plan then raise exception 'El plan aceptado cambió o no está disponible'; end if;
    -- Una caída nunca queda simulada como trabajo durable en segundo plano.
    update public.analysis_runs set status='failed', finished_at=now(), error='Ejecución interrumpida o vencida. Puedes reintentar.'
    where conversation_id=c.id and status='running' and started_at < now() - interval '180 seconds';
    select * into r from public.analysis_runs where conversation_id=c.id and request_id=p_request;
    if found then
        if r.proposal_id <> p_proposal or r.specification <> p_specification or r.plan_snapshot <> p_plan then
            return jsonb_build_object('status','mismatch');
        end if;
        if r.result is not null or r.status in ('completed','partial') then
            return jsonb_build_object('status','replayed','run_id',r.id);
        end if;
    end if;
    if c.active_request_id is not null and c.active_since > now() - interval '180 seconds'
       or exists(select 1 from public.analysis_runs where conversation_id=c.id and status='running') then
        return jsonb_build_object('status','busy');
    end if;
    if r.id is null then
        insert into public.analysis_runs(project_id,conversation_id,proposal_id,request_id,title,specification,plan_snapshot)
        values(c.project_id,c.id,p.id,p_request,p.title,p_specification,p_plan) returning * into r;
    else
        update public.analysis_runs set status='running',started_at=now(),finished_at=null,error=null,lease_token=gen_random_uuid()
        where id=r.id returning * into r;
    end if;
    return jsonb_build_object('status','started','run_id',r.id,'lease_token',r.lease_token);
end;
$$;

create function public.finish_analysis_run(p_run uuid, p_token uuid, p_result jsonb, p_artifacts jsonb)
returns void language plpgsql security invoker set search_path = '' as $$
declare r public.analysis_runs; item jsonb; v_status text; v_conversation uuid;
begin
    -- Mismo orden de bloqueos que begin_analysis_run: conversación, después ejecución.
    select conversation_id into v_conversation from public.analysis_runs where id=p_run;
    if not found then raise exception 'Ejecución no disponible'; end if;
    perform 1 from public.conversations where id=v_conversation for update;
    select * into r from public.analysis_runs where id=p_run for update;
    if not found or r.status <> 'running' or r.lease_token <> p_token then raise exception 'La concesión de ejecución ya no es válida'; end if;
    v_status := p_result->>'status';
    if v_status is null or v_status not in ('completed','partial','failed') or p_result->'specification' is distinct from r.specification
       or p_result->'plan_snapshot' is distinct from r.plan_snapshot then raise exception 'Resultado incoherente con las decisiones'; end if;
    for item in select value from jsonb_array_elements(p_artifacts) loop
        if item->>'storage_path' <> auth.uid()::text || '/' || r.project_id::text || '/' || r.id::text || '/' || p_token::text || '/' || (item->>'name')
           or not exists(select 1 from storage.objects where bucket_id='analysis-results' and name=item->>'storage_path') then
            raise exception 'Artefacto privado ausente o con ruta inválida';
        end if;
        insert into public.analysis_artifacts(run_id,project_id,name,storage_path,mime_type,size_bytes,sha256)
        values(r.id,r.project_id,item->>'name',item->>'storage_path',item->>'mime_type',(item->>'size_bytes')::bigint,item->>'sha256');
    end loop;
    if not exists(select 1 from public.analysis_artifacts where run_id=r.id and name='resultados_analisis.zip') then
        raise exception 'Falta el ZIP de la ejecución';
    end if;
    update public.analysis_runs set status=v_status,result=p_result,finished_at=now(),
        artifact_count=jsonb_array_length(p_artifacts),error=case when v_status='failed' then 'Ningún componente pudo ejecutarse; consulta los motivos.' else null end
    where id=r.id;
    insert into public.messages(conversation_id,role,content,message_type,metadata)
    values(r.conversation_id,'assistant',p_result->>'summary','event',jsonb_build_object('analysis_run_id',r.id));
    update public.conversations set updated_at=now() where id=r.conversation_id;
end;
$$;

create function public.fail_analysis_run(p_run uuid, p_token uuid, p_error text)
returns void language plpgsql security invoker set search_path = '' as $$
begin
    update public.analysis_runs set status='failed', finished_at=now(), error=left(p_error,1500)
    where id=p_run and lease_token=p_token and status='running';
end;
$$;
revoke all on function public.begin_analysis_run(uuid,uuid,uuid,jsonb,jsonb), public.finish_analysis_run(uuid,uuid,jsonb,jsonb), public.fail_analysis_run(uuid,uuid,text) from public, anon;
grant execute on function public.begin_analysis_run(uuid,uuid,uuid,jsonb,jsonb), public.finish_analysis_run(uuid,uuid,jsonb,jsonb), public.fail_analysis_run(uuid,uuid,text) to authenticated;

-- Serializa turnos y cálculos mediante el mismo bloqueo de conversación.
create or replace function public.begin_chat_turn(p_conversation uuid, p_request uuid, p_payload jsonb) returns text
language plpgsql security invoker set search_path = '' as $$
declare c public.conversations; r public.chat_requests;
begin
    select * into c from public.conversations where id = p_conversation for update;
    if not found then raise exception 'Conversación no disponible'; end if;
    select * into r from public.chat_requests where conversation_id = p_conversation and request_id = p_request;
    if found then
        if r.payload <> p_payload then return 'mismatch'; end if;
        if r.status = 'completed' then return 'completed'; end if;
    end if;
    if exists(select 1 from public.analysis_runs where conversation_id=c.id and status='running' and started_at > now() - interval '180 seconds') then return 'busy'; end if;
    if c.active_request_id is not null and c.active_since > now() - interval '180 seconds' then return 'busy'; end if;
    if c.active_request_id is not null then
        update public.chat_requests set status = 'failed' where conversation_id = p_conversation and request_id = c.active_request_id;
    end if;
    insert into public.chat_requests(conversation_id,request_id,payload,status) values(p_conversation,p_request,p_payload,'pending')
    on conflict(conversation_id,request_id) do update set status = 'pending';
    if r.request_id is null then
        insert into public.messages(conversation_id,role,content,metadata) values
        (p_conversation,'user',p_payload->>'display',jsonb_build_object('request_id',p_request));
    end if;
    update public.conversations set active_request_id = p_request, active_since = now() where id = p_conversation;
    return 'started';
end;
$$;


create or replace function public.create_conversation(p_project uuid, p_source uuid default null) returns uuid
language plpgsql security invoker set search_path = '' as $$
declare v_id uuid; v_source uuid; v_files jsonb; v_goal text; v_title text;
begin
    if p_source is not null then
        select stage_data->'goal_change'->>'goal', stage_data->'goal_change'->>'title' into v_goal, v_title
        from public.conversations where id = p_source and project_id = p_project and stage_data->'goal_change' <> 'null'::jsonb;
        if not found then raise exception 'No hay cambio de finalidad confirmado'; end if;
    end if;
    select c.id into v_source from public.conversations c
    where c.project_id = p_project and exists(select 1 from public.conversation_files f where f.conversation_id = c.id)
    order by c.updated_at desc limit 1;
    select coalesce(jsonb_agg(f.file_id), '[]'::jsonb) into v_files
    from public.conversation_files f where f.conversation_id = v_source;
    insert into public.conversations(project_id,title,primary_goal,current_stage,stage_data)
    values (p_project,coalesce(v_title,'Nueva conversación'),v_goal,case when v_source is null then 'instrument' else 'reuse' end,
        jsonb_build_object('reuse_file_ids',v_files)) returning id into v_id;
    insert into public.messages(conversation_id,role,content,message_type) values
    (v_id,'assistant','Hola, soy tu asistente estadístico. Puedo ayudarte a comprender tus datos y preparar análisis. Después de aceptar un plan puedes revisar las decisiones, ejecutar análisis con Python y consultar los resultados.','text'),
    (v_id,'assistant',case when v_source is null then '¿Tus datos están relacionados con algún instrumento de recolección de información?'
        else '¿Deseas reutilizar los archivos de la conversación más reciente que tiene archivos o cargar archivos nuevos?' end,'question');
    return v_id;
end;
$$;


commit;
