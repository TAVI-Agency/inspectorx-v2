-- ============================================================================
-- InspectorX v2 — jurisdiction в requirements и change_events
-- Решение и обоснование: docs/adr/0005-ecosystem-contracts.md
--
-- Добавляем колонку jurisdiction (ISO 3166-1 alpha-2) к requirements и
-- change_events. Контент (contents/details/scope) наследует страну через
-- FK requirement_id (решение ADR-0006). Default 'UZ' — первый запуск только
-- для Узбекистана.
-- ============================================================================

alter table public.requirements
  add column jurisdiction text not null default 'UZ' check (jurisdiction ~ '^[A-Z]{2}$');
create index on public.requirements (jurisdiction);

comment on column public.requirements.jurisdiction is
  'ISO 3166-1 alpha-2 (UZ, KZ, AE). Контент наследует страну через FK на '
  'requirement_id (ADR-0006). Default UZ для первого запуска.';

alter table public.change_events
  add column jurisdiction text not null default 'UZ' check (jurisdiction ~ '^[A-Z]{2}$');

comment on column public.change_events.jurisdiction is
  'ISO 3166-1 alpha-2 (UZ, KZ, AE). Синхронизируется с requirements.jurisdiction '
  'через trigger на обновление requirements (будущая реализация).';
