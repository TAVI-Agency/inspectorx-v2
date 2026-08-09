-- Сокращённый режим (§6, ступень 2 деградации VLM): оба провайдера недоступны,
-- прогон выполнен только детерминированными источниками -> списывается ПОЛОВИНА
-- единицы квоты, а не целая. Поверх finalize_photo_inspection Волны 1
-- (20260810100000_photo_runtime.sql).

-- used становится numeric, чтобы половина была числом, а не легендой.
alter table public.photo_quota
  alter column used type numeric(6,1) using used::numeric(6,1);

-- Перегрузка финализации: p_degraded_mode — ПЯТЫЙ, ОБЯЗАТЕЛЬНЫЙ параметр (без
-- default), отдельная сигнатура от исходной finalize_photo_inspection(uuid,
-- text, text, jsonb) Волны 1. Без обязательности звонок с четырьмя
-- аргументами стал бы неоднозначным между двумя перегрузками ("function is
-- not unique"); так вызовы без пятого параметра однозначно уходят в исходную
-- функцию, а вызовы серверной части витрины (с p_degraded_mode) — в эту.
-- Тело — как в исходной finalize_photo_inspection Волны 1, но при
-- p_outcome='done' and p_degraded_mode='local_only' квота списывается 0.5
-- вместо 1 (единственная правка — строка списания used в ветке v_holds_reserve).
-- Исходная функция сохраняется без изменений — обратная совместимость вызовов
-- без параметра (реперная джоба reap_stale_inspections, create_photo_revision
-- и любой прежний код, который его не знает).
create or replace function public.finalize_photo_inspection(
  p_inspection_id uuid, p_outcome text, p_reason text, p_payload jsonb,
  p_degraded_mode text)
returns void
language plpgsql security definer set search_path = public
as $$
declare
  v public.photo_inspections%rowtype;
  v_period date;
  v_holds_reserve boolean;
  refundable constant text[] := array[
    'worker_unreachable', 'worker_timeout', 'dispatch_lost',
    'ruleset_drift', 'ocr_unavailable', 'vlm_unavailable'];
begin
  select * into v from public.photo_inspections
   where id = p_inspection_id for update;
  if not found then raise exception 'inspection_not_found'; end if;
  if v.status not in ('queued', 'running') then return; end if;  -- идемпотентно
  v_period := date_trunc('month', v.created_at)::date;
  v_holds_reserve := v.revision = 1;

  if p_outcome = 'done' then
    update public.photo_inspections set
      status = 'done', checked_at = now(), last_error = null,
      overall          = p_payload ->> 'overall',
      decided          = (p_payload ->> 'decided')::int,
      checked          = (p_payload ->> 'checked')::int,
      reader_coverage  = p_payload -> 'reader_coverage',
      policy_applied   = p_payload -> 'policy_applied',
      extraction_errors = p_payload -> 'extraction_errors',
      degraded_mode    = p_payload ->> 'degraded_mode',
      prompt_version   = p_payload ->> 'prompt_version',
      model_versions   = p_payload -> 'model_versions',
      evaluated_at     = nullif(p_payload ->> 'evaluated_at', '')::timestamptz,
      cost_usd         = coalesce((p_payload ->> 'cost_usd')::numeric, 0)
    where id = p_inspection_id;

    insert into public.photo_findings
      (inspection_id, checkpoint_id, requirement_id, rule_ref, group_key, surface,
       kind, severity, status, decided_by, confidence_class, message, basis,
       recommendation, evidence, evidence_crop_path)
    select p_inspection_id, f ->> 'checkpoint_id',
           nullif(f ->> 'requirement_id', '')::uuid,
           f ->> 'rule_ref', f ->> 'group_key', coalesce(f ->> 'surface', 'any_panel'),
           f ->> 'kind', f ->> 'severity', f ->> 'status',
           coalesce(f ->> 'decided_by', 'none'),
           coalesce(f ->> 'confidence_class', 'needs_human'),
           coalesce(f ->> 'message', ''), coalesce(f ->> 'basis', ''),
           f ->> 'recommendation', coalesce(f -> 'evidence', '[]'::jsonb),
           f ->> 'evidence_crop_path'
    from jsonb_array_elements(coalesce(p_payload -> 'findings', '[]'::jsonb)) f;

    insert into public.photo_not_checkable (inspection_id, checkpoint_key, rule_ref, reason, class)
    select p_inspection_id, n ->> 'checkpoint_key', coalesce(n ->> 'rule_ref', ''),
           n ->> 'reason', n ->> 'klass'
    from jsonb_array_elements(coalesce(p_payload -> 'not_checkable', '[]'::jsonb)) n;

    insert into public.photo_facts (inspection_id, revision, slot_id, payload, source,
                                    confidence, asset_idx, bbox)
    select p_inspection_id, v.revision, r ->> 'slot_id',
           coalesce(r -> 'payload', '{}'::jsonb), r ->> 'source',
           (r ->> 'confidence')::real, (r ->> 'asset_idx')::int, r -> 'bbox'
    from jsonb_array_elements(coalesce(p_payload -> 'facts', '[]'::jsonb)) r;

    insert into public.photo_model_calls (inspection_id, stage, provider, model,
                                          tokens_in, tokens_out, latency_ms, cost_usd)
    select p_inspection_id, m ->> 'stage', coalesce(m ->> 'provider', ''),
           coalesce(m ->> 'model', ''), coalesce((m ->> 'tokens_in')::int, 0),
           coalesce((m ->> 'tokens_out')::int, 0), coalesce((m ->> 'latency_ms')::int, 0),
           coalesce((m ->> 'cost_usd')::numeric, 0)
    from jsonb_array_elements(coalesce(p_payload -> 'model_calls', '[]'::jsonb)) m;

    update public.photo_assets a set
      sha256 = x.sha256, width = x.width, height = x.height, mime = x.mime,
      face_name = x.face_name, usable = x.usable, problems = x.problems
    from (select (e ->> 'idx')::int idx, e ->> 'sha256' sha256,
                 (e ->> 'width')::int width, (e ->> 'height')::int height,
                 e ->> 'mime' mime, coalesce(e ->> 'face_name', 'unknown') face_name,
                 coalesce((e ->> 'usable')::boolean, true) usable,
                 coalesce(e -> 'problems', '[]'::jsonb) problems
          from jsonb_array_elements(coalesce(p_payload -> 'assets', '[]'::jsonb)) e) x
    where a.inspection_id = p_inspection_id and a.idx = x.idx;

    if v_holds_reserve then
      -- Единственная правка тела относительно исходной функции (план §6,
      -- ступень 2): local_only списывает половину единицы квоты — прогон
      -- состоялся, но только детерминированными источниками, без VLM.
      update public.photo_quota set reserved = greatest(reserved - 1, 0),
        used = used + (case when p_degraded_mode = 'local_only' then 0.5 else 1 end),
        spent_usd = spent_usd + coalesce((p_payload ->> 'cost_usd')::numeric, 0)
      where user_id = v.user_id and period_start = v_period;
    else
      -- Досъёмка/пересуд единицы квоты не стоят, но деньги за прогон реальные —
      -- учитываем только расход.
      update public.photo_quota
        set spent_usd = spent_usd + coalesce((p_payload ->> 'cost_usd')::numeric, 0)
      where user_id = v.user_id and period_start = v_period;
    end if;

  elsif p_outcome = 'failed' then
    update public.photo_inspections
      set status = 'failed', checked_at = now(), last_error = p_reason
      where id = p_inspection_id;
    if not v_holds_reserve then
      null;   -- нечего возвращать и нечего списывать
    elsif p_reason = any (refundable) then
      -- возврат — только по закрытому списку причин и не больше 3 за период
      update public.photo_quota
        set reserved = greatest(reserved - 1, 0),
            refunds_used = refunds_used + 1
        where user_id = v.user_id and period_start = v_period and refunds_used < 3;
      if not found then
        update public.photo_quota
          set reserved = greatest(reserved - 1, 0), used = used + 1
          where user_id = v.user_id and period_start = v_period;
      end if;
    else
      -- отказ по данным (no_text_layer, asset_fetch_failed, checklist_empty…)
      update public.photo_quota
        set reserved = greatest(reserved - 1, 0), used = used + 1
        where user_id = v.user_id and period_start = v_period;
    end if;
  else
    raise exception 'bad_outcome';
  end if;

  insert into public.photo_inspection_events (inspection_id, stage, detail)
  values (p_inspection_id,
          case when p_outcome = 'done' then 'done' else 'failed' end,
          jsonb_build_object('reason', p_reason));
end;
$$;
revoke all on function public.finalize_photo_inspection(uuid, text, text, jsonb, text) from public;
revoke all on function public.finalize_photo_inspection(uuid, text, text, jsonb, text) from anon, authenticated;
grant execute on function public.finalize_photo_inspection(uuid, text, text, jsonb, text) to service_role;
