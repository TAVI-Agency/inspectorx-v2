-- ============================================================================
-- InspectorX v2 — слой юридической верификации: «Проверка юристом» (итерация 1)
-- Основа: docs/adr/0001-expert-verification.md,
--         docs/superpowers/specs/2026-07-29-lawyer-review-handoff.md
--
-- Строго аддитивно: только новые типы/таблицы/вью/функции/триггеры.
-- Из существующего пересоздаются лишь subscriber-политики закрытого контента —
-- drop/create с добавлением is_verified_lawyer(), чистое расширение доступа.
--
-- Модерация и верификация — только service_role (SQL-редактор), клиентских
-- грантов на статусные колонки нет нигде.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Типы
-- ----------------------------------------------------------------------------

create type public.lawyer_status as enum ('pending', 'verified', 'rejected');

-- подтверждаю / есть неточность / устарело / дополнение
create type public.review_verdict as enum ('confirm', 'inaccurate', 'outdated', 'addition');

create type public.review_status as enum ('pending', 'published', 'rejected');

create type public.lawyer_notification_kind as enum
  ('review_published', 'review_rejected', 'new_requirement');

-- ----------------------------------------------------------------------------
-- lawyer_profiles — заявка и статус юриста
-- ----------------------------------------------------------------------------

create table public.lawyer_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,          -- как подписываются заключения
  credentials text not null,           -- регалии свободным текстом: стаж, место работы
  license_no text,                     -- номер лицензии/удостоверения адвоката, если есть
  specializations text,                -- свободным текстом: «фарма, ВЭД, маркировка»
  status public.lawyer_status not null default 'pending',
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.lawyer_profiles is
  'Заявка «стать экспертом» и статус юриста. Верификация — вручную service_role.';

create trigger set_updated_at before update on public.lawyer_profiles
  for each row execute function public.set_updated_at();

alter table public.lawyer_profiles enable row level security;

-- Статус клиент себе не выставит: колоночный грант не покрывает status/verified_at
-- (тот же приём, что с profiles.is_subscribed).
revoke insert, update, delete on public.lawyer_profiles from anon, authenticated;
grant insert (user_id, display_name, credentials, license_no, specializations)
  on public.lawyer_profiles to authenticated;
grant update (display_name, credentials, license_no, specializations)
  on public.lawyer_profiles to authenticated;

create policy "own insert" on public.lawyer_profiles
  for insert to authenticated
  with check (user_id = (select auth.uid()));

create policy "own read" on public.lawyer_profiles
  for select to authenticated
  using (user_id = (select auth.uid()));

-- Публичное чтение верифицированных: заключение подписывается именем юриста
create policy "public read verified" on public.lawyer_profiles
  for select to anon, authenticated
  using (status = 'verified');

-- Повторная подача после отказа: владелец правит поля заявки (см. триггер ниже)
create policy "own update" on public.lawyer_profiles
  for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

-- Отклонённая заявка, поданная владельцем заново, возвращается в pending.
-- Сам клиент колонку status трогать не может — её сбрасывает этот триггер.
-- Для service_role auth.uid() пуст, админские правки триггер не задевает.
create or replace function public.lawyer_reapply_resets_status()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if old.status = 'rejected' and new.user_id = (select auth.uid()) then
    new.status := 'pending';
    new.verified_at := null;
  end if;
  return new;
end;
$$;

revoke all on function public.lawyer_reapply_resets_status() from public;
revoke all on function public.lawyer_reapply_resets_status() from anon, authenticated;

create trigger lawyer_reapply before update on public.lawyer_profiles
  for each row execute function public.lawyer_reapply_resets_status();

-- Проверка «текущий пользователь — верифицированный юрист» для политик
-- других таблиц. SECURITY DEFINER по образцу is_subscriber().
create or replace function public.is_verified_lawyer()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.lawyer_profiles lp
    where lp.user_id = (select auth.uid())
      and lp.status = 'verified'
  );
$$;

revoke all on function public.is_verified_lawyer() from public;
grant execute on function public.is_verified_lawyer() to anon, authenticated;

-- ----------------------------------------------------------------------------
-- Доступ юриста к закрытому контенту: наравне с подписчиком.
-- Пересоздание subscriber-политик — строго добавление or is_verified_lawyer(),
-- внутренние exists-подзапросы не меняются.
-- ----------------------------------------------------------------------------

drop policy "subscriber read" on public.requirement_details;
create policy "subscriber read" on public.requirement_details
  for select to authenticated
  using (
    (public.is_subscriber() or public.is_verified_lawyer())
    and exists (
      select 1 from public.requirements r
      where r.id = requirement_id and r.status = 'published'
    )
  );

drop policy "subscriber read" on public.requirement_faqs;
create policy "subscriber read" on public.requirement_faqs
  for select to authenticated
  using (
    (public.is_subscriber() or public.is_verified_lawyer())
    and exists (
      select 1 from public.requirements r
      where r.id = requirement_id and r.status = 'published'
    )
  );

drop policy "subscriber read" on public.requirement_citations;
create policy "subscriber read" on public.requirement_citations
  for select to authenticated
  using (
    (public.is_subscriber() or public.is_verified_lawyer())
    and exists (
      select 1 from public.requirements r
      where r.id = requirement_id and r.status = 'published'
    )
  );

drop policy "subscriber read" on public.requirement_revisions;
create policy "subscriber read" on public.requirement_revisions
  for select to authenticated
  using (
    (public.is_subscriber() or public.is_verified_lawyer())
    and exists (
      select 1 from public.requirements r
      where r.id = requirement_id and r.status = 'published'
    )
  );

-- Без act_paragraphs юридический слой пуст: цитаты embed-ятся из этой таблицы.
-- Handoff перечислял только 4 таблицы, но citations без текстов пунктов
-- бесполезны — расширяем и её (отступление зафиксировано в отчёте).
drop policy "subscriber read" on public.act_paragraphs;
create policy "subscriber read" on public.act_paragraphs
  for select to authenticated
  using (public.is_subscriber() or public.is_verified_lawyer());

-- ----------------------------------------------------------------------------
-- requirement_reviews — заключение юриста с вердиктом
-- ----------------------------------------------------------------------------

create table public.requirement_reviews (
  id uuid primary key default gen_random_uuid(),
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  lawyer_id uuid not null references public.lawyer_profiles(user_id) on delete cascade,
  verdict public.review_verdict not null,
  comment_text text not null,          -- фронт валидирует минимум ~20 символов
  status public.review_status not null default 'pending',
  official_reply text,                 -- ответ команды InspectorX, пишет только service_role
  official_replied_at timestamptz,
  published_at timestamptz,
  created_at timestamptz not null default now()
);

comment on table public.requirement_reviews is
  'Заключения юристов: премодерация (pending -> published/rejected service_role-ом).';

create index requirement_reviews_req_idx
  on public.requirement_reviews (requirement_id, status);
create index requirement_reviews_lawyer_idx
  on public.requirement_reviews (lawyer_id);

-- Антиспам: не больше одного pending-заключения юриста на требование
create unique index requirement_reviews_pending_uidx
  on public.requirement_reviews (lawyer_id, requirement_id)
  where status = 'pending';

alter table public.requirement_reviews enable row level security;

-- Статус и официальный ответ клиенту не выдаём даже на вставке:
-- всегда default pending, update-гранта нет вовсе.
revoke insert, update, delete on public.requirement_reviews from anon, authenticated;
grant insert (requirement_id, lawyer_id, verdict, comment_text)
  on public.requirement_reviews to authenticated;

create policy "verified lawyer insert" on public.requirement_reviews
  for insert to authenticated
  with check (
    lawyer_id = (select auth.uid())
    and public.is_verified_lawyer()
  );

-- Опубликованные заключения published-требований видят все
create policy "read published of published" on public.requirement_reviews
  for select to anon, authenticated
  using (
    status = 'published'
    and exists (
      select 1 from public.requirements r
      where r.id = requirement_id and r.status = 'published'
    )
  );

-- Юрист видит все свои (в т.ч. «на модерации» и отклонённые)
create policy "own read" on public.requirement_reviews
  for select to authenticated
  using (lawyer_id = (select auth.uid()));

-- Штампы времени при модерации service_role-ом: publish и официальный ответ
create or replace function public.review_moderation_stamps()
returns trigger
language plpgsql
as $$
begin
  if new.status = 'published' and old.status <> 'published'
     and new.published_at is null then
    new.published_at := now();
  end if;
  if new.official_reply is not null
     and new.official_reply is distinct from old.official_reply then
    new.official_replied_at := now();
  end if;
  return new;
end;
$$;

create trigger review_moderation_stamps before update on public.requirement_reviews
  for each row execute function public.review_moderation_stamps();

-- ----------------------------------------------------------------------------
-- review_votes — голоса «помогло / не помогло»
-- ----------------------------------------------------------------------------

create table public.review_votes (
  review_id uuid not null references public.requirement_reviews(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  vote smallint not null check (vote in (1, -1)),  -- 1 = помогло, -1 = не помогло
  created_at timestamptz not null default now(),
  primary key (review_id, user_id)                 -- один голос на пользователя
);

comment on table public.review_votes is
  'Голоса «помогло/не помогло»: менять и снимать можно, за своё заключение — нельзя.';

alter table public.review_votes enable row level security;

revoke insert, update, delete on public.review_votes from anon, authenticated;
grant insert (review_id, user_id, vote) on public.review_votes to authenticated;
grant update (vote) on public.review_votes to authenticated;
grant delete on public.review_votes to authenticated;

-- Голосовать можно только за published-заключение и не за собственное.
-- SECURITY DEFINER: заглядывает в requirement_reviews мимо её RLS.
create or replace function public.review_votable(rid uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.requirement_reviews r
    where r.id = rid
      and r.status = 'published'
      and r.lawyer_id <> (select auth.uid())
  );
$$;

revoke all on function public.review_votable(uuid) from public;
grant execute on function public.review_votable(uuid) to authenticated;

create policy "own insert" on public.review_votes
  for insert to authenticated
  with check (user_id = (select auth.uid()) and public.review_votable(review_id));

create policy "own update" on public.review_votes
  for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()) and public.review_votable(review_id));

create policy "own delete" on public.review_votes
  for delete to authenticated
  using (user_id = (select auth.uid()));

-- Чужие голоса не видны — публичны только счётчики через view ниже
create policy "own read" on public.review_votes
  for select to authenticated
  using (user_id = (select auth.uid()));

-- ----------------------------------------------------------------------------
-- Агрегатные view: счётчики публичны, сырые голоса — нет.
-- security_invoker = off: view работает от владельца, мимо RLS таблиц.
-- ----------------------------------------------------------------------------

create view public.review_vote_counts with (security_invoker = off) as
  select review_id,
         count(*) filter (where vote = 1)::int  as helpful,
         count(*) filter (where vote = -1)::int as not_helpful
  from public.review_votes
  group by review_id;

-- Бейдж на строке требования: сколько юристов подтвердили / оставили замечания
create view public.requirement_review_stats with (security_invoker = off) as
  select requirement_id,
         count(*) filter (where verdict = 'confirm')::int as confirms,
         count(*) filter (where verdict in ('inaccurate', 'outdated'))::int as disputes,
         count(*)::int as total
  from public.requirement_reviews
  where status = 'published'
  group by requirement_id;

-- Дешборд юриста: вклад и полезность
create view public.lawyer_stats with (security_invoker = off) as
  select r.lawyer_id,
         count(distinct r.requirement_id)::int as requirements_reviewed,
         count(*)::int as reviews_published,
         coalesce(sum(v.helpful), 0)::int as helpful_total,
         coalesce(sum(v.not_helpful), 0)::int as not_helpful_total
  from public.requirement_reviews r
  left join public.review_vote_counts v on v.review_id = r.id
  where r.status = 'published'
  group by r.lawyer_id;

-- Рейтинг: полезность, при равенстве — число публикаций
create view public.lawyer_leaderboard with (security_invoker = off) as
  select s.lawyer_id,
         lp.display_name,
         lp.credentials,
         s.requirements_reviewed,
         s.reviews_published,
         s.helpful_total,
         s.not_helpful_total,
         (rank() over (order by s.helpful_total desc, s.reviews_published desc))::int as rank
  from public.lawyer_stats s
  join public.lawyer_profiles lp
    on lp.user_id = s.lawyer_id and lp.status = 'verified';

grant select on public.review_vote_counts,
                public.requirement_review_stats,
                public.lawyer_stats,
                public.lawyer_leaderboard
  to anon, authenticated;

-- ----------------------------------------------------------------------------
-- lawyer_notifications — in-app уведомления юристу.
-- user_notifications не переиспользуем: она зарезервирована под цепочку
-- change_events и закрыта для клиентского insert.
-- ----------------------------------------------------------------------------

create table public.lawyer_notifications (
  id uuid primary key default gen_random_uuid(),
  lawyer_id uuid not null references public.lawyer_profiles(user_id) on delete cascade,
  kind public.lawyer_notification_kind not null,
  requirement_id uuid references public.requirements(id) on delete cascade,
  review_id uuid references public.requirement_reviews(id) on delete cascade,
  is_read boolean not null default false,
  read_at timestamptz,
  created_at timestamptz not null default now()
);

create index lawyer_notifications_lawyer_idx
  on public.lawyer_notifications (lawyer_id, is_read, created_at desc);

-- Повторная публикация требования не плодит дублей «нового требования»
create unique index lawyer_notifications_new_req_uidx
  on public.lawyer_notifications (lawyer_id, requirement_id)
  where kind = 'new_requirement';

alter table public.lawyer_notifications enable row level security;

-- Точная копия паттерна user_notifications: own read; own update только
-- is_read/read_at; клиентский insert запрещён — пишут триггеры ниже.
revoke insert, update, delete on public.lawyer_notifications from anon, authenticated;
grant update (is_read, read_at) on public.lawyer_notifications to authenticated;

create policy "own read" on public.lawyer_notifications
  for select to authenticated
  using (lawyer_id = (select auth.uid()));

create policy "own update" on public.lawyer_notifications
  for update to authenticated
  using (lawyer_id = (select auth.uid()))
  with check (lawyer_id = (select auth.uid()));

-- ----------------------------------------------------------------------------
-- Триггеры-писатели уведомлений (security definer, ошибки никогда не роняют
-- исходную операцию — правило из 20260727120000_lead_notifications.sql)
-- ----------------------------------------------------------------------------

-- pending -> published / rejected: уведомить автора заключения
create or replace function public.notify_lawyer_review_status()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if old.status = 'pending' and new.status = 'published' then
    insert into public.lawyer_notifications (lawyer_id, kind, requirement_id, review_id)
    values (new.lawyer_id, 'review_published', new.requirement_id, new.id);
  elsif old.status = 'pending' and new.status = 'rejected' then
    insert into public.lawyer_notifications (lawyer_id, kind, requirement_id, review_id)
    values (new.lawyer_id, 'review_rejected', new.requirement_id, new.id);
  end if;
  return new;
exception when others then
  raise warning 'notify_lawyer_review_status: %', sqlerrm;
  return new;
end;
$$;

revoke all on function public.notify_lawyer_review_status() from public;
revoke all on function public.notify_lawyer_review_status() from anon, authenticated;

create trigger notify_lawyer_on_review_status
  after update on public.requirement_reviews
  for each row execute function public.notify_lawyer_review_status();

-- Требование стало published: по уведомлению каждому verified-юристу.
-- Юристов на старте мало — объём безопасен; конфликт молча пропускается.
create or replace function public.notify_lawyers_new_requirement()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.status = 'published'
     and (tg_op = 'INSERT' or old.status is distinct from new.status) then
    insert into public.lawyer_notifications (lawyer_id, kind, requirement_id)
    select lp.user_id, 'new_requirement', new.id
    from public.lawyer_profiles lp
    where lp.status = 'verified'
    on conflict (lawyer_id, requirement_id) where kind = 'new_requirement' do nothing;
  end if;
  return new;
exception when others then
  raise warning 'notify_lawyers_new_requirement: %', sqlerrm;
  return new;
end;
$$;

revoke all on function public.notify_lawyers_new_requirement() from public;
revoke all on function public.notify_lawyers_new_requirement() from anon, authenticated;

create trigger notify_lawyers_on_new_requirement
  after insert or update on public.requirements
  for each row execute function public.notify_lawyers_new_requirement();

-- ----------------------------------------------------------------------------
-- Уведомления модератору в Telegram: новое заключение и новая заявка юриста.
-- Точный образец 20260727120000: исключение никогда не роняет вставку,
-- при отсутствии секретов notify_admin_telegram молча пропускает.
-- ----------------------------------------------------------------------------

create or replace function public.notify_admin_new_review()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  req_title   text;
  lawyer_name text;
  stamp       text := to_char(now() at time zone 'Asia/Tashkent', 'DD.MM.YYYY HH24:MI');
begin
  select title into req_title
    from public.requirement_contents
    where requirement_id = new.requirement_id and lang = 'ru'
    limit 1;
  select display_name into lawyer_name
    from public.lawyer_profiles
    where user_id = new.lawyer_id;

  perform public.notify_admin_telegram(
    '⚖️ Заключение юриста на модерацию' || E'\n'
    || 'Юрист: '   || coalesce(lawyer_name, '—') || E'\n'
    || 'Вердикт: ' || new.verdict::text || E'\n'
    || 'Требование: ' || coalesce(left(req_title, 200), new.requirement_id::text) || E'\n'
    || left(coalesce(new.comment_text, ''), 300) || E'\n'
    || stamp
  );
  return new;
exception when others then
  raise warning 'notify_admin_new_review: %', sqlerrm;
  return new;
end;
$$;

revoke all on function public.notify_admin_new_review() from public;
revoke all on function public.notify_admin_new_review() from anon, authenticated;

create trigger notify_admin_on_new_review
  after insert on public.requirement_reviews
  for each row execute function public.notify_admin_new_review();

-- Заявка юриста: без сигнала админу ручная верификация зависнет
create or replace function public.notify_admin_lawyer_application()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  stamp text := to_char(now() at time zone 'Asia/Tashkent', 'DD.MM.YYYY HH24:MI');
begin
  perform public.notify_admin_telegram(
    '👨‍⚖️ Заявка юриста на верификацию' || E'\n'
    || 'Имя: '     || coalesce(new.display_name, '—') || E'\n'
    || 'Регалии: ' || left(coalesce(new.credentials, '—'), 200) || E'\n'
    || coalesce('Лицензия: ' || new.license_no || E'\n', '')
    || stamp
  );
  return new;
exception when others then
  raise warning 'notify_admin_lawyer_application: %', sqlerrm;
  return new;
end;
$$;

revoke all on function public.notify_admin_lawyer_application() from public;
revoke all on function public.notify_admin_lawyer_application() from anon, authenticated;

create trigger notify_admin_on_lawyer_application
  after insert on public.lawyer_profiles
  for each row execute function public.notify_admin_lawyer_application();
