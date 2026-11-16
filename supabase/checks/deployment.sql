-- Solo inspección. SQL Editor es privilegiado: esto NO prueba aislamiento RLS.
select table_name from information_schema.tables
where table_schema = 'public' and table_name in (
  'projects', 'conversations', 'messages', 'project_files', 'conversation_files',
  'analysis_proposals', 'chat_requests', 'analysis_runs', 'analysis_artifacts', 'research_contexts'
) order by table_name;

select tablename, rowsecurity from pg_tables where schemaname = 'public'
and tablename in ('projects', 'conversations', 'messages', 'project_files',
  'conversation_files', 'analysis_proposals', 'chat_requests', 'analysis_runs', 'analysis_artifacts', 'research_contexts');

select tablename, policyname, cmd, roles from pg_policies
where schemaname in ('public', 'storage') order by schemaname, tablename, policyname;

select id, public, file_size_limit from storage.buckets
where id in ('project-files', 'analysis-results');

select column_name from information_schema.columns
where table_schema = 'public' and table_name = 'analysis_proposals' and column_name = 'source_message_id';

select p.proname, p.prosecdef as security_definer, pg_get_functiondef(p.oid) as definition
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname in (
  'decide_proposal', 'finish_chat_turn', 'begin_analysis_run', 'finish_analysis_run', 'save_research_context'
) order by p.proname;
