-- Actualizar únicamente títulos provisionales al aceptar; no reescribe planes ni datos previos.
begin;

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
    (p_conversation,'system',case when p_status = 'accepted' then 'Plan aceptado y preparado para ejecución en la Sesión 03. No se han calculado resultados inferenciales.'
        else 'Propuesta rechazada. Puedes explicar qué deseas cambiar y solicitar otra.' end,'event',jsonb_build_object('proposal_id',p_proposal,'status',p_status));
end;
$$;

commit;
