-- Очередь юриста по находкам фотоконтроля — по образцу /lawyer/queue (ADR-0001,
-- поправка 5). security_invoker = off + предикат is_verified_lawyer() внутри:
-- клиенту-не-юристу вью отдаёт ноль строк, service_role видит всё.
create view public.photo_finding_queue
with (security_invoker = off) as
select f.id as finding_id,
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
where (public.is_verified_lawyer() or (select auth.uid()) is null)
  and not exists (
    select 1 from public.photo_finding_reviews r
    where r.finding_id = f.id and r.status = 'published');

grant select on public.photo_finding_queue to anon, authenticated;

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
