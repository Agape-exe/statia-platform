begin;

-- Aditiva: no reescribir mensajes, planes, resultados ni atribuir modelos históricos.
alter table public.conversations add column assistant_provider text not null default 'gemini'
    check (assistant_provider in ('gemini','openai'));
alter table public.chat_requests add column provider text not null default 'gemini'
    check (provider in ('gemini','openai'));
alter table public.chat_requests add column model text;

create function public.guard_conversation_provider() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    if new.assistant_provider is distinct from old.assistant_provider then
        if (old.active_request_id is not null and old.active_since > now() - interval '180 seconds')
            or exists(select 1 from public.analysis_runs where conversation_id=old.id
                and status='running' and started_at > now() - interval '180 seconds') then
            raise exception 'Espera a que termine la operación antes de cambiar de proveedor';
        end if;
    end if;
    return new;
end;
$$;
create trigger conversation_provider_guard before update of assistant_provider on public.conversations
    for each row execute function public.guard_conversation_provider();

create function public.record_provider_selection() returns trigger
language plpgsql security invoker set search_path = '' as $$
begin
    if new.assistant_provider is distinct from old.assistant_provider then
        insert into public.messages(conversation_id,role,content,message_type,metadata)
        values(new.id,'system',case when new.assistant_provider='gemini'
            then 'Gemini procesará los próximos mensajes y el contexto compartido de esta conversación.'
            else 'Terra (OpenAI), experimental, procesará los próximos mensajes y el contexto compartido de esta conversación.' end,
            'event',jsonb_build_object('source','deterministic','event','provider_selected',
                'previous_provider',old.assistant_provider,'provider',new.assistant_provider));
    end if;
    return new;
end;
$$;
create trigger conversation_provider_event after update of assistant_provider on public.conversations
    for each row execute function public.record_provider_selection();

create function public.select_conversation_provider(p_conversation uuid, p_provider text, p_expected text)
returns void language plpgsql security invoker set search_path = '' as $$
declare c public.conversations;
begin
    select * into c from public.conversations where id=p_conversation for update;
    if not found then raise exception 'Conversación no disponible'; end if;
    if p_provider is null or p_provider not in ('gemini','openai') then raise exception 'Proveedor desconocido'; end if;
    if c.assistant_provider is distinct from p_expected then raise exception 'La selección cambió; recarga'; end if;
    update public.conversations set assistant_provider=p_provider where id=c.id;
end;
$$;

create function public.create_provider_conversation(p_project uuid, p_source uuid default null, p_provider text default 'gemini')
returns uuid language plpgsql security invoker set search_path = '' as $$
declare cid uuid;
begin
    if p_provider is null or p_provider not in ('gemini','openai') then raise exception 'Proveedor desconocido'; end if;
    cid := public.create_conversation(p_project,p_source);
    update public.conversations set assistant_provider=p_provider where id=cid;
    return cid;
end;
$$;

-- La envoltura conserva serialización con ejecución, payload y firmas de los RPC previos.
create function public.begin_provider_chat_turn(p_conversation uuid, p_request uuid, p_payload jsonb, p_provider text, p_model text)
returns text language plpgsql security invoker set search_path = '' as $$
declare c public.conversations; r public.chat_requests; result text;
begin
    select * into c from public.conversations where id=p_conversation for update;
    if not found then raise exception 'Conversación no disponible'; end if;
    select * into r from public.chat_requests where conversation_id=p_conversation and request_id=p_request;
    if found then
        if r.payload <> p_payload then return 'mismatch'; end if;
        -- Un replay completado nunca llama al proveedor, aunque la selección haya cambiado.
        if r.status='completed' then return 'completed'; end if;
        if r.provider is distinct from p_provider or (r.model is not null and r.model is distinct from p_model)
            then return 'provider_changed'; end if;
    end if;
    if c.assistant_provider is distinct from p_provider then return 'provider_changed'; end if;
    if p_model is null or length(p_model)=0 or length(p_model)>120
        or (p_provider='openai' and p_model <> 'gpt-6.1-terra') then raise exception 'Modelo no permitido'; end if;
    result := public.begin_chat_turn(p_conversation,p_request,p_payload);
    if result='started' then
        update public.chat_requests set provider=p_provider,model=p_model
        where conversation_id=p_conversation and request_id=p_request;
    end if;
    return result;
end;
$$;

-- RLS existente por propietario cubre las columnas nuevas. Todos los RPC son invoker.
revoke all on function public.guard_conversation_provider(), public.record_provider_selection(),
    public.select_conversation_provider(uuid,text,text), public.create_provider_conversation(uuid,uuid,text),
    public.begin_provider_chat_turn(uuid,uuid,jsonb,text,text) from public, anon;
grant execute on function public.guard_conversation_provider(), public.record_provider_selection(),
    public.select_conversation_provider(uuid,text,text), public.create_provider_conversation(uuid,uuid,text),
    public.begin_provider_chat_turn(uuid,uuid,jsonb,text,text) to authenticated;

commit;
