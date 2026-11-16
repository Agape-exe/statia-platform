begin;

-- Asociación persistida; el historial previo permanece sin orden inventado.
alter table public.messages add constraint messages_id_conversation_unique unique (id, conversation_id);
alter table public.analysis_proposals add column source_message_id uuid;
alter table public.analysis_proposals add constraint analysis_proposals_source_message_fk
    foreign key (source_message_id, conversation_id) references public.messages(id, conversation_id);
create index analysis_proposals_source_message_idx on public.analysis_proposals(source_message_id);

create function public.record_conversation_file() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    insert into public.messages(conversation_id,role,content,message_type,metadata)
    values(new.conversation_id,'system','Archivo asociado a la conversación.','event',jsonb_build_object('file_ids',jsonb_build_array(new.file_id)));
    return new;
end;
$$;
create trigger conversation_file_event after insert on public.conversation_files
    for each row execute function public.record_conversation_file();

create or replace function public.finish_chat_turn(p_conversation uuid, p_request uuid, p_result jsonb) returns void
language plpgsql security invoker set search_path = '' as $$
declare c public.conversations; plan jsonb; file_id text; message_id uuid;
begin
    select * into c from public.conversations where id = p_conversation for update;
    if not found or c.active_request_id is distinct from p_request then raise exception 'Turno no activo'; end if;
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
create or replace function public.decide_proposal(p_conversation uuid, p_proposal uuid, p_status text) returns void
language plpgsql security invoker set search_path = '' as $$
declare v_status text; v_title text; v_objective text;
begin
    perform 1 from public.conversations where id = p_conversation and active_request_id is null for update;
    if not found then raise exception 'Conversación no disponible u ocupada'; end if;
    if p_status not in ('accepted','rejected') then raise exception 'Decisión inválida'; end if;
    select status, title, objective into v_status, v_title, v_objective from public.analysis_proposals where id = p_proposal and conversation_id = p_conversation for update;
    if not found then raise exception 'Propuesta no disponible'; end if;
    if v_status = p_status then return; end if;
    if v_status <> 'proposed' then raise exception 'La propuesta ya fue decidida'; end if;
    update public.analysis_proposals set status = p_status where id = p_proposal;
    update public.conversations set current_stage = case when p_status = 'accepted' or exists(
        select 1 from public.analysis_proposals where conversation_id = p_conversation and status = 'accepted') then 'ready' else 'goal' end where id = p_conversation;
    -- Misma transacción y bloqueo que la decisión; el renombrado manual siempre prevalece.
    if p_status = 'accepted' then
        v_title := btrim(regexp_replace(v_title, '\s+', ' ', 'g'));
        if length(v_title) > 80 then
            v_title := coalesce(nullif(regexp_replace(left(v_title,79), '\s+\S*$', ''), ''), left(v_title,79)) || '…';
        end if;
        update public.conversations set title = v_title,
            stage_data = stage_data || '{"title_provisional":false}'::jsonb,
            primary_goal = coalesce(primary_goal, v_objective)
        where id = p_conversation and not title_manual and
            (coalesce(stage_data->'title_provisional' = 'true'::jsonb, false)
             or lower(title) in ('nueva conversación','nuevo chat','comprender archivos','comprender los archivos adjuntos',
                 'reutilizar archivos','cargar archivos nuevos','continuar con los datasets',
                 'sí, utilicé un instrumento','no tengo instrumento','continuar con la finalidad actual'));
    end if;
    insert into public.messages(conversation_id,role,content,message_type,metadata) values
    (p_conversation,'system',case when p_status = 'accepted' then 'Plan aceptado. Prepara los procedimientos y confirma su ejecución cuando estén listos.'
        else 'Propuesta rechazada. Puedes explicar qué deseas cambiar y solicitar otra.' end,'event',jsonb_build_object('proposal_id',p_proposal,'status',p_status));
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
    (v_id,'assistant','Hola, soy tu asistente estadístico. Puedo ayudarte a comprender tus datos, preparar procedimientos y ejecutar los análisis que confirmes.','text'),
    (v_id,'assistant',case when v_source is null then '¿Tus datos están relacionados con algún instrumento de recolección de información?'
        else '¿Deseas reutilizar los archivos de la conversación más reciente que tiene archivos o cargar archivos nuevos?' end,'question');
    return v_id;
end;
$$;


commit;
