begin;

create table public.projects (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    name text not null check (name = btrim(name) and char_length(name) between 1 and 120),
    project_type text not null check (project_type in ('thesis', 'general')),
    description text check (char_length(description) <= 2000),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index projects_user_updated_idx on public.projects (user_id, updated_at desc);

create function public.protect_project_fields() returns trigger
language plpgsql set search_path = '' as $$
begin
    if new.id is distinct from old.id
       or new.user_id is distinct from old.user_id
       or new.project_type is distinct from old.project_type
       or new.created_at is distinct from old.created_at then
        raise exception 'La identidad, propietario, tipo y fecha de creación son inmutables';
    end if;
    new.updated_at = now();
    return new;
end;
$$;

create trigger projects_before_update before update on public.projects
for each row execute function public.protect_project_fields();

alter table public.projects enable row level security;
revoke all on public.projects from anon, authenticated;
grant select, insert, update, delete on public.projects to authenticated;

create policy projects_select on public.projects for select to authenticated
using ((select auth.uid()) = user_id);
create policy projects_insert on public.projects for insert to authenticated
with check ((select auth.uid()) = user_id);
create policy projects_update on public.projects for update to authenticated
using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy projects_delete on public.projects for delete to authenticated
using ((select auth.uid()) = user_id);

commit;
