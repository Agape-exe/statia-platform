begin;

alter table public.project_files drop constraint project_files_file_type_check;
alter table public.project_files drop constraint project_files_check;
alter table public.project_files add constraint project_files_file_type_check
  check (file_type in ('csv','xlsx','json','pdf','docx'));
alter table public.project_files add constraint project_files_check
  check ((file_role = 'instrument') = (file_type in ('pdf','docx')));

update storage.buckets
set allowed_mime_types = array_append(allowed_mime_types,
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
where id = 'project-files' and not (
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document' = any(allowed_mime_types));

commit;
