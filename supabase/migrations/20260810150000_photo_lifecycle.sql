-- Устаревание вердиктов при изменении нормы (план §2 шаг 7; этап 7, код).
-- До полного этапа 6 requirement_id заполнен у малой доли находок (мост) —
-- механизм честно покрывает только их; функция не продаётся до этапа 6 (риск 13).
--
-- Идемпотентность: unique-индекс на (user_id, requirement_id, payload->>'inspection')
-- для kind='checklist_version' — тот же паттерн, что и user_notifications_lifecycle_uidx
-- (20260804100000_lifecycle_cron.sql). Ни один вердикт (photo_findings) не
-- изменяется — только photo_inspections.stale_since (append-only инвариант плана).
create unique index if not exists user_notifications_checklist_version_uidx
  on public.user_notifications (user_id, requirement_id, ((payload ->> 'inspection')))
  where kind = 'checklist_version';

comment on index public.user_notifications_checklist_version_uidx is
  'Идемпотентность flag_stale_photo_inspections(): повторный прогон на уже '
  'помеченную проверку не заводит вторую строку — INSERT … ON CONFLICT DO NOTHING.';

create or replace function public.flag_stale_photo_inspections()
returns int
language plpgsql security definer set search_path = public
as $$
declare
  n int;
begin
  with affected as (
    select distinct i.id as inspection_id, i.user_id, f.requirement_id,
           ce.effective_date
    from public.photo_findings f
    join public.photo_inspections i on i.id = f.inspection_id and i.status = 'done'
    join public.requirement_change_impacts imp
      on imp.requirement_id = f.requirement_id
     and imp.status in ('pending_review', 'confirmed')
    join public.change_events ce on ce.id = imp.change_event_id
    where f.requirement_id is not null
      and ce.effective_date is not null
      and i.stale_since is null
  ),
  marked as (
    update public.photo_inspections i
       set stale_since = a.effective_date
      from affected a
     where i.id = a.inspection_id
    returning i.id, i.user_id
  )
  insert into public.user_notifications (user_id, requirement_id, kind, payload)
  select a.user_id, a.requirement_id, 'checklist_version',
         jsonb_build_object('inspection', a.inspection_id::text,
                            'effective_date', a.effective_date)
  from affected a
  on conflict (user_id, requirement_id, ((payload ->> 'inspection')))
    where kind = 'checklist_version'
  do nothing;

  get diagnostics n = row_count;
  return n;
end;
$$;

comment on function public.flag_stale_photo_inspections() is
  'Этап 7 (план): проверка done, чья находка ссылается на requirement_id с '
  'подтверждённым/ожидающим review impact-ом изменения нормы, метится '
  'stale_since = дата вступления изменения в силу; заводится уведомление '
  'user_notifications(kind=checklist_version). Вердикты (photo_findings) не '
  'трогаются — только photo_inspections.stale_since. Идемпотентно (условие '
  'i.stale_since is null + ON CONFLICT DO NOTHING). Вызывается только '
  'cron-джобом ниже и service_role — не выдана anon/authenticated.';

revoke all on function public.flag_stale_photo_inspections() from public;
revoke all on function public.flag_stale_photo_inspections() from anon, authenticated;
grant execute on function public.flag_stale_photo_inspections() to service_role;

-- Расписание: 03:15 UTC каждый день — после lifecycle-transitions (03:00,
-- 20260804100000_lifecycle_cron.sql), тот же паттерн обёртки-проверки.
do $$
begin
  if not exists (select 1 from cron.job where jobname = 'photo-stale-flag') then
    perform cron.schedule('photo-stale-flag', '15 3 * * *',
      $cron$select public.flag_stale_photo_inspections()$cron$);
  end if;
end;
$$;
