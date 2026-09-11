-- ============================================================================
-- InspectorX v2 — pipeline.documents: кэш скачанных документов
--
-- Кэш скачанных документов research-режима Cartographer (importer/build/docfetch.py).
-- Ключ — URL; sha256 — для отчёта «по какому снимку построена карта».
--
-- Гранты/RLS — как у остальных таблиц pipeline (см. 20260803170000_pipeline_schema.sql):
-- вся таблица доступна только service role.
-- ============================================================================

create table pipeline.documents (
  url text primary key,
  final_url text not null,
  content_type text not null,
  sha256 text not null,
  text text not null,
  fetched_at timestamptz not null default now()
);

comment on table pipeline.documents is
  'Кэш документов research-режима Cartographer: URL -> текст + sha256 снимка';
comment on column pipeline.documents.url is 'Исходный запрошенный URL (ключ кэша)';
comment on column pipeline.documents.final_url is 'URL после редиректов';
comment on column pipeline.documents.content_type is 'Content-Type ответа (без параметров, напр. text/html)';
comment on column pipeline.documents.sha256 is 'sha256 сырого тела ответа — снимок источника для отчёта картирования';
comment on column pipeline.documents.text is 'Извлечённый текст (HTML/PDF); пустая строка для скана без текстового слоя';
comment on column pipeline.documents.fetched_at is 'Момент скачивания';

alter table pipeline.documents enable row level security;

-- Явный grant: только service_role, без anon/authenticated (usage на схему
-- уже выдан в 20260803170000_pipeline_schema.sql).
grant select, insert, update, delete
  on pipeline.documents
  to service_role;
