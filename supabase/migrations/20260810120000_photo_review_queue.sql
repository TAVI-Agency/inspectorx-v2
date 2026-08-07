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
