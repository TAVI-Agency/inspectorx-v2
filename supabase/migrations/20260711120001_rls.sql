-- ============================================================================
-- InspectorX v2 — RLS с первого дня
--
-- Матрица доступа (ревью схемы 11.07.2026):
--   anon / authenticated : published-тизер (requirements + contents),
--                          каталог, применимость, метаданные актов
--   подписчик            : details, faqs, тексты пунктов актов, citations,
--                          revisions, change_events, confirmed impacts
--   владелец строки      : profiles, chosen_products, questions, notifications
--   service_role         : всё админское (write контента, публикация, события)
-- ============================================================================

-- Активная подписка. SECURITY DEFINER: profiles закрыт RLS-ом,
-- а проверка нужна политикам других таблиц.
create or replace function public.is_subscriber()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.profiles p
    where p.id = (select auth.uid())
      and p.is_subscribed
      and (p.subscribed_until is null or p.subscribed_until > now())
  );
$$;

revoke all on function public.is_subscriber() from public;
grant execute on function public.is_subscriber() to anon, authenticated;

-- ----------------------------------------------------------------------------
-- Включаем RLS на всех таблицах (write без политики = запрещён всем, кроме service_role)
-- ----------------------------------------------------------------------------

alter table public.lifecycle_stages            enable row level security;
alter table public.authorities                 enable row level security;
alter table public.products                    enable row level security;
alter table public.services                    enable row level security;
alter table public.search_aliases              enable row level security;
alter table public.acts                        enable row level security;
alter table public.act_paragraphs              enable row level security;
alter table public.change_events               enable row level security;
alter table public.requirements                enable row level security;
alter table public.requirement_contents        enable row level security;
alter table public.requirement_details         enable row level security;
alter table public.requirement_applicability   enable row level security;
alter table public.requirement_citations       enable row level security;
alter table public.requirement_revisions       enable row level security;
alter table public.requirement_faqs            enable row level security;
alter table public.profiles                    enable row level security;
alter table public.chosen_products             enable row level security;
alter table public.subscription_requests       enable row level security;
alter table public.content_requests            enable row level security;
alter table public.user_questions              enable row level security;
alter table public.requirement_change_impacts  enable row level security;
alter table public.user_notifications          enable row level security;

-- ----------------------------------------------------------------------------
-- Публичное чтение: каталог и справочники
-- ----------------------------------------------------------------------------

create policy "public read" on public.lifecycle_stages
  for select to anon, authenticated using (true);

create policy "public read" on public.authorities
  for select to anon, authenticated using (true);

create policy "public read" on public.products
  for select to anon, authenticated using (true);

create policy "public read" on public.services
  for select to anon, authenticated using (true);

create policy "public read" on public.search_aliases
  for select to anon, authenticated using (true);

-- Метаданные актов (реквизиты) — публичны; тексты пунктов — по подписке (ниже)
create policy "public read" on public.acts
  for select to anon, authenticated using (true);

-- ----------------------------------------------------------------------------
-- Требования: уровень 0 (тизер) — публичен для published
-- ----------------------------------------------------------------------------

create policy "read published" on public.requirements
  for select to anon, authenticated
  using (status = 'published');

create policy "read teaser of published" on public.requirement_contents
  for select to anon, authenticated
  using (
    exists (
      select 1 from public.requirements r
      where r.id = requirement_id and r.status = 'published'
    )
  );

-- Применимость публична: без неё анонимная страница товара не найдёт требования
create policy "read applicability of published" on public.requirement_applicability
  for select to anon, authenticated
  using (
    exists (
      select 1 from public.requirements r
      where r.id = requirement_id and r.status = 'published'
    )
  );

-- ----------------------------------------------------------------------------
-- Платный контент: уровни 1–2 — только активная подписка
-- ----------------------------------------------------------------------------

create policy "subscriber read" on public.requirement_details
  for select to authenticated
  using (
    public.is_subscriber()
    and exists (
      select 1 from public.requirements r
      where r.id = requirement_id and r.status = 'published'
    )
  );

create policy "subscriber read" on public.requirement_faqs
  for select to authenticated
  using (
    public.is_subscriber()
    and exists (
      select 1 from public.requirements r
      where r.id = requirement_id and r.status = 'published'
    )
  );

create policy "subscriber read" on public.requirement_citations
  for select to authenticated
  using (
    public.is_subscriber()
    and exists (
      select 1 from public.requirements r
      where r.id = requirement_id and r.status = 'published'
    )
  );

create policy "subscriber read" on public.requirement_revisions
  for select to authenticated
  using (
    public.is_subscriber()
    and exists (
      select 1 from public.requirements r
      where r.id = requirement_id and r.status = 'published'
    )
  );

create policy "subscriber read" on public.act_paragraphs
  for select to authenticated
  using (public.is_subscriber());

create policy "subscriber read" on public.change_events
  for select to authenticated
  using (public.is_subscriber());

create policy "subscriber read confirmed" on public.requirement_change_impacts
  for select to authenticated
  using (public.is_subscriber() and status = 'confirmed');

-- ----------------------------------------------------------------------------
-- Профили: владелец читает и правит только «свои» поля.
-- Подписку (is_subscribed / subscribed_until) юзер себе включить не может:
-- колоночный грант не покрывает эти поля.
-- ----------------------------------------------------------------------------

create policy "own read" on public.profiles
  for select to authenticated
  using (id = (select auth.uid()));

create policy "own update" on public.profiles
  for update to authenticated
  using (id = (select auth.uid()))
  with check (id = (select auth.uid()));

revoke insert, update, delete on public.profiles from anon, authenticated;
grant update (full_name, phone, company) on public.profiles to authenticated;

-- ----------------------------------------------------------------------------
-- Избранное
-- ----------------------------------------------------------------------------

create policy "own read" on public.chosen_products
  for select to authenticated using (user_id = (select auth.uid()));

create policy "own insert" on public.chosen_products
  for insert to authenticated with check (user_id = (select auth.uid()));

create policy "own delete" on public.chosen_products
  for delete to authenticated using (user_id = (select auth.uid()));

-- ----------------------------------------------------------------------------
-- Заявки: вставка доступна и без логина (лендинг), чтение — только своих
-- ----------------------------------------------------------------------------

create policy "anyone insert" on public.subscription_requests
  for insert to anon, authenticated
  with check (user_id is null or user_id = (select auth.uid()));

create policy "own read" on public.subscription_requests
  for select to authenticated using (user_id = (select auth.uid()));

create policy "anyone insert" on public.content_requests
  for insert to anon, authenticated
  with check (user_id is null or user_id = (select auth.uid()));

create policy "own read" on public.content_requests
  for select to authenticated using (user_id = (select auth.uid()));

-- ----------------------------------------------------------------------------
-- Вопросы: только авторизованные, только свои
-- ----------------------------------------------------------------------------

create policy "own insert" on public.user_questions
  for insert to authenticated with check (user_id = (select auth.uid()));

create policy "own read" on public.user_questions
  for select to authenticated using (user_id = (select auth.uid()));

-- ----------------------------------------------------------------------------
-- Уведомления: чтение своих; UPDATE ограничен колонками is_read / read_at
-- ----------------------------------------------------------------------------

create policy "own read" on public.user_notifications
  for select to authenticated using (user_id = (select auth.uid()));

create policy "own update" on public.user_notifications
  for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

revoke insert, update, delete on public.user_notifications from anon, authenticated;
grant update (is_read, read_at) on public.user_notifications to authenticated;
