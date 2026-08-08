-- ============================================================================
-- Модерация заключений юриста по находкам фотоконтроля (решение владельца: «б»)
--
-- Дыра процесса, зафиксированная приёмкой Волны 1: юрист отправляет заключение
-- (`photo_finding_reviews`, всегда `status = 'pending'` — колоночный грант не
-- пускает клиента к `status`), владелец проверки видит только `published`
-- ("owner reads published", 20260810100000_photo_runtime.sql), а перехода
-- pending -> published не делал НИКТО: у `requirement_reviews` его выполняет
-- админ руками в SQL-редакторе (service_role), для фотоконтроля такого шага
-- не было вовсе.
--
-- Владелец выбрал вариант «б»: публикует МОДЕРАТОР через экран `/moderation`,
-- автопубликации нет. Отсюда три части:
--   1) роль модератора — `profiles.is_moderator` + `public.is_moderator()`
--      (та же механика, что `profiles.is_subscribed` + `is_subscriber()`:
--      флаг ставит владелец руками SQL-ом, клиент себе включить не может —
--      колоночный грант `update` его не покрывает);
--   2) RPC `moderate_photo_finding_review` — единственный путь смены статуса
--      для не-service_role; прямой update модератору по-прежнему запрещён;
--   3) вью `photo_review_moderation_queue` — данные экрана модерации.
--
-- Append-only вердиктов (`photo_verdicts`, Задача 16) НЕ трогается: здесь
-- модерируются заключения юристов, а не вердикты движка.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Роль модератора
-- ----------------------------------------------------------------------------

-- Отдельной таблицы ролей в схеме нет (проверено: `lawyer_profiles.status` —
-- это про юриста, `profiles.is_subscribed` — про подписку), поэтому флаг живёт
-- на профиле — минимально инвазивно и по уже действующему в проекте образцу.
alter table public.profiles
  add column is_moderator boolean not null default false;

comment on column public.profiles.is_moderator is
  'Модератор заключений юристов. Ставится вручную владельцем (service_role): '
  'клиентский грант update покрывает только full_name/phone/company.';

-- Проверка «текущий пользователь — модератор» для политик и RPC.
-- SECURITY DEFINER по образцу is_subscriber()/is_verified_lawyer(): profiles
-- закрыт RLS-ом, а предикат нужен из контекста других объектов.
create or replace function public.is_moderator()
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
      and p.is_moderator
  );
$$;

revoke all on function public.is_moderator() from public;
-- Грант anon — для единообразия с is_subscriber()/is_verified_lawyer(): для
-- анонима функция всегда false (auth.uid() пуст), но политика, случайно
-- вычисленная в anon-контексте, не упадёт «permission denied for function».
grant execute on function public.is_moderator() to anon, authenticated;

-- ----------------------------------------------------------------------------
-- 2. Штампы модерации на заключении
-- ----------------------------------------------------------------------------

-- `published_at` в таблице уже есть (калька requirement_reviews). Нужны ещё
-- «кто» и «когда» — причём `moderated_at` отдельно от `published_at`, иначе у
-- отклонённого заключения не остаётся вообще никакой отметки времени.
alter table public.photo_finding_reviews
  add column moderated_by uuid references auth.users(id) on delete set null,
  add column moderated_at timestamptz;

comment on column public.photo_finding_reviews.moderated_by is
  'Модератор, принявший решение (RPC moderate_photo_finding_review).';

-- Статус — enum public.review_status ('pending' | 'published' | 'rejected',
-- 20260729013000_lawyer_reviews.sql), 'rejected' в нём уже есть: расширять
-- ничего не нужно, CHECK-констрейнта на колонке нет.

-- ----------------------------------------------------------------------------
-- 3. RLS: модератор ЧИТАЕТ pending, но не правит
-- ----------------------------------------------------------------------------

-- Permissive-политика складывается по OR с "owner reads published" / "lawyer
-- reads own" / "lawyer reads published" — ничего не заменяет и не сужает.
-- Только pending: опубликованное модератору как модератору уже не нужно
-- (очередь — pending-only), а лишний доступ к чужим текстам не выдаём.
create policy "moderator reads pending" on public.photo_finding_reviews
  for select to authenticated
  using (status = 'pending' and public.is_moderator());

-- Update-политики нет намеренно: грант `update` у authenticated отозван ещё в
-- 20260810100000_photo_runtime.sql (`revoke insert, update, delete … from anon,
-- authenticated`), а insert-грант колоночный и статус не покрывает. Значит
-- единственный путь модератора к смене статуса — RPC ниже.

-- ----------------------------------------------------------------------------
-- 4. RPC модерации
-- ----------------------------------------------------------------------------

-- SECURITY DEFINER: владелец функции ходит мимо RLS и грантов, поэтому
-- авторизация проверяется здесь явно, первой строкой. Переход разрешён
-- ТОЛЬКО из 'pending' — предикат в самом update: повторная модерация (в т.ч.
-- гонка двух вкладок) обновит 0 строк и получит ошибку, а не молча перепишет
-- чужое решение.
create or replace function public.moderate_photo_finding_review(
  p_review_id uuid,
  p_decision  text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_moderator uuid := (select auth.uid());
  v_updated   int;
begin
  if not public.is_moderator() then
    raise exception 'not_a_moderator';
  end if;

  if p_decision not in ('published', 'rejected') then
    raise exception 'bad_decision';
  end if;

  update public.photo_finding_reviews
     set status       = p_decision::public.review_status,
         moderated_by = v_moderator,
         moderated_at = now(),
         -- published_at ставим только на публикации и только если пусто
         published_at = case
                          when p_decision = 'published' then coalesce(published_at, now())
                          else published_at
                        end
   where id = p_review_id
     and status = 'pending';

  get diagnostics v_updated = row_count;
  if v_updated = 0 then
    raise exception 'review_not_pending';
  end if;
end;
$$;

revoke all on function public.moderate_photo_finding_review(uuid, text) from public;
revoke all on function public.moderate_photo_finding_review(uuid, text) from anon;
grant execute on function public.moderate_photo_finding_review(uuid, text) to authenticated;

-- ----------------------------------------------------------------------------
-- 5. Очередь модерации — данные экрана /moderation
-- ----------------------------------------------------------------------------

-- Точная калька `photo_finding_queue` (20260810120000_photo_review_queue.sql),
-- включая её Critical-фикс: `security_invoker = off` (вью читает чужие
-- проверки от владельца, мимо RLS), единственная граница безопасности — WHERE,
-- и в нём НЕ `auth.uid() is null` (у anon-ключа uid тоже пуст), а явная роль
-- `auth.role() = 'service_role'`.
create view public.photo_review_moderation_queue
with (security_invoker = off) as
select r.id           as review_id,
       r.finding_id,
       r.lawyer_id,
       r.verdict,
       r.comment_text,
       r.created_at,
       lp.display_name as lawyer_name,
       lp.credentials  as lawyer_credentials,
       f.inspection_id,
       f.checkpoint_id,
       f.rule_ref,
       f.severity,
       f.message,
       i.product_key,
       i.packaging_level
from public.photo_finding_reviews r
join public.lawyer_profiles lp   on lp.user_id = r.lawyer_id
join public.photo_findings f     on f.id = r.finding_id
join public.photo_inspections i  on i.id = f.inspection_id
where r.status = 'pending'
  and (public.is_moderator() or auth.role() = 'service_role');

grant select on public.photo_review_moderation_queue to authenticated;
-- Гигиена (как у остальных photo-объектов): default privileges Supabase
-- раздают гранты всем — снимаем явно, хотя вью с join и так не автообновляемая.
revoke insert, update, delete on public.photo_review_moderation_queue
  from anon, authenticated;

-- ── ФИКС ПОСЛЕ РЕВЬЮ (Important): anon-привилегия на очереди ────────────────
-- `grant select … to authenticated` НИЧЕГО НЕ СУЖАЕТ: default privileges
-- Supabase уже выдали select всем ролям на любую новую таблицу/вью в public.
-- То есть до этого ревока anon имел привилегию и на новую очередь модерации, и
-- на `photo_finding_queue` (20260810120000): от анонимного чтения там держал
-- ТОЛЬКО WHERE-предикат внутри вью, а комментарий той миграции («grant сужен до
-- authenticated», «anon вообще не получает select») описывал слой, которого не
-- существовало. Возвращаем второй слой явным ревоком — предикат остаётся, но
-- больше не единственный. Чужую миграцию не правим: ревок из более поздней
-- миграции корректен и накатывается тем же порядком.
revoke all on public.photo_review_moderation_queue from anon;
revoke all on public.photo_finding_queue from anon;

-- Minor того же ревью: `security_barrier` не даёт планировщику протащить
-- пользовательские (в т.ч. «текучие») предикаты PostgREST-запроса ВНУТРЬ вью,
-- под её собственный WHERE — то есть предикат безопасности гарантированно
-- вычисляется первым и не может протечь через дешёвую leaky-функцию в фильтре.
alter view public.photo_review_moderation_queue set (security_barrier = true);
alter view public.photo_finding_queue           set (security_barrier = true);

-- ----------------------------------------------------------------------------
-- 6. Сигнал модератору о новом заключении
-- ----------------------------------------------------------------------------

-- Без него очередь модерации надо опрашивать вручную — ровно та же дыра, что
-- закрывает `notify_admin_on_new_review` для requirement_reviews
-- (20260729013000). Образец соблюдён дословно: SECURITY DEFINER, любая ошибка —
-- warning, вставка заключения никогда не падает из-за уведомления.
create or replace function public.notify_admin_new_photo_review()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  lawyer_name text;
  finding_msg text;
  stamp       text := to_char(now() at time zone 'Asia/Tashkent', 'DD.MM.YYYY HH24:MI');
begin
  select display_name into lawyer_name
    from public.lawyer_profiles where user_id = new.lawyer_id;
  select message into finding_msg
    from public.photo_findings where id = new.finding_id;

  perform public.notify_admin_telegram(
    '📷 Заключение по находке фотоконтроля — на модерацию' || E'\n'
    || 'Юрист: '   || coalesce(lawyer_name, '—') || E'\n'
    || 'Вердикт: ' || new.verdict::text || E'\n'
    || 'Находка: ' || coalesce(left(finding_msg, 200), new.finding_id::text) || E'\n'
    || left(coalesce(new.comment_text, ''), 300) || E'\n'
    || stamp
  );
  return new;
exception when others then
  raise warning 'notify_admin_new_photo_review: %', sqlerrm;
  return new;
end;
$$;

revoke all on function public.notify_admin_new_photo_review() from public;
revoke all on function public.notify_admin_new_photo_review() from anon, authenticated;

create trigger notify_admin_on_new_photo_review
  after insert on public.photo_finding_reviews
  for each row execute function public.notify_admin_new_photo_review();
