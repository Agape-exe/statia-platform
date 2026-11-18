begin;

do $$
begin
    if to_regprocedure('public.begin_provider_chat_turn(uuid,uuid,jsonb,text,text)') is null
        or to_regclass('public.analysis_runs') is null
        or not exists(select 1 from information_schema.columns where table_schema='public'
            and table_name='analysis_proposals' and column_name='source_message_id')
        or (select count(*) from information_schema.columns where table_schema='public' and
            ((table_name='conversations' and column_name='assistant_provider') or
             (table_name='chat_requests' and column_name in ('provider','model')))) <> 3 then
        raise exception 'Aplicar y verificar la migración 007 antes de 008';
    end if;
end;
$$;

-- Corrección aditiva de 007. No tocar datos ni reescribir las migraciones anteriores.
-- Adquisiciones separadas: el RPC multiproveedor NO delega al RPC legacy restringido.
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
    -- Una versión anterior no comunica el modelo: solo se permiten turnos Gemini sin vínculo conocido.
    if c.assistant_provider <> 'gemini' or (r.request_id is not null and (r.provider <> 'gemini' or r.model is not null)) then
        raise exception 'Este turno requiere un backend compatible con el proveedor y modelo registrados';
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

create or replace function public.begin_provider_chat_turn(p_conversation uuid, p_request uuid, p_payload jsonb, p_provider text, p_model text) returns text
language plpgsql security invoker set search_path = '' as $$
declare c public.conversations; r public.chat_requests;
begin
    select * into c from public.conversations where id = p_conversation for update;
    if not found then raise exception 'Conversación no disponible'; end if;
    select * into r from public.chat_requests where conversation_id = p_conversation and request_id = p_request;
    if found then
        if r.payload <> p_payload then return 'mismatch'; end if;
        if r.status = 'completed' then return 'completed'; end if;
        if r.provider is distinct from p_provider or (r.model is not null and r.model is distinct from p_model) then return 'provider_changed'; end if;
    end if;
    if p_provider is null or p_provider not in ('gemini','openai') or c.assistant_provider is distinct from p_provider then return 'provider_changed'; end if;
    if p_model is null or length(p_model)=0 or length(p_model)>120 or (p_provider='openai' and p_model <> 'gpt-6.1-terra') then raise exception 'Modelo no permitido'; end if;
    if exists(select 1 from public.analysis_runs where conversation_id=c.id and status='running' and started_at > now() - interval '180 seconds') then return 'busy'; end if;
    if c.active_request_id is not null and c.active_since > now() - interval '180 seconds' then return 'busy'; end if;
    if c.active_request_id is not null then
        update public.chat_requests set status = 'failed' where conversation_id = p_conversation and request_id = c.active_request_id;
    end if;
    insert into public.chat_requests(conversation_id,request_id,payload,status,provider,model) values(p_conversation,p_request,p_payload,'pending',p_provider,p_model)
    on conflict(conversation_id,request_id) do update set status = 'pending', model = excluded.model;
    if r.request_id is null then
        insert into public.messages(conversation_id,role,content,metadata) values
        (p_conversation,'user',p_payload->>'display',jsonb_build_object('request_id',p_request));
    end if;
    update public.conversations set active_request_id = p_request, active_since = now() where id = p_conversation;
    return 'started';
end;
$$;

-- La finalización conserva la transacción de 005 y exige procedencia para turnos vinculados.
create or replace function public.finish_chat_turn(p_conversation uuid, p_request uuid, p_result jsonb) returns void
language plpgsql security invoker set search_path = '' as $$
declare c public.conversations; plan jsonb; file_id text; message_id uuid; r public.chat_requests;
begin
    select * into c from public.conversations where id = p_conversation for update;
    if not found or c.active_request_id is distinct from p_request then raise exception 'Turno no activo'; end if;
    select * into r from public.chat_requests where conversation_id=p_conversation and request_id=p_request;
    if r.model is not null and not (
        coalesce(p_result->'metadata'->'generation'->>'source','')='deterministic'
        or (p_result->'metadata'->'generation'->>'provider' is not distinct from r.provider
            and p_result->'metadata'->'generation'->>'model' is not distinct from r.model)
    ) then raise exception 'La respuesta no coincide con la procedencia de la solicitud'; end if;

    for file_id in select jsonb_array_elements_text(coalesce(p_result->'link_file_ids','[]')) loop
        insert into public.conversation_files(conversation_id,file_id,project_id) values(p_conversation,file_id::uuid,c.project_id)
        on conflict do nothing;
    end loop;
    insert into public.messages(conversation_id,role,content,message_type,metadata)
    values(p_conversation,'assistant',p_result->>'content',p_result->>'message_type',coalesce(p_result->'metadata','{}')) returning id into message_id;
    for plan in select jsonb_array_elements(coalesce(p_result->'proposals','[]')) loop
        insert into public.analysis_proposals(conversation_id,title,objective,analysis_plan,source_message_id)
        values(p_conversation,plan->>'title',plan->>'objective',plan,message_id);
    end loop;
    update public.conversations set current_stage = p_result->>'stage',
        stage_data = coalesce(p_result->'stage_data',stage_data),
        primary_goal = coalesce(primary_goal,p_result->>'goal'),
        title = case when not title_manual then coalesce(p_result->>'title',title) else title end,
        active_request_id = null, active_since = null where id = p_conversation;
    update public.chat_requests set status = 'completed' where conversation_id = p_conversation and request_id = p_request;
end;
$$;

create function public.protect_chat_request_binding() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    if new.provider is distinct from old.provider or (old.model is not null and new.model is distinct from old.model)
        or (old.status='completed' and new.model is distinct from old.model)
        then raise exception 'La procedencia de una solicitud existente no puede reescribirse'; end if;
    return new;
end;
$$;
create trigger chat_request_binding_guard before update on public.chat_requests
    for each row execute function public.protect_chat_request_binding();

-- Fence de instalación para impedir habilitar Terra con únicamente el esquema vulnerable 007.
create function public.provider_rollback_safety() returns integer
language sql stable security invoker set search_path = '' as $$ select 1 $$;

revoke all on function public.provider_rollback_safety(), public.begin_chat_turn(uuid,uuid,jsonb),
    public.begin_provider_chat_turn(uuid,uuid,jsonb,text,text),
    public.finish_chat_turn(uuid,uuid,jsonb), public.protect_chat_request_binding() from public, anon;
grant execute on function public.provider_rollback_safety(), public.begin_chat_turn(uuid,uuid,jsonb),
    public.begin_provider_chat_turn(uuid,uuid,jsonb,text,text),
    public.finish_chat_turn(uuid,uuid,jsonb), public.protect_chat_request_binding() to authenticated;

commit;
