-- ============================================================================
-- InspectorX v2 — даты жизненного цикла + вычисляемый статус
-- Функция lifecycle_status() и view requirements_with_status
-- ============================================================================

alter table public.requirements
  add column effective_from  date,   -- вступление в силу
  add column transition_until date,  -- конец переходного периода
  add column valid_to        date,   -- утрата силы
  add column repealed_by_ref text;   -- реквизит отменяющего акта (текст: акт в LegalX)

create or replace function public.lifecycle_status(
  p_effective_from date, p_transition_until date, p_valid_to date,
  p_today date default current_date
) returns text language sql immutable as $$
  select case
    when p_valid_to is not null and p_today >= p_valid_to then 'repealed'
    when p_valid_to is not null
         and p_today >= p_valid_to - 60 then 'expiring'      -- окно 60 дней, константа
    when p_effective_from is not null and p_today < p_effective_from then 'upcoming'
    when p_transition_until is not null and p_today <= p_transition_until then 'transitional'
    else 'in_force'
  end
$$;

-- ВНИМАНИЕ: `select r.*` фиксирует список колонок `requirements` НА МОМЕНТ
-- СОЗДАНИЯ view (Postgres разворачивает `*` в конкретные имена колонок при
-- `create view`, а не заново при каждом запросе). Будущий `alter table
-- public.requirements add column ...` в отдельной миграции такую колонку в
-- этот view НЕ добавит — понадобится `create or replace view` в ТОЙ ЖЕ
-- миграции, что добавляет колонку, иначе потребители view (`src/data/real.ts`
-- и т.п.) её не увидят.
create view public.requirements_with_status with (security_invoker = true) as
  select r.*, public.lifecycle_status(r.effective_from, r.transition_until, r.valid_to) as lifecycle
  from public.requirements r;

comment on view public.requirements_with_status is
  'Требования с вычисленным lifecycle-статусом. Статус не хранится текстом в таблице (TARGET_FORMAT §4а), '
  'вычисляется на лету на основе дат: effective_from, transition_until, valid_to. '
  'Возможные значения статуса: upcoming (не вступило в силу), transitional (переходный период), '
  'in_force (действует), expiring (в течение 60 дней до отмены), repealed (отменено).';

comment on column public.requirements.effective_from is
  'Дата вступления нормативного акта в силу';

comment on column public.requirements.transition_until is
  'Дата завершения переходного периода действия нормативного акта';

comment on column public.requirements.valid_to is
  'Дата утраты силы нормативным актом';

comment on column public.requirements.repealed_by_ref is
  'Текстовая ссылка (реквизит) на нормативный акт, который отменил данный';
