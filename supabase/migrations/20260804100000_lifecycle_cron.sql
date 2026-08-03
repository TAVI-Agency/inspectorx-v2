-- ============================================================================
-- InspectorX v2 — Задача 38: cron переходов ЖЦ + lifecycle-уведомления
-- (Блок 5, финал). Раз в сутки находит требования, у которых даты жизненного
-- цикла (effective_from / transition_until / valid_to) наступили СЕГОДНЯ, и
-- заводит уведомление user_notifications(kind='lifecycle') каждому юзеру, у
-- которого выбран товар/услуга, к которому применимо требование.
--
-- Источник событий переиспользует view user_deadline_events (Задача 12,
-- 20260803180000_calendar_notifications.sql): она уже DISTINCT по
-- (user_id, requirement_id, event_kind, event_date) и матчит применимость и
-- по точному product_type_id, и по широким scope 'all_products'/
-- 'all_services' — велосипед здесь не нужен, достаточно сузить её условие
-- event_date >= current_date до event_date = current_date («наступило
-- сегодня», а не «предстоит»).
--
-- Перенос даты актом (админ поменял effective_from/valid_to у уже
-- published-требования между прогонами cron) — это обычное изменение
-- требования и приходит пользователю через Impact-маппер как
-- user_notifications(kind='change', impact_id=…), как любое другое
-- редактирование. Этот cron такие переносы не отслеживает и не обрабатывает.
-- ============================================================================

create extension if not exists pg_cron;
-- На проде Supabase pg_cron НЕЛЬЗЯ включить одним `create extension` в
-- миграции — расширение сначала нужно разрешить в Dashboard → Database →
-- Extensions (галка pg_cron), иначе GitHub-интеграция уронит накат этой
-- миграции. Добавить пункт в docs/LAUNCH_CHECKLIST.md перед мёржем.

-- ----------------------------------------------------------------------------
-- Идемпотентность вставки: одно lifecycle-уведомление на пару
-- (юзер, требование, событие). payload->>'event' — immutable-выражение
-- (jsonb ->> immutable), поэтому обычный (не generated column) expression-
-- индекс работает и годится как arbiter для ON CONFLICT ниже.
-- ----------------------------------------------------------------------------

create unique index if not exists user_notifications_lifecycle_uidx
  on public.user_notifications (user_id, requirement_id, ((payload ->> 'event')))
  where kind = 'lifecycle';

comment on index public.user_notifications_lifecycle_uidx is
  'Идемпотентность cron-а Задачи 38: повторный прогон process_lifecycle_'
  'transitions в тот же день (или на уже обработанное событие) не заводит '
  'вторую строку — INSERT … ON CONFLICT DO NOTHING на этот индекс.';

-- ----------------------------------------------------------------------------
-- process_lifecycle_transitions — тело cron-джоба. security definer: читает
-- user_deadline_events (view закрыта revoke-ом от anon/authenticated, отдана
-- только service_role) и пишет user_notifications мимо RLS-политики "own
-- insert" — такой политики на user_notifications нет вообще, вставляют
-- только серверные функции. search_path закреплён явно (security definer +
-- незафиксированный search_path — стандартная дыра).
-- Возвращает число реально вставленных строк (не общее число кандидатов) —
-- ON CONFLICT DO NOTHING их не считает, что и нужно для теста идемпотентности.
-- ----------------------------------------------------------------------------

create or replace function public.process_lifecycle_transitions()
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  inserted_count int;
begin
  insert into public.user_notifications (user_id, requirement_id, kind, payload)
  select
    e.user_id,
    e.requirement_id,
    'lifecycle',
    jsonb_build_object('event', e.event_kind, 'date', e.event_date, 'title', e.title)
  from public.user_deadline_events e
  where e.event_date = current_date
  on conflict (user_id, requirement_id, ((payload ->> 'event')))
    where kind = 'lifecycle'
  do nothing;

  get diagnostics inserted_count = row_count;
  return inserted_count;
end;
$$;

comment on function public.process_lifecycle_transitions() is
  'Задача 38: раз в сутки (см. cron.schedule ниже) заводит user_notifications'
  '(kind=lifecycle) по событиям user_deadline_events, наступившим сегодня. '
  'Возвращает число вставленных строк. Вызывается только cron-джобом — не '
  'выдана anon/authenticated (revoke ниже), чтобы через PostgREST rpc её не '
  'мог дёрнуть посторонний и не устроил спам-рассылку задним числом.';

revoke all on function public.process_lifecycle_transitions() from public;
revoke all on function public.process_lifecycle_transitions() from anon, authenticated;

-- ----------------------------------------------------------------------------
-- Расписание: 03:00 (UTC — таймзона cron.timezone по умолчанию) каждый день.
-- Обёрнуто в проверку существования джоба — повторный накат этой миграции
-- (или ручной re-run) не плодит дублей в cron.job.
-- ----------------------------------------------------------------------------

do $$
begin
  if not exists (select 1 from cron.job where jobname = 'lifecycle-transitions') then
    perform cron.schedule(
      'lifecycle-transitions',
      '0 3 * * *',
      $cron$select public.process_lifecycle_transitions()$cron$
    );
  end if;
end;
$$;
