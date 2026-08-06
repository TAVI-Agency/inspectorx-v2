-- Рантайм фотоконтроля упаковки (Волна 1; нормативный план docs/PHOTOCONTROL_INTEGRATION_PLAN.md §4).
-- Схема public, не pipeline: фотоконтроль — контур B (рантайм), его читает пользователь.
-- ПРОД: pg_cron и pg_net уже включены (20260804100000, 20260727120000); на свежем
-- проде pg_cron сперва разрешается в Dashboard (см. комментарий в 20260804100000).
create extension if not exists pg_cron;
create extension if not exists pg_net;

-- ── 1. Реестр версий набора правил (план §3) ────────────────────────────────
create table public.ruleset_versions (
  sha256       text primary key,
  version      text not null,
  built_at     timestamptz not null default now(),
  packs        jsonb not null default '{}'::jsonb,
  checks_count int not null default 0,
  is_current   boolean not null default false
);
create unique index ruleset_versions_current_uidx
  on public.ruleset_versions (is_current) where is_current;

alter table public.ruleset_versions enable row level security;
create policy "public read" on public.ruleset_versions
  for select to anon, authenticated using (true);
revoke insert, update, delete on public.ruleset_versions from anon, authenticated;

-- ── 2. Профили движка: какому товару собран чек-лист ────────────────────────
-- До этапа-6-выгрузки профили заданы HS-префиксами трёх категорий vision.
create table public.photo_profiles (
  profile_id  text primary key,        -- id профиля движка (config/products/*.yaml)
  title_ru    text not null,
  hs_prefixes text[] not null
);
insert into public.photo_profiles (profile_id, title_ru, hs_prefixes) values
  ('tobacco',     'Табачная продукция',  '{2402,2403}'),
  ('dairy',       'Молочная продукция',  '{0401,0402,0403,0404,0405,0406}'),
  ('electronics', 'Бытовая электроника', '{84,85}');

alter table public.photo_profiles enable row level security;
create policy "public read" on public.photo_profiles
  for select to anon, authenticated using (true);
revoke insert, update, delete on public.photo_profiles from anon, authenticated;

create or replace function public.photo_profile_for_product(p_product_id uuid)
returns text
language sql stable security definer set search_path = public
as $$
  select pp.profile_id
  from public.products p
  join public.photo_profiles pp
    on exists (select 1 from unnest(pp.hs_prefixes) pref
               where p.hs_code like pref || '%')
  where p.id = p_product_id
  limit 1;
$$;
revoke all on function public.photo_profile_for_product(uuid) from public;
grant execute on function public.photo_profile_for_product(uuid) to anon, authenticated;

-- ── 3. Проверки ─────────────────────────────────────────────────────────────
create table public.photo_inspections (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users(id) on delete cascade,
  product_id       uuid references public.products(id) on delete set null,
  product_key      text not null,      -- профиль движка (tobacco|dairy|electronics)
  packaging_level  text not null check (packaging_level in ('consumer', 'transport')),
  markets          text[] not null default '{UZ}',
  source_kind      text not null check (source_kind in ('photo', 'master_pdf')),
  status           text not null default 'queued'
                     check (status in ('queued', 'running', 'done', 'failed')),
  idempotency_key  text not null,
  heartbeat_at     timestamptz,
  overall          text,
  decided          int,
  checked          int,
  revision         int not null default 1 check (revision between 1 and 3),
  superseded_by    uuid references public.photo_inspections(id),
  stale_since      date,
  ruleset_version  text,
  ruleset_sha256   text not null references public.ruleset_versions(sha256),
  policy_applied   jsonb,
  prompt_version   text,
  model_versions   jsonb,
  reader_coverage  jsonb,
  extraction_errors jsonb,
  degraded_mode    text,
  evaluated_at     timestamptz,
  checked_at       timestamptz,
  cost_usd         numeric(10,6),
  signed_by        uuid references auth.users(id),
  signed_at        timestamptz,
  attempts         int not null default 0 check (attempts <= 2),
  last_error       text,
  created_at       timestamptz not null default now(),
  -- ключ уникален В ПРЕДЕЛАХ пользователя: одинаковый макет у двух клиентов —
  -- две независимые проверки (план §4 задаёт состав ключа, охват — наш выбор)
  unique (user_id, idempotency_key)
);
create index photo_inspections_user_idx
  on public.photo_inspections (user_id, created_at desc);
create index photo_inspections_stale_idx
  on public.photo_inspections (status) where status in ('queued', 'running');

create table public.photo_inspection_events (
  id            bigint generated always as identity primary key,
  inspection_id uuid not null references public.photo_inspections(id) on delete cascade,
  at            timestamptz not null default now(),
  stage         text not null check (stage in
                  ('received', 'prepare', 'read', 'judge', 'render', 'done', 'failed')),
  detail        jsonb not null default '{}'::jsonb
);
create index photo_inspection_events_idx
  on public.photo_inspection_events (inspection_id, at);

create table public.photo_assets (
  inspection_id uuid not null references public.photo_inspections(id) on delete cascade,
  idx           int not null,
  kind          text not null check (kind in ('photo', 'master_pdf')),
  storage_path  text not null,
  sha256        text,
  width         int,
  height        int,
  mime          text,
  face_name     text not null default 'unknown',
  usable        boolean not null default true,
  problems      jsonb not null default '[]'::jsonb,
  purged_at     timestamptz,
  primary key (inspection_id, idx)
);

create table public.photo_findings (
  id               uuid primary key default gen_random_uuid(),
  inspection_id    uuid not null references public.photo_inspections(id) on delete cascade,
  checkpoint_id    text not null,
  requirement_id   uuid references public.requirements(id) on delete set null,
  rule_ref         text not null,
  group_key        text not null,
  surface          text not null default 'any_panel',
  kind             text not null,
  severity         text not null,
  status           text not null check (status in ('pass', 'fail', 'unreadable', 'not_applicable')),
  decided_by       text not null default 'none',
  confidence_class text not null default 'needs_human'
                     check (confidence_class in ('machine_read', 'needs_human', 'not_checkable')),
  message          text not null default '',
  basis            text not null default '',
  recommendation   text,
  evidence         jsonb not null default '[]'::jsonb,
  evidence_crop_path text
);
create index photo_findings_inspection_idx on public.photo_findings (inspection_id);
create index photo_findings_requirement_idx
  on public.photo_findings (requirement_id) where requirement_id is not null;

create table public.photo_not_checkable (
  id             bigint generated always as identity primary key,
  inspection_id  uuid not null references public.photo_inspections(id) on delete cascade,
  checkpoint_key text not null,
  rule_ref       text not null default '',
  reason         text not null,
  class          text not null check (class in
                   ('метод', 'нет данных о товаре', 'нет эталона', 'нет чтеца'))
);
create index photo_not_checkable_idx on public.photo_not_checkable (inspection_id);

create table public.photo_facts (
  id            bigint generated always as identity primary key,
  inspection_id uuid not null references public.photo_inspections(id) on delete cascade,
  revision      int not null default 1,
  slot_id       text not null,
  payload       jsonb not null default '{}'::jsonb,
  -- 'system' — не источник факта, а служебная строка паспорта (__scan__ и т.п.)
  source        text not null check (source in
                  ('yolo', 'ocr', 'zbar', 'pdf_text', 'vlm', 'human', 'system')),
  confidence    real,
  asset_idx     int,
  bbox          jsonb
);
create index photo_facts_idx on public.photo_facts (inspection_id, revision);

create table public.photo_fact_overrides (
  id             uuid primary key default gen_random_uuid(),
  inspection_id  uuid not null references public.photo_inspections(id) on delete cascade,
  slot_id        text not null,
  payload        jsonb not null,
  author_user_id uuid not null references auth.users(id) on delete cascade,
  note           text not null default '',
  created_at     timestamptz not null default now()
);
create index photo_fact_overrides_idx on public.photo_fact_overrides (inspection_id);

create table public.photo_finding_actions (
  id         uuid primary key default gen_random_uuid(),
  finding_id uuid not null references public.photo_findings(id) on delete cascade,
  user_id    uuid not null references auth.users(id) on delete cascade,
  action     text not null check (action in ('fixed', 'accepted_with_reason', 'escalated')),
  reason     text,
  created_at timestamptz not null default now(),
  -- у «принять с обоснованием» обязателен текст (план §7)
  constraint action_reason_required
    check (action <> 'accepted_with_reason' or length(coalesce(reason, '')) >= 10)
);
create index photo_finding_actions_idx on public.photo_finding_actions (finding_id);

-- Калька requirement_reviews (20260729013000): заключение юриста ПО НАХОДКЕ.
-- Существующая таблица непригодна: not null FK на requirements (поправка 5 к ADR-0001).
create table public.photo_finding_reviews (
  id                  uuid primary key default gen_random_uuid(),
  finding_id          uuid not null references public.photo_findings(id) on delete cascade,
  lawyer_id           uuid not null references public.lawyer_profiles(user_id) on delete cascade,
  verdict             public.review_verdict not null,
  comment_text        text not null,
  status              public.review_status not null default 'pending',
  official_reply      text,
  official_replied_at timestamptz,
  published_at        timestamptz,
  created_at          timestamptz not null default now()
);
create index photo_finding_reviews_finding_idx
  on public.photo_finding_reviews (finding_id, status);
create unique index photo_finding_reviews_pending_uidx
  on public.photo_finding_reviews (lawyer_id, finding_id) where status = 'pending';

create table public.photo_model_calls (
  id            bigint generated always as identity primary key,
  inspection_id uuid not null references public.photo_inspections(id) on delete cascade,
  stage         text not null check (stage in ('pdf_text', 'ocr', 'vlm_shard', 'vlm_reask')),
  provider      text not null default '',
  model         text not null default '',
  tokens_in     int not null default 0,
  tokens_out    int not null default 0,
  latency_ms    int not null default 0,
  cost_usd      numeric(10, 6) not null default 0
);
create index photo_model_calls_idx on public.photo_model_calls (inspection_id);

create table public.photo_quota (
  user_id      uuid not null references auth.users(id) on delete cascade,
  period_start date not null,
  used         int not null default 0,
  reserved     int not null default 0,
  refunds_used int not null default 0,
  limit_n      int not null default 5,    -- закрытая бета: 5 проверок / 30 дней (развилка 12)
  spent_usd    numeric(10, 4) not null default 0,
  primary key (user_id, period_start)
);

-- ── 4. RLS: select только own; запись — только service_role (план §4) ───────
-- Default privileges Supabase выдают гранты всем — снимаем явно.
alter table public.photo_inspections       enable row level security;
alter table public.photo_inspection_events enable row level security;
alter table public.photo_assets            enable row level security;
alter table public.photo_findings          enable row level security;
alter table public.photo_not_checkable     enable row level security;
alter table public.photo_facts             enable row level security;
alter table public.photo_fact_overrides    enable row level security;
alter table public.photo_finding_actions   enable row level security;
alter table public.photo_finding_reviews   enable row level security;
alter table public.photo_model_calls       enable row level security;
alter table public.photo_quota             enable row level security;

revoke insert, update, delete on public.photo_inspections,
  public.photo_inspection_events, public.photo_assets, public.photo_findings,
  public.photo_not_checkable, public.photo_facts, public.photo_fact_overrides,
  public.photo_finding_actions, public.photo_finding_reviews,
  public.photo_model_calls, public.photo_quota
  from anon, authenticated;

create policy "own read" on public.photo_inspections
  for select to authenticated using (user_id = (select auth.uid()));

create policy "own read" on public.photo_inspection_events
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_assets
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_findings
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_not_checkable
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_facts
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_fact_overrides
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_finding_actions
  for select to authenticated using (exists (
    select 1 from public.photo_findings f
    join public.photo_inspections i on i.id = f.inspection_id
    where f.id = finding_id and i.user_id = (select auth.uid())));

-- Заключения: владелец проверки видит опубликованные, юрист — свои.
create policy "owner reads published" on public.photo_finding_reviews
  for select to authenticated using (
    status = 'published' and exists (
      select 1 from public.photo_findings f
      join public.photo_inspections i on i.id = f.inspection_id
      where f.id = finding_id and i.user_id = (select auth.uid())));
create policy "lawyer reads own" on public.photo_finding_reviews
  for select to authenticated using (lawyer_id = (select auth.uid()));
-- Осознанное исключение из «пишет только service_role»: калька контура ADR-0001 —
-- verified-юрист вставляет заключение сам, статус всегда default 'pending'.
grant insert (finding_id, lawyer_id, verdict, comment_text)
  on public.photo_finding_reviews to authenticated;
create policy "verified lawyer insert" on public.photo_finding_reviews
  for insert to authenticated
  with check (lawyer_id = (select auth.uid()) and public.is_verified_lawyer());

create policy "own read" on public.photo_model_calls
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_quota
  for select to authenticated using (user_id = (select auth.uid()));

-- ── 5. RPC: единственный вход (план §4) ─────────────────────────────────────
create or replace function public.request_photo_inspection(
  p_product_id uuid, p_level text, p_markets text[], p_source_kind text,
  p_asset_paths text[], p_idempotency_key text)
returns uuid
language plpgsql security definer set search_path = public
as $$
declare
  v_uid     uuid := (select auth.uid());
  v_profile text;
  v_sha     text;
  v_version text;
  v_period  date := date_trunc('month', now())::date;
  v_id      uuid;
  v_path    text;
  v_i       int := 0;
begin
  if v_uid is null then raise exception 'not_authenticated'; end if;
  if not public.is_subscriber() then raise exception 'not_subscriber'; end if;
  if p_source_kind not in ('photo', 'master_pdf') then raise exception 'bad_source_kind'; end if;
  if p_level not in ('consumer', 'transport') then raise exception 'bad_level'; end if;
  if p_source_kind = 'photo' and coalesce(array_length(p_asset_paths, 1), 0) < 4 then
    raise exception 'need_four_photos';   -- первый ключ покрытия (план §2Б шаг 3)
  end if;
  if p_source_kind = 'master_pdf' and coalesce(array_length(p_asset_paths, 1), 0) <> 1 then
    raise exception 'need_single_pdf';
  end if;
  foreach v_path in array p_asset_paths loop
    if position(v_uid::text || '/' in v_path) <> 1 then
      raise exception 'foreign_path';     -- путь обязан начинаться с <uid>/
    end if;
  end loop;

  v_profile := public.photo_profile_for_product(p_product_id);
  if v_profile is null then raise exception 'no_checklist'; end if;

  select sha256, version into v_sha, v_version
    from public.ruleset_versions where is_current;
  if v_sha is null then raise exception 'no_ruleset'; end if;

  -- идемпотентность: тот же ключ → та же проверка, без второго резерва
  select id into v_id from public.photo_inspections
   where user_id = v_uid and idempotency_key = p_idempotency_key;
  if v_id is not null then return v_id; end if;

  -- атомарный резерв квоты (не count(*): гонка на границе лимита)
  insert into public.photo_quota as q (user_id, period_start, reserved)
  values (v_uid, v_period, 1)
  on conflict (user_id, period_start) do update
    set reserved = q.reserved + 1
    where q.used + q.reserved < q.limit_n;
  if not found then raise exception 'quota_exhausted'; end if;

  insert into public.photo_inspections
    (user_id, product_id, product_key, packaging_level, markets, source_kind,
     idempotency_key, ruleset_sha256, ruleset_version)
  values (v_uid, p_product_id, v_profile, p_level, p_markets, p_source_kind,
          p_idempotency_key, v_sha, v_version)
  returning id into v_id;

  foreach v_path in array p_asset_paths loop
    insert into public.photo_assets (inspection_id, idx, kind, storage_path, mime)
    values (v_id, v_i, p_source_kind,
            v_path, case when p_source_kind = 'master_pdf'
                         then 'application/pdf' else 'image/jpeg' end);
    v_i := v_i + 1;
  end loop;

  insert into public.photo_inspection_events (inspection_id, stage, detail)
  values (v_id, 'received', jsonb_build_object('assets', v_i));
  return v_id;
end;
$$;
revoke all on function public.request_photo_inspection(uuid, text, text[], text, text[], text) from public;
grant execute on function public.request_photo_inspection(uuid, text, text[], text, text[], text) to authenticated;

-- Досъёмка: та же проверка, revision+1, БЕЗ нового резерва (план §6 механизм 5).
create or replace function public.request_photo_retake(
  p_inspection_id uuid, p_new_asset_paths text[], p_idempotency_key text)
returns uuid
language plpgsql security definer set search_path = public
as $$
declare
  v_uid  uuid := (select auth.uid());
  parent public.photo_inspections%rowtype;
  v_id   uuid;
  v_path text;
  v_i    int;
begin
  select * into parent from public.photo_inspections
   where id = p_inspection_id and user_id = v_uid;
  if not found then raise exception 'inspection_not_found'; end if;
  if parent.source_kind <> 'photo' then raise exception 'retake_is_for_photos'; end if;
  if parent.status <> 'done' then raise exception 'parent_not_done'; end if;
  if parent.revision >= 3 then
    raise exception 'revision_limit';     -- четвёртая досъёмка = новая единица квоты
  end if;
  foreach v_path in array p_new_asset_paths loop
    if position(v_uid::text || '/' in v_path) <> 1 then raise exception 'foreign_path'; end if;
  end loop;

  insert into public.photo_inspections
    (user_id, product_id, product_key, packaging_level, markets, source_kind,
     idempotency_key, ruleset_sha256, ruleset_version, revision)
  select p.user_id, p.product_id, p.product_key, p.packaging_level, p.markets, p.source_kind,
         p_idempotency_key, r.sha256, r.version, parent.revision + 1
  from public.photo_inspections p, public.ruleset_versions r
  where p.id = p_inspection_id and r.is_current
  returning id into v_id;

  -- старые кадры переезжают в новую ревизию (переиспользуются, не переизвлекаются)
  insert into public.photo_assets (inspection_id, idx, kind, storage_path, sha256,
                                   width, height, mime, face_name, usable, problems)
  select v_id, idx, kind, storage_path, sha256, width, height, mime, face_name, usable, problems
  from public.photo_assets where inspection_id = p_inspection_id;

  select coalesce(max(idx) + 1, 0) into v_i
    from public.photo_assets where inspection_id = v_id;
  foreach v_path in array p_new_asset_paths loop
    insert into public.photo_assets (inspection_id, idx, kind, storage_path, mime)
    values (v_id, v_i, 'photo', v_path, 'image/jpeg');
    v_i := v_i + 1;
  end loop;

  update public.photo_inspections set superseded_by = v_id where id = p_inspection_id;
  insert into public.photo_inspection_events (inspection_id, stage, detail)
  values (v_id, 'received', jsonb_build_object('retake_of', p_inspection_id));
  return v_id;
end;
$$;
revoke all on function public.request_photo_retake(uuid, text[], text) from public;
grant execute on function public.request_photo_retake(uuid, text[], text) to authenticated;

-- ── 6. Финализация: единственная точка перехода done|failed (план §4) ───────
create or replace function public.finalize_photo_inspection(
  p_inspection_id uuid, p_outcome text, p_reason text default null,
  p_payload jsonb default null)
returns void
language plpgsql security definer set search_path = public
as $$
declare
  v public.photo_inspections%rowtype;
  v_period date;
  -- Держит ли эта строка резерв квоты. Резервирует ТОЛЬКО
  -- request_photo_inspection, и только он создаёт revision = 1;
  -- request_photo_retake (досъёмка) и create_photo_revision (пересуд) квоту не
  -- трогают вовсе — по плану они бесплатны. Значит revision > 1 однозначно
  -- означает «резерва под этой строкой нет»: списывать с неё used, гасить
  -- reserved или жечь слот возврата нельзя.
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
      update public.photo_quota set reserved = greatest(reserved - 1, 0), used = used + 1,
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
revoke all on function public.finalize_photo_inspection(uuid, text, text, jsonb) from public;
revoke all on function public.finalize_photo_inspection(uuid, text, text, jsonb) from anon, authenticated;
grant execute on function public.finalize_photo_inspection(uuid, text, text, jsonb) to service_role;

-- ── 7. Ревизия после пересуда (правка факта; план §6 механизм 5, этап 5) ────
create or replace function public.create_photo_revision(
  p_parent_id uuid, p_payload jsonb)
returns uuid
language plpgsql security definer set search_path = public
as $$
declare
  parent public.photo_inspections%rowtype;
  v_id uuid;
begin
  select * into parent from public.photo_inspections where id = p_parent_id for update;
  if not found then raise exception 'inspection_not_found'; end if;
  if parent.revision >= 3 then raise exception 'revision_limit'; end if;

  insert into public.photo_inspections
    (user_id, product_id, product_key, packaging_level, markets, source_kind,
     idempotency_key, ruleset_sha256, ruleset_version, revision, status,
     overall, decided, checked, reader_coverage, policy_applied, degraded_mode,
     evaluated_at, checked_at, cost_usd)
  values (parent.user_id, parent.product_id, parent.product_key,
          parent.packaging_level, parent.markets, parent.source_kind,
          parent.idempotency_key || ':r' || (parent.revision + 1),
          parent.ruleset_sha256, parent.ruleset_version, parent.revision + 1, 'done',
          p_payload ->> 'overall', (p_payload ->> 'decided')::int,
          (p_payload ->> 'checked')::int, p_payload -> 'reader_coverage',
          p_payload -> 'policy_applied', parent.degraded_mode,
          parent.evaluated_at, now(), 0)
  returning id into v_id;

  insert into public.photo_assets (inspection_id, idx, kind, storage_path, sha256,
                                   width, height, mime, face_name, usable, problems)
  select v_id, idx, kind, storage_path, sha256, width, height, mime, face_name,
         usable, problems
  from public.photo_assets where inspection_id = p_parent_id;

  insert into public.photo_findings
    (inspection_id, checkpoint_id, requirement_id, rule_ref, group_key, surface,
     kind, severity, status, decided_by, confidence_class, message, basis,
     recommendation, evidence, evidence_crop_path)
  select v_id, f ->> 'checkpoint_id', nullif(f ->> 'requirement_id', '')::uuid,
         f ->> 'rule_ref', f ->> 'group_key', coalesce(f ->> 'surface', 'any_panel'),
         f ->> 'kind', f ->> 'severity', f ->> 'status',
         coalesce(f ->> 'decided_by', 'none'),
         coalesce(f ->> 'confidence_class', 'needs_human'),
         coalesce(f ->> 'message', ''), coalesce(f ->> 'basis', ''),
         f ->> 'recommendation', coalesce(f -> 'evidence', '[]'::jsonb),
         f ->> 'evidence_crop_path'
  from jsonb_array_elements(coalesce(p_payload -> 'findings', '[]'::jsonb)) f;

  insert into public.photo_not_checkable (inspection_id, checkpoint_key, rule_ref, reason, class)
  select v_id, n ->> 'checkpoint_key', coalesce(n ->> 'rule_ref', ''),
         n ->> 'reason', n ->> 'klass'
  from jsonb_array_elements(coalesce(p_payload -> 'not_checkable', '[]'::jsonb)) n;

  insert into public.photo_facts (inspection_id, revision, slot_id, payload, source,
                                  confidence, asset_idx, bbox)
  select v_id, parent.revision + 1, r ->> 'slot_id',
         coalesce(r -> 'payload', '{}'::jsonb), r ->> 'source',
         (r ->> 'confidence')::real, (r ->> 'asset_idx')::int, r -> 'bbox'
  from jsonb_array_elements(coalesce(p_payload -> 'facts', '[]'::jsonb)) r;

  update public.photo_inspections set superseded_by = v_id where id = p_parent_id;
  insert into public.photo_inspection_events (inspection_id, stage, detail)
  values (v_id, 'done', jsonb_build_object('rejudge_of', p_parent_id));
  return v_id;
end;
$$;
revoke all on function public.create_photo_revision(uuid, jsonb) from public;
revoke all on function public.create_photo_revision(uuid, jsonb) from anon, authenticated;
grant execute on function public.create_photo_revision(uuid, jsonb) to service_role;

-- ── 8. Действия по находке и подпись (план §7, §8; этап 5) ──────────────────
create or replace function public.record_finding_action(
  p_finding_id uuid, p_action text, p_reason text default null)
returns uuid
language plpgsql security definer set search_path = public
as $$
declare
  v_uid uuid := (select auth.uid());
  v_id uuid;
begin
  if v_uid is null then raise exception 'not_authenticated'; end if;
  if not exists (
      select 1 from public.photo_findings f
      join public.photo_inspections i on i.id = f.inspection_id
      where f.id = p_finding_id and i.user_id = v_uid) then
    raise exception 'finding_not_found';
  end if;
  insert into public.photo_finding_actions (finding_id, user_id, action, reason)
  values (p_finding_id, v_uid, p_action, p_reason)
  returning id into v_id;
  return v_id;
end;
$$;
revoke all on function public.record_finding_action(uuid, text, text) from public;
grant execute on function public.record_finding_action(uuid, text, text) to authenticated;

-- Подпись: вердикт с fail или критичной находкой не окончателен без неё (§8).
create or replace function public.sign_photo_inspection(p_inspection_id uuid)
returns void
language plpgsql security definer set search_path = public
as $$
declare
  v_uid uuid := (select auth.uid());
begin
  if not public.is_verified_lawyer() then raise exception 'not_a_verified_lawyer'; end if;
  update public.photo_inspections
    set signed_by = v_uid, signed_at = now()
    where id = p_inspection_id and status = 'done' and signed_by is null;
  if not found then raise exception 'nothing_to_sign'; end if;
end;
$$;
revoke all on function public.sign_photo_inspection(uuid) from public;
grant execute on function public.sign_photo_inspection(uuid) to authenticated;

-- ── 9. Реперная джоба: никто не висит в queued/running вечно (план §4, §6) ──
create or replace function public.reap_stale_inspections()
returns int
language plpgsql security definer set search_path = public
as $$
declare
  r record;
  n int := 0;
begin
  -- coalesce, а не голый heartbeat_at: воркер, взявший строку в работу и
  -- умерший ДО первого пульса, оставляет heartbeat_at = null, а `null < …`
  -- даёт null — такая строка не отбиралась бы и висела в running вечно вместе
  -- с живым резервом квоты. Порог для неё считаем от created_at.
  for r in select id from public.photo_inspections
            where status = 'running'
              and coalesce(heartbeat_at, created_at) < now() - interval '3 minutes'
  loop
    perform public.finalize_photo_inspection(r.id, 'failed', 'worker_timeout');
    n := n + 1;
  end loop;
  for r in select id from public.photo_inspections
            where status = 'queued' and created_at < now() - interval '5 minutes'
  loop
    perform public.finalize_photo_inspection(r.id, 'failed', 'dispatch_lost');
    n := n + 1;
  end loop;
  return n;
end;
$$;
revoke all on function public.reap_stale_inspections() from public;
revoke all on function public.reap_stale_inspections() from anon, authenticated;
grant execute on function public.reap_stale_inspections() to service_role;

-- ── 10. Ретеншн 30 дней — механизм, а не обещание (план §4) ─────────────────
-- Секреты (завести владельцу ПОСЛЕ наката, гейт А6 Волны 3):
--   select vault.create_secret('https://<project>.supabase.co', 'supabase_project_url', 'Storage API');
--   select vault.create_secret('<service_role key>', 'supabase_service_role_key', 'Storage delete');
-- Пока секретов нет — джоба молча пропускает удаление (как notify_admin_telegram).
-- http_delete вызывается БЕЗ схемы: pg_net на разных проектах Supabase ставится
-- то в net, то в extensions (локально — extensions), обе схемы в search_path —
-- тот же приём, что в notify_admin_telegram (20260727120000).
create or replace function public.purge_expired_photo_assets()
returns int
language plpgsql security definer set search_path = public, net, extensions
as $$
declare
  base_url text;
  srv_key  text;
  r record;
  n int := 0;
begin
  select decrypted_secret into base_url
    from vault.decrypted_secrets where name = 'supabase_project_url';
  select decrypted_secret into srv_key
    from vault.decrypted_secrets where name = 'supabase_service_role_key';
  if base_url is null or srv_key is null then
    raise warning 'purge_expired_photo_assets: секреты Vault не заведены, пропуск';
    return 0;
  end if;
  for r in
    select a.inspection_id, a.idx, a.storage_path,
           case a.kind when 'master_pdf' then 'packaging-artwork'
                       else 'packaging-photos' end as bucket
    from public.photo_assets a
    join public.photo_inspections i on i.id = a.inspection_id
    where a.purged_at is null
      and i.created_at < now() - interval '30 days'
    limit 500
  loop
    perform http_delete(
      url := base_url || '/storage/v1/object/' || r.bucket || '/' || r.storage_path,
      headers := jsonb_build_object('Authorization', 'Bearer ' || srv_key));
    update public.photo_assets set purged_at = now()
      where inspection_id = r.inspection_id and idx = r.idx;
    n := n + 1;
  end loop;
  return n;
exception when others then
  raise warning 'purge_expired_photo_assets: %', sqlerrm;
  return n;
end;
$$;
revoke all on function public.purge_expired_photo_assets() from public;
revoke all on function public.purge_expired_photo_assets() from anon, authenticated;
grant execute on function public.purge_expired_photo_assets() to service_role;

-- Расписания (идемпотентно, по образцу 20260804100000)
do $$
begin
  if not exists (select 1 from cron.job where jobname = 'photo-reap-stale') then
    perform cron.schedule('photo-reap-stale', '* * * * *',
      $cron$select public.reap_stale_inspections()$cron$);
  end if;
  if not exists (select 1 from cron.job where jobname = 'photo-purge-assets') then
    perform cron.schedule('photo-purge-assets', '30 2 * * *',
      $cron$select public.purge_expired_photo_assets()$cron$);
  end if;
end;
$$;
