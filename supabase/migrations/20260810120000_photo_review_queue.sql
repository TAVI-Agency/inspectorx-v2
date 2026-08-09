-- Очередь юриста по находкам фотоконтроля — по образцу /lawyer/queue (ADR-0001,
-- поправка 5). security_invoker = off: вью выполняется от владельца, RLS
-- нижележащих таблиц не участвует — единственная граница безопасности здесь
-- это сам WHERE. `distinct on (f.id) … order by f.id, a.created_at` — защита
-- от дублей строки при повторной эскалации одной и той же находки (нет
-- уникального индекса на `photo_finding_actions (finding_id, action)`,
-- значит `record_finding_action('escalated')` можно вызвать дважды): вью
-- берёт ПЕРВУЮ эскалацию (минимальный created_at), а не плодит вторую строку
-- на ту же находку.
--
-- ФИКС ПОСЛЕ РЕВЬЮ (Critical): было `(select auth.uid()) is null` как эскейп
-- для service_role — но у anon-ключа `auth.uid()` тоже null (в JWT нет claim
-- `sub`), поэтому вместе с `grant select … to anon` вью читалась анонимно
-- (подтверждено живым прогоном: anon-select вернул чужую находку). Заменено
-- на явную проверку роли `auth.role() = 'service_role'` (штатная обёртка
-- Supabase над `request.jwt.claims->>'role'`, отличает anon/authenticated/
-- service_role по факту роли, а не по отсутствию claim'а) + grant сужен до
-- `authenticated` (anon вообще не получает select).
create view public.photo_finding_queue
with (security_invoker = off) as
select distinct on (f.id)
       f.id as finding_id,
       f.inspection_id,
       f.checkpoint_id,
       f.rule_ref,
       f.severity,
       f.status,
       f.message,
       i.product_key,
       i.packaging_level,
       a.created_at as escalated_at
from public.photo_findings f
join public.photo_inspections i on i.id = f.inspection_id
join public.photo_finding_actions a
  on a.finding_id = f.id and a.action = 'escalated'
where (public.is_verified_lawyer() or auth.role() = 'service_role')
  and not exists (
    select 1 from public.photo_finding_reviews r
    where r.finding_id = f.id and r.status = 'published')
order by f.id, a.created_at;

grant select on public.photo_finding_queue to authenticated;
-- Гигиена (как у остальных photo-таблиц в 20260810100000_photo_runtime.sql):
-- Supabase default privileges раздают гранты всем — снимаем явно, хотя вью
-- с join и так не автообновляемая (Postgres откажет в insert/update/delete
-- без INSTEAD OF-триггера) — это второй, defence-in-depth слой.
revoke insert, update, delete on public.photo_finding_queue from anon, authenticated;

-- ── Юрист читает ЧУЖОЙ отчёт для подписи (решение владельца поверх брифа) ───
-- Кнопка «Подписать вердикт» на /checks/packaging/:id (Задача 14) нуждается в
-- полном bundle (inspection + findings + notCheckable + assets + events +
-- facts) чужой проверки — «own read» из 20260810100000_photo_runtime.sql даёт
-- select только владельцу. Ниже — ДОПОЛНИТЕЛЬНЫЕ permissive-политики только
-- на select (складываются с "own read" через OR, не заменяют её); insert/
-- update/delete для authenticated по-прежнему отозваны на уровне грантов той
-- миграции (`revoke insert, update, delete … from anon, authenticated`) —
-- писать чужие данные юрист не может ни при каком предикате RLS. Файл Task 8
-- не трогаем — политики живут здесь, в миграции очереди юриста.
-- Storage (evidence-crops) сознательно не тронут: подписанные URL кропов для
-- юриста — вне Волны 1; `useEvidenceCropUrls` на чужом инспекшне просто не
-- получит ссылки (запрос уйдёт в error, `cropUrls.data` останется undefined),
-- карточка находки рендерится без картинки — деградация без падения.
create policy "lawyer reads for signing" on public.photo_inspections
  for select to authenticated using (public.is_verified_lawyer());

create policy "lawyer reads for signing" on public.photo_findings
  for select to authenticated using (public.is_verified_lawyer());

create policy "lawyer reads for signing" on public.photo_not_checkable
  for select to authenticated using (public.is_verified_lawyer());

create policy "lawyer reads for signing" on public.photo_assets
  for select to authenticated using (public.is_verified_lawyer());

create policy "lawyer reads for signing" on public.photo_inspection_events
  for select to authenticated using (public.is_verified_lawyer());

create policy "lawyer reads for signing" on public.photo_facts
  for select to authenticated using (public.is_verified_lawyer());

-- MINOR (ревью): без этого блок «Заключения юристов» в чужом отчёте
-- (CPackagingReportPage.tsx, fetchFindingReviews) был бы пустым для юриста —
-- существующие политики photo_finding_reviews дают select только владельцу
-- проверки ("owner reads published") или самому автору заключения ("lawyer
-- reads own", туда входит и pending). Публикация — премодерация владельцем
-- (service_role), поэтому published-заключения ЛЮБОГО юриста безопасно
-- показать ЛЮБОМУ verified-юристу — то же решение, что уже действует для
-- лендинга/каталога через is_verified_lawyer() в 20260729013000_lawyer_reviews.sql.
create policy "lawyer reads published" on public.photo_finding_reviews
  for select to authenticated using (status = 'published' and public.is_verified_lawyer());
