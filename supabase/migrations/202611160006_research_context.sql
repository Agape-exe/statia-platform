begin;

create function public.valid_research_context(doc jsonb) returns boolean
language plpgsql immutable set search_path = '' as $$
declare k text; v jsonb; item jsonb;
begin
  if jsonb_typeof(doc) is distinct from 'object'
     or doc->'schema_version' is distinct from '1'::jsonb
     or char_length(doc::text) > 18000 then return false; end if;
  for k, v in select * from jsonb_each(doc) loop
    if k = 'schema_version' then continue;
    elsif k in ('research_title', 'research_problem', 'general_objective',
      'methodological_design', 'population_sample', 'additional_information') then
      if v <> 'null'::jsonb and (jsonb_typeof(v) <> 'string' or char_length(v #>> '{}') > 2000) then return false; end if;
    elsif k in ('specific_objectives', 'hypotheses', 'variables', 'instruments') then
      if jsonb_typeof(v) <> 'array' then return false; end if;
      if jsonb_array_length(v) > 20 then return false; end if;
      for item in select * from jsonb_array_elements(v) loop
        if jsonb_typeof(item) <> 'string' or char_length(item #>> '{}') not between 1 and 500 then return false; end if;
      end loop;
    elsif k = 'additional_fields' then
      if jsonb_typeof(v) <> 'object' then return false; end if;
      if (select count(*) from jsonb_object_keys(v)) > 20 then return false; end if;
      if exists (select 1 from jsonb_each(v) as entry where
        char_length(entry.key) not between 1 and 80 or
        (entry.value <> 'null'::jsonb and (jsonb_typeof(entry.value) <> 'string' or char_length(entry.value #>> '{}') > 2000))) then return false; end if;
    else return false;
    end if;
  end loop;
  return true;
end;
$$;

create table public.research_contexts (
  project_id uuid primary key references public.projects(id) on delete cascade,
  document jsonb not null check (public.valid_research_context(document)),
  revision integer not null default 1 check (revision >= 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create function public.protect_research_context() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    new.revision = 1;
  else
    if new.project_id is distinct from old.project_id or new.created_at is distinct from old.created_at then
      raise exception 'La identidad y fecha de creación del contexto son inmutables';
    end if;
    new.revision = old.revision + 1;
  end if;
  new.updated_at = now();
  return new;
end;
$$;
create trigger research_context_before_write before insert or update on public.research_contexts
for each row execute function public.protect_research_context();

alter table public.research_contexts enable row level security;
revoke all on public.research_contexts from anon, authenticated;
grant select, insert, update on public.research_contexts to authenticated;

create policy research_context_select on public.research_contexts for select to authenticated
using (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid()) and p.project_type = 'thesis'));
create policy research_context_insert on public.research_contexts for insert to authenticated
with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid()) and p.project_type = 'thesis'));
create policy research_context_update on public.research_contexts for update to authenticated
using (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid()) and p.project_type = 'thesis'))
with check (exists (select 1 from public.projects p where p.id = project_id and p.user_id = (select auth.uid()) and p.project_type = 'thesis'));

create function public.save_research_context(p_project uuid, p_document jsonb, p_expected_revision integer)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare current_revision integer; saved public.research_contexts;
begin
  -- Serializar guardados de todas las conversaciones/pestañas del mismo proyecto.
  perform 1 from public.projects where id = p_project and user_id = (select auth.uid())
    and project_type = 'thesis' for update;
  if not found then raise exception 'Proyecto de tesis no disponible' using errcode = 'P0001'; end if;
  select revision into current_revision from public.research_contexts where project_id = p_project;
  if p_expected_revision is null or p_expected_revision < 0
     or coalesce(current_revision, 0) <> p_expected_revision then
    raise exception 'El contexto cambió; recarga y revisa antes de guardar' using errcode = 'P0001';
  end if;
  if current_revision is null then
    insert into public.research_contexts(project_id, document) values (p_project, p_document) returning * into saved;
  else
    update public.research_contexts set document = p_document where project_id = p_project returning * into saved;
  end if;
  return jsonb_build_object('document', saved.document, 'revision', saved.revision, 'updated_at', saved.updated_at);
end;
$$;
revoke all on function public.save_research_context(uuid, jsonb, integer) from public, anon;
grant execute on function public.save_research_context(uuid, jsonb, integer) to authenticated;

commit;
