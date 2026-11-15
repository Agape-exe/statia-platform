begin;

create table public.conversations (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    title text not null default 'Nueva conversación' check (char_length(btrim(title)) between 1 and 120),
    title_manual boolean not null default false,
    primary_goal text check (char_length(primary_goal) <= 2000),
    current_stage text not null default 'instrument' check (current_stage in
        ('reuse','instrument','upload_instrument','upload_dataset','understanding','clarification','goal','proposal','ready')),
    stage_data jsonb not null default '{}',
    active_request_id uuid,
    active_since timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (id, project_id)
);
create table public.messages (
    id uuid primary key default gen_random_uuid(),
    position bigint generated always as identity unique,
    conversation_id uuid not null references public.conversations(id) on delete cascade,
    role text not null check (role in ('user','assistant','system')),
    content text not null check (char_length(content) between 1 and 20000),
    message_type text not null default 'text' check (message_type in
        ('text','question','file_request','dataset_summary','proposal','confirmation','recoverable_error','event')),
    metadata jsonb not null default '{}',
    created_at timestamptz not null default now()
);
create table public.project_files (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.projects(id) on delete cascade,
    uploaded_by uuid not null references auth.users(id),
    original_name text not null check (char_length(original_name) between 1 and 240),
    storage_path text not null unique,
    file_type text not null check (file_type in ('csv','xlsx','json','pdf')),
    file_role text not null check (file_role in ('dataset','instrument')),
    file_size bigint not null check (file_size > 0 and file_size <= 104857600),
    metadata jsonb not null default '{}',
    created_at timestamptz not null default now(),
    unique (id, project_id),
    check ((file_role = 'instrument') = (file_type = 'pdf')),
    check (storage_path like uploaded_by::text || '/' || project_id::text || '/' || id::text || '/%'
           and storage_path !~ '(^|/)\.\.(/|$)')
);
create table public.conversation_files (
    conversation_id uuid not null,
    file_id uuid not null,
    project_id uuid not null,
    created_at timestamptz not null default now(),
    primary key (conversation_id, file_id),
    foreign key (conversation_id, project_id) references public.conversations(id, project_id) on delete cascade,
    foreign key (file_id, project_id) references public.project_files(id, project_id) on delete cascade
);
create table public.analysis_proposals (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references public.conversations(id) on delete cascade,
    title text not null check (char_length(title) between 1 and 160),
    objective text not null check (char_length(objective) between 1 and 2000),
    analysis_plan jsonb not null check (jsonb_typeof(analysis_plan) = 'object'),
    status text not null default 'proposed' check (status in ('proposed','accepted','rejected')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
-- Registro durable de idempotencia y exclusión de turnos, sin infraestructura adicional.
create table public.chat_requests (
    conversation_id uuid not null references public.conversations(id) on delete cascade,
    request_id uuid not null,
    payload jsonb not null,
    status text not null check (status in ('pending','completed','failed')),
    created_at timestamptz not null default now(),
    primary key (conversation_id, request_id)
);
create index conversations_project_updated_idx on public.conversations(project_id, updated_at desc);
create index messages_conversation_created_idx on public.messages(conversation_id, position);
create index files_project_created_idx on public.project_files(project_id, created_at desc);
create index conversation_files_file_idx on public.conversation_files(file_id);
create index proposals_conversation_idx on public.analysis_proposals(conversation_id, created_at);

create function public.touch_chat_row() returns trigger language plpgsql set search_path = '' as $$
begin
    if new.id is distinct from old.id or new.created_at is distinct from old.created_at then
        raise exception 'La identidad y fecha inicial son inmutables';
    end if;
    new.updated_at = now();
    return new;
end;
$$;
create trigger conversations_touch before update on public.conversations for each row execute function public.touch_chat_row();
create trigger proposals_touch before update on public.analysis_proposals for each row execute function public.touch_chat_row();

alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.project_files enable row level security;
alter table public.conversation_files enable row level security;
alter table public.analysis_proposals enable row level security;
alter table public.chat_requests enable row level security;

create policy conversations_owner on public.conversations for all to authenticated
using (exists(select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())))
with check (exists(select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())));
create policy files_owner on public.project_files for all to authenticated
using (exists(select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())))
with check (uploaded_by = (select auth.uid()) and exists(select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())));
create policy links_owner on public.conversation_files for all to authenticated
using (exists(select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())))
with check (exists(select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid())));
create policy messages_owner on public.messages for all to authenticated
using (exists(select 1 from public.conversations c where c.id = conversation_id))
with check (exists(select 1 from public.conversations c where c.id = conversation_id));
create policy proposals_owner on public.analysis_proposals for all to authenticated
using (exists(select 1 from public.conversations c where c.id = conversation_id))
with check (exists(select 1 from public.conversations c where c.id = conversation_id));
create policy requests_owner on public.chat_requests for all to authenticated
using (exists(select 1 from public.conversations c where c.id = conversation_id))
with check (exists(select 1 from public.conversations c where c.id = conversation_id));
revoke all on public.conversations, public.messages, public.project_files, public.conversation_files,
    public.analysis_proposals, public.chat_requests from anon, authenticated;
grant select, insert, update, delete on public.conversations, public.messages, public.project_files,
    public.conversation_files, public.analysis_proposals, public.chat_requests to authenticated;
grant usage on sequence public.messages_position_seq to authenticated;

create function public.protect_chat_parent() returns trigger language plpgsql set search_path = '' as $$
begin
    if (to_jsonb(new)->'project_id') is distinct from (to_jsonb(old)->'project_id')
       or (to_jsonb(new)->'conversation_id') is distinct from (to_jsonb(old)->'conversation_id')
       or (to_jsonb(new)->'uploaded_by') is distinct from (to_jsonb(old)->'uploaded_by')
       or (to_jsonb(new)->'storage_path') is distinct from (to_jsonb(old)->'storage_path') then
        raise exception 'La pertenencia y el almacenamiento son inmutables';
    end if;
    return new;
end;
$$;
create trigger conversations_parent before update on public.conversations for each row execute function public.protect_chat_parent();
create trigger files_parent before update on public.project_files for each row execute function public.protect_chat_parent();
create trigger messages_parent before update on public.messages for each row execute function public.protect_chat_parent();
create trigger proposals_parent before update on public.analysis_proposals for each row execute function public.protect_chat_parent();
create trigger links_parent before update on public.conversation_files for each row execute function public.protect_chat_parent();

create function public.create_conversation(p_project uuid, p_source uuid default null) returns uuid
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
    (v_id,'assistant','Hola, soy tu asistente estadístico. Puedo ayudarte a comprender tus datos y preparar análisis. La ejecución e interpretación de resultados se habilitará en la Sesión 03.','text'),
    (v_id,'assistant',case when v_source is null then '¿Tus datos están relacionados con algún instrumento de recolección de información?'
        else '¿Deseas reutilizar los archivos de la conversación más reciente que tiene archivos o cargar archivos nuevos?' end,'question');
    return v_id;
end;
$$;

create function public.begin_chat_turn(p_conversation uuid, p_request uuid, p_payload jsonb) returns text
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

create function public.finish_chat_turn(p_conversation uuid, p_request uuid, p_result jsonb) returns void
language plpgsql security invoker set search_path = '' as $$
declare c public.conversations; plan jsonb; file_id text;
begin
    select * into c from public.conversations where id = p_conversation for update;
    if not found or c.active_request_id is distinct from p_request then raise exception 'Turno no activo'; end if;
    for file_id in select jsonb_array_elements_text(coalesce(p_result->'link_file_ids','[]')) loop
        insert into public.conversation_files(conversation_id,file_id,project_id) values(p_conversation,file_id::uuid,c.project_id)
        on conflict do nothing;
    end loop;
    for plan in select jsonb_array_elements(coalesce(p_result->'proposals','[]')) loop
        insert into public.analysis_proposals(conversation_id,title,objective,analysis_plan)
        values(p_conversation,plan->>'title',plan->>'objective',plan);
    end loop;
    insert into public.messages(conversation_id,role,content,message_type,metadata)
    values(p_conversation,'assistant',p_result->>'content',p_result->>'message_type',coalesce(p_result->'metadata','{}'));
    update public.conversations set current_stage = p_result->>'stage',
        stage_data = coalesce(p_result->'stage_data',stage_data),
        primary_goal = coalesce(primary_goal,p_result->>'goal'),
        title = case when not title_manual then coalesce(p_result->>'title',title) else title end,
        active_request_id = null, active_since = null where id = p_conversation;
    update public.chat_requests set status = 'completed' where conversation_id = p_conversation and request_id = p_request;
end;
$$;
create function public.fail_chat_turn(p_conversation uuid, p_request uuid) returns void
language plpgsql security invoker set search_path = '' as $$
begin
    update public.conversations set active_request_id = null, active_since = null
    where id = p_conversation and active_request_id = p_request;
    if found then update public.chat_requests set status = 'failed' where conversation_id = p_conversation and request_id = p_request; end if;
end;
$$;

create function public.decide_proposal(p_conversation uuid, p_proposal uuid, p_status text) returns void
language plpgsql security invoker set search_path = '' as $$
declare v_status text;
begin
    perform 1 from public.conversations where id = p_conversation and active_request_id is null for update;
    if not found then raise exception 'Conversación no disponible u ocupada'; end if;
    if p_status not in ('accepted','rejected') then raise exception 'Decisión inválida'; end if;
    select status into v_status from public.analysis_proposals where id = p_proposal and conversation_id = p_conversation for update;
    if not found then raise exception 'Propuesta no disponible'; end if;
    if v_status = p_status then return; end if;
    if v_status <> 'proposed' then raise exception 'La propuesta ya fue decidida'; end if;
    update public.analysis_proposals set status = p_status where id = p_proposal;
    update public.conversations set current_stage = case when p_status = 'accepted' or exists(
        select 1 from public.analysis_proposals where conversation_id = p_conversation and status = 'accepted') then 'ready' else 'goal' end where id = p_conversation;
    insert into public.messages(conversation_id,role,content,message_type,metadata) values
    (p_conversation,'system',case when p_status = 'accepted' then 'Plan aceptado y preparado para ejecución en la Sesión 03. No se han calculado resultados inferenciales.'
        else 'Propuesta rechazada. Puedes explicar qué deseas cambiar y solicitar otra.' end,'event',jsonb_build_object('proposal_id',p_proposal,'status',p_status));
end;
$$;

revoke all on function public.create_conversation(uuid,uuid), public.begin_chat_turn(uuid,uuid,jsonb),
    public.finish_chat_turn(uuid,uuid,jsonb), public.fail_chat_turn(uuid,uuid), public.decide_proposal(uuid,uuid,text) from public, anon;
grant execute on function public.create_conversation(uuid,uuid), public.begin_chat_turn(uuid,uuid,jsonb),
    public.finish_chat_turn(uuid,uuid,jsonb), public.fail_chat_turn(uuid,uuid), public.decide_proposal(uuid,uuid,text) to authenticated;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values ('project-files','project-files',false,10485760,array[
    'text/csv','application/json','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/pdf'])
on conflict(id) do update set public = false, file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;
create policy project_files_storage_select on storage.objects for select to authenticated using (
    bucket_id = 'project-files' and (storage.foldername(name))[1] = (select auth.uid())::text
    and exists(select 1 from public.projects p where p.id::text = (storage.foldername(objects.name))[2] and p.user_id = (select auth.uid())));
create policy project_files_storage_insert on storage.objects for insert to authenticated with check (
    bucket_id = 'project-files' and (storage.foldername(name))[1] = (select auth.uid())::text
    and array_length(storage.foldername(name),1) = 3
    and exists(select 1 from public.projects p where p.id::text = (storage.foldername(objects.name))[2] and p.user_id = (select auth.uid())));
-- Permite limpiar objetos propios incluso después de eliminar el proyecto.
create policy project_files_storage_delete on storage.objects for delete to authenticated using (
    bucket_id = 'project-files' and (storage.foldername(name))[1] = (select auth.uid())::text);

commit;
