-- ============================================================================
-- InspectorX v2 — Задача 40: Impact-маппер + In-house lawyer (мониторинг) +
-- ре-ревью (Блок 6, контур C). importer/monitoring/impact_mapper.py.
--
-- 1) change_events.processed_at — маркер «маппер уже обработал это событие»
--    (impacts посчитаны/impact-кандидатов не нашлось — оба исхода валидны
--    и оба помечаются). requirement_change_impacts НЕ годится маркером:
--    событие без единого затронутого требования тоже должно считаться
--    обработанным, иначе маппер бесконечно пересчитывал бы его заново.
--
-- 2) public.fanout_change_notifications(uuid[]) — SQL-функция фан-аута
--    impacts -> user_notifications(kind='change') для пользователей с
--    применимым товаром/услугой. Тот же принцип, что и
--    process_lifecycle_transitions (20260804100000_lifecycle_cron.sql):
--    применимость матчится и по точному product_type_id, и по широким
--    scope 'all_products'/'all_services' (requirement_applicability.
--    product_type_id у них всегда NULL по дизайну, см.
--    20260803130000_scope_product_type.sql) — тот же join, что у
--    user_deadline_events (20260803180000_calendar_notifications.sql).
--    Идемпотентность — ON CONFLICT на unique(user_id, impact_id) из
--    20260711120000_initial_schema.sql (kind='change' держит impact_id
--    NOT NULL, см. 20260803180000_calendar_notifications.sql chk).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) processed_at
-- ----------------------------------------------------------------------------

alter table public.change_events add column processed_at timestamptz;

comment on column public.change_events.processed_at is
  'Задача 40: маркер «Impact-маппер уже обработал это событие» (импакт-'
  'кандидаты посчитаны либо честно не найдены — оба исхода помечаются). '
  'NULL — событие в очереди на обработку.';

-- Частичный индекс под list_unprocessed_events (processed_at is null) —
-- очередь необработанных событий обычно много меньше всей таблицы.
create index change_events_unprocessed_idx
  on public.change_events (created_at) where processed_at is null;

-- ----------------------------------------------------------------------------
-- 2) fanout_change_notifications — фан-аут impacts -> user_notifications.
-- security definer по тому же принципу, что и process_lifecycle_
-- transitions/ingest_change_event: search_path закреплён явно, вызывается
-- только сервисным ключом импортёра (SupabaseMonitoringStore.
-- fanout_notifications), не PostgREST-ролями клиента — revoke от
-- anon/authenticated ниже.
-- ----------------------------------------------------------------------------

create or replace function public.fanout_change_notifications(p_impact_ids uuid[])
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  inserted_count int;
begin
  insert into public.user_notifications (user_id, impact_id, requirement_id, product_id, service_id, kind)
  select distinct
    cp.user_id, i.id, i.requirement_id, cp.product_id, cp.service_id, 'change'
  from public.requirement_change_impacts i
  join public.requirement_applicability ra on ra.requirement_id = i.requirement_id
  join public.chosen_products cp on true
  left join public.products p on p.id = cp.product_id
  left join public.services s on s.id = cp.service_id
  where i.id = any(p_impact_ids)
    and (
         (ra.product_type_id is not null
            and ra.product_type_id = coalesce(p.product_type_id, s.product_type_id))
      or (ra.scope = 'all_products' and cp.product_id is not null)
      or (ra.scope = 'all_services' and cp.service_id is not null)
    )
  on conflict (user_id, impact_id) do nothing;

  get diagnostics inserted_count = row_count;
  return inserted_count;
end;
$$;

comment on function public.fanout_change_notifications(uuid[]) is
  'Задача 40: по списку requirement_change_impacts.id заводит '
  'user_notifications(kind=change) пользователям с применимым товаром/'
  'услугой (chosen_products, та же применимость, что и user_deadline_'
  'events). Возвращает число реально вставленных строк — ON CONFLICT '
  '(user_id, impact_id) DO NOTHING их не считает, что и нужно для '
  'идемпотентности повторного вызова.';

revoke all on function public.fanout_change_notifications(uuid[]) from public;
revoke all on function public.fanout_change_notifications(uuid[]) from anon, authenticated;
