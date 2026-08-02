-- ============================================================================
-- InspectorX v2 — Задача 12: календарные токены + виды персональных
-- уведомлений (kind/payload) + view предстоящих дат ЖЦ по товарам юзера.
-- Потребители (Блок 5, отдельная задача): .ics-фид (Vercel-функция, читает
-- calendar_tokens + user_deadline_events service_role-ключом) и cron
-- переходов ЖЧ (пишет user_notifications.kind = 'lifecycle').
-- Эта миграция готовит только данные — сам фид/cron не входит в задачу 12.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- calendar_tokens — токен .ics-подписки на календарь пользователя.
-- ----------------------------------------------------------------------------

create table public.calendar_tokens (
  user_id uuid primary key references auth.users(id) on delete cascade,
  token text not null unique default encode(extensions.gen_random_bytes(24), 'hex'),
  created_at timestamptz not null default now()
);

comment on table public.calendar_tokens is
  'Токен .ics-подписки на календарь пользователя (Блок 5). Сам фид по токену '
  'читает Vercel-функция service_role-ключом мимо RLS — отдельной политики на '
  'select по токену не нужно. RLS ниже — только владельцу из клиента: '
  'создать / посмотреть / отключить (удалить) свой токен.';

alter table public.calendar_tokens enable row level security;

create policy "own read" on public.calendar_tokens
  for select to authenticated using (user_id = (select auth.uid()));

create policy "own insert" on public.calendar_tokens
  for insert to authenticated with check (user_id = (select auth.uid()));

create policy "own delete" on public.calendar_tokens
  for delete to authenticated using (user_id = (select auth.uid()));

-- ----------------------------------------------------------------------------
-- user_notifications — новые виды уведомлений.
-- 'change' (умолчание) — существующая цепочка change_events ->
--   requirement_change_impacts, impact_id обязателен, как и раньше.
-- 'lifecycle' — переход даты ЖЦ требования (came_into_force/transition_end/
--   valid_to), пишет cron Блока 5; impact_id нет — событие не привязано к
--   ревью изменения.
-- 'checklist_version' — состав чек-листа товара юзера поменялся; impact_id
--   тоже нет. Детали обоих новых видов — в payload.
-- ----------------------------------------------------------------------------

alter table public.user_notifications
  add column kind text not null default 'change'
    check (kind in ('change', 'lifecycle', 'checklist_version')),
  add column payload jsonb,                       -- {event: 'came_into_force', date: …}
  alter column impact_id drop not null;            -- lifecycle-уведомления без impact

comment on column public.user_notifications.kind is
  'change — из requirement_change_impacts (impact_id обязателен); '
  'lifecycle / checklist_version — без impact_id, детали события в payload.';

comment on column public.user_notifications.payload is
  'Доп. данные для lifecycle/checklist_version, напр. '
  '{"event": "effective_from", "date": "2026-09-01"}. Для kind=change не используется.';

-- Держит связку kind <-> impact_id, заявленную выше, на уровне схемы.
alter table public.user_notifications
  add constraint user_notifications_kind_impact_chk check (
    (kind = 'change' and impact_id is not null)
    or (kind <> 'change' and impact_id is null)
  );

-- unique(user_id, impact_id) из 20260711120000 НЕ переопределяется: это
-- table CONSTRAINT (не NULLS NOT DISTINCT), а в Postgres NULL-ы в unique
-- constraint по умолчанию различны (NULLS DISTINCT — умолчание всегда, не
-- только начиная с 15-й версии). Поэтому много строк одного user_id с
-- impact_id = NULL (lifecycle/checklist_version) друг с другом НЕ
-- конфликтуют — партиционный unique-индекс из брифа (запасной путь) не
-- понадобился. Проверено вручную на db reset --local (см. отчёт задачи 12):
-- 3 строки (1, null) вставляются без ошибки в изолированном тесте, а затем
-- то же самое — двумя реальными lifecycle-уведомлениями одного юзера.

-- ----------------------------------------------------------------------------
-- user_deadline_events — предстоящие даты ЖЦ (effective_from/transition_
-- until/valid_to) published-требований, применимых к товарам/услугам юзера
-- (chosen_products). Источник для .ics-фида и cron-а lifecycle-уведомлений
-- (Блок 5, отдельная задача).
--
-- Отступление от брифа: применимость требования матчится не только точным
-- product_type_id (ADR-0004), но и широкими scope 'all_products' /
-- 'all_services' — у них requirement_applicability.product_type_id всегда
-- NULL по дизайну (см. 20260803130000_scope_product_type.sql, «NULL у
-- all_products/all_services — нет типа-цели»), и наивный join из брифа
-- (только по product_type_id) такие требования из фида терял бы целиком.
-- distinct — те же (user_id, requirement_id, event_kind, event_date) могут
-- прийти дважды, если у юзера выбрано несколько товаров/услуг, матчащих одно
-- и то же требование (напр. один и тот же 'all_products' плюс точный тип).
--
-- Страна НЕ фильтруется (юзер видит дедлайны товаров всех юрисдикций).
--
-- Безопасность: view обычная (security_invoker выключен, умолчание) — то
-- есть выполняется от владельца (postgres) и НЕ применяет RLS
-- chosen_products/requirements внутри себя. Поэтому select на неё НЕ выдан
-- anon/authenticated (revoke ниже) — иначе любой залогиненный юзер увидел бы
-- дедлайны и товары всех пользователей. Читает её только service_role:
-- Vercel-функция .ics-фида сервисным ключом, мимо PostgREST-ролей клиента.
-- ----------------------------------------------------------------------------

create view public.user_deadline_events with (security_invoker = off) as
  select distinct
         cp.user_id, r.id as requirement_id, r.jurisdiction,
         d.event_kind, d.event_date, rc.title
  from public.chosen_products cp
  left join public.products p on p.id = cp.product_id
  left join public.services s on s.id = cp.service_id
  join public.requirement_applicability ra on (
       (ra.product_type_id is not null
          and ra.product_type_id = coalesce(p.product_type_id, s.product_type_id))
    or (ra.scope = 'all_products' and cp.product_id is not null)
    or (ra.scope = 'all_services' and cp.service_id is not null)
  )
  join public.requirements r on r.id = ra.requirement_id and r.status = 'published'
  join lateral (values
    ('effective_from', r.effective_from),
    ('transition_until', r.transition_until),
    ('valid_to', r.valid_to)
  ) as d(event_kind, event_date) on d.event_date is not null and d.event_date >= current_date
  join public.requirement_contents rc on rc.requirement_id = r.id and rc.lang = 'ru';

comment on view public.user_deadline_events is
  'Предстоящие даты ЖЦ требований по товарам/услугам юзера (Блок 5: .ics-фид, '
  'lifecycle-уведомления). security_invoker выключен (умолчание) — работает от '
  'владельца, мимо RLS. Поэтому доступна только service_role (см. revoke/grant '
  'ниже) — обычному юзеру эта view не выдана, чтобы через PostgREST не утекли '
  'чужие данные.';

revoke all on public.user_deadline_events from anon, authenticated;
grant select on public.user_deadline_events to service_role;
