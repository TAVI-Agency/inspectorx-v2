-- ============================================================================
-- InspectorX v2 — Задача 15 (этап 6 плана фотоконтроля, «правила как данные»):
-- requirement_photo / requirement_photo_checks / photo_checklist().
--
-- Адаптация черновика inspectorx-vision/docs/DB_EXTENSION.sql. Отличия от
-- черновика — названы, а не молчат:
--  1) requirement_id СТАЛ nullable: канонический ключ — rule_ref (пакет.
--     требование), uuid приезжает мостом config/bridge/requirement_ids.csv
--     (заполняет юрист, Волна 3) и честно отсутствует, пока моста нет;
--  2) тавтологичный CHECK (checkability <> 'checkable' or true) заменён
--     constraint-триггером requirement_photo_checkable_needs_checks (deferrable);
--  3) unique(requirement_id, kind, subject, measure) с NULL-ловушкой заменён на
--     unique (rule_ref, check_id) — предмет-дедуп остаётся задачей компилятора
--     чек-листа (compile_checklist._dedup_key на стороне vision), эта таблица —
--     сырой каталог правил, не готовый к показу чек-лист;
--  4) params проверяется pg_jsonschema-схемой, сгенерированной из полей
--     PhotoCheckSpec.params (surface/language/min_mm) — теперь констрейнт,
--     а не соглашение линтера.
--
-- ПРОД: pg_jsonschema включается в Dashboard → Database → Extensions до
-- мёржа (гейт А6 Волны 3) — паттерн как у pg_cron (20260804100000). Схема
-- extensions — явно: это конвенция Supabase (config.toml extra_search_path)
-- и то, как мы дальше вызываем extensions.jsonb_matches_schema() ниже.
-- ============================================================================
create extension if not exists pg_jsonschema with schema extensions;

create type public.photo_check_kind as enum ('presence', 'text_semantic', 'absence', 'geometry');
create type public.photo_checkability as enum ('checkable', 'partial', 'not_checkable');
create type public.photo_severity as enum ('critical', 'major', 'minor', 'info');
create type public.photo_packaging_level as enum ('consumer', 'transport', 'both');

-- ----------------------------------------------------------------------------
-- 1. Проверяемость требования по фото. Строка со статусом not_checkable —
--    это ОТВЕТ («нужен лабораторный анализ»), а не пробел: она попадает в
--    раздел вердикта «не проверяется по фото» (см. `photo_not_checkable` в
--    рантайме, 20260810100000_photo_runtime.sql — разные таблицы, не путать).
-- ----------------------------------------------------------------------------
create table public.requirement_photo (
  rule_ref        text primary key,       -- "<пакет>.<requirement.id>" из выгрузки vision
  requirement_id  uuid references public.requirements(id) on delete set null,
  pack            text not null default '',
  title_ru        text not null default '',
  checkability    public.photo_checkability not null,
  packaging_level public.photo_packaging_level not null default 'consumer',
  why             text not null,          -- почему именно так; показывается человеку
  markets         text[] not null default '{UZ}',
  -- Легаси-scope выгрузки: 'all_products' — горизонтальная норма без применимости,
  -- 'hs_prefix' — применяется к товарам, чей hs_code начинается с одного из
  -- hs_prefixes. Третьего значения выгрузка vision (scripts/export_checks.py,
  -- _applicability_summary) сегодня не порождает — появится, расширить вместе
  -- с public.photo_checklist().
  scope           text not null default 'hs_prefix' check (scope in ('hs_prefix', 'all_products')),
  hs_prefixes     text[] not null default '{}',
  source          jsonb not null default '{}'::jsonb,
  ruleset_sha256  text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

comment on column public.requirement_photo.rule_ref is
  'Канонический ключ выгрузки "<пакет>.<requirement.id>" — не совпадает с '
  'человекочитаемым "акт + пункт" (тот меняется при слиянии дублей компилятором '
  'vision). Стабилен между прогонами export_checks.py; выгрузка — источник '
  'истины, правки в базе руками перетираются следующим прогоном.';
comment on column public.requirement_photo.why is
  'Причина статуса checkability. Для not_checkable/partial — текст, который '
  'увидит инспектор: «фактическая жирность подтверждается лабораторным '
  'протоколом, не фотографией».';

create trigger set_updated_at before update on public.requirement_photo
  for each row execute function public.set_updated_at();

-- ----------------------------------------------------------------------------
-- 2. Атомарные проверки. Одно требование → 0..N проверок; N = 0 законно
--    (partial/not_checkable). params — намеренно jsonb: у четырёх kind разные
--    наборы параметров, добавление параметра — не миграция, а данные.
-- ----------------------------------------------------------------------------
create table public.requirement_photo_checks (
  id              uuid primary key default gen_random_uuid(),
  rule_ref        text not null references public.requirement_photo(rule_ref) on delete cascade,
  check_id        text not null,          -- id проверки внутри требования (PhotoCheckSpec.id)
  ord             int not null default 0,
  kind            public.photo_check_kind not null,
  severity        public.photo_severity not null default 'major',
  group_key       text not null,
  subject         text not null default '',
  packaging_level public.photo_packaging_level not null default 'both',
  target          text,                  -- для presence: что искать
  question_ru     text,                  -- для text_semantic / absence — он же уходит в VLM
  measure         text,                  -- для geometry: min_size_mm | area_fraction | ...
  params          jsonb not null default '{}'::jsonb,
  hint_ru         text,                  -- что доснять, если пункт не прошёл
  title_ru        text,                  -- если пусто — берётся заголовок требования
  created_at      timestamptz not null default now(),
  unique (rule_ref, check_id),
  constraint photo_check_target_for_presence
    check (kind <> 'presence' or target is not null),
  constraint photo_check_question_for_text
    check (kind not in ('text_semantic', 'absence') or question_ru is not null),
  constraint photo_check_measure_for_geometry
    check (kind <> 'geometry' or measure is not null),
  -- min_mm приезжает из YAML как явный null (метод измерения ещё не выбран
  -- между абсолютным и относительным — см. reference_scale в соседних
  -- params); схема обязана принимать null ровно у тех ключей, что реально
  -- приезжают с null (проверено на выгрузке 07.08.2026: min_mm — 33 раза).
  -- minimum (не exclusiveMinimum): один пункт несёт min_mm=0 намеренно —
  -- «стандарт не задаёт обязательного порога, движок обязан ЗАФИКСИРОВАТЬ
  -- измеренное значение, а не сравнить его с нормой» (horizontal.yaml,
  -- transport.mark_size_series, min_mm_semantics).
  --
  -- surface НЕ заужен до словаря линтера (SURFACE_VOCABULARY в
  -- scripts/lint_params.py vision, те же 10 значений, что в черновике
  -- DB_EXTENSION.sql): это ЦЕЛЕВОЙ словарь ratchet-линтера, а не форма
  -- текущих данных — у выгрузки 07.08.2026 28 РАЗНЫХ значений surface (39
  -- из них уже баселайнены в scripts/lint_params_baseline.json как известный,
  -- принятый долг vision). Constraint строже собственного линтера vision
  -- отклонил бы легитимные 364/364 проверки при накате этой самой миграции —
  -- нормализация словаря осталась вне периметра Задачи 15.
  constraint photo_check_params_valid check (extensions.jsonb_matches_schema(
    '{"type":"object","properties":{
       "surface":{"type":["string","null"]},
       "language":{"type":["array","null"],"items":{"enum":["ru","uz","uz-cyrl","uz-latn","en","kk","hy","ky"]}},
       "min_mm":{"type":["number","null"],"minimum":0}
     }}'::json, params))
);

create index requirement_photo_checks_rule_ref_idx on public.requirement_photo_checks (rule_ref);
create index requirement_photo_checks_subject_idx on public.requirement_photo_checks (subject);
create index requirement_photo_checks_level_idx on public.requirement_photo_checks (packaging_level);

-- contents: язык-строки (ru сейчас, uz/en позже) — по образцу requirement_contents.
-- Пусто сегодня (выгрузка несёт только ru): наполнится вместе с переводом чек-листа.
create table public.requirement_photo_check_contents (
  check_id uuid not null references public.requirement_photo_checks(id) on delete cascade,
  lang     text not null check (lang in ('ru', 'uz', 'en')),
  question text,
  hint     text,
  title    text,
  primary key (check_id, lang)
);

-- ----------------------------------------------------------------------------
-- 3. «checkable ⇒ есть хотя бы одна проверка» — то, что CHECK одной таблицы
--    не выразит (нужна видимость дочерней requirement_photo_checks).
--    Deferrable: генератор миграции контента вставляет requirement_photo и
--    requirement_photo_checks в одной транзакции, checkable-требование обязано
--    обзавестись проверкой ДО конца транзакции, а не до конца своего insert.
-- ----------------------------------------------------------------------------
create or replace function public.requirement_photo_checkable_guard()
returns trigger language plpgsql as $$
begin
  if new.checkability = 'checkable' and not exists (
      select 1 from public.requirement_photo_checks c where c.rule_ref = new.rule_ref) then
    raise exception 'checkable_needs_checks: % объявлен checkable без единой проверки', new.rule_ref;
  end if;
  return new;
end;
$$;
create constraint trigger requirement_photo_checkable_needs_checks
  after insert or update on public.requirement_photo
  deferrable initially deferred
  for each row execute function public.requirement_photo_checkable_guard();

-- ----------------------------------------------------------------------------
-- 4. RLS: чтение всем (это каталог правил, не пользовательские данные),
--    запись — только service_role (генератор миграции контента).
-- ----------------------------------------------------------------------------
alter table public.requirement_photo enable row level security;
alter table public.requirement_photo_checks enable row level security;
alter table public.requirement_photo_check_contents enable row level security;
create policy "public read" on public.requirement_photo for select to anon, authenticated using (true);
create policy "public read" on public.requirement_photo_checks for select to anon, authenticated using (true);
create policy "public read" on public.requirement_photo_check_contents for select to anon, authenticated using (true);
revoke insert, update, delete on public.requirement_photo,
  public.requirement_photo_checks, public.requirement_photo_check_contents
  from anon, authenticated;

-- ----------------------------------------------------------------------------
-- 5. Чек-лист из SQL: объединение легаси-scope выгрузки (hs_prefix/
--    all_products) и каталога catalog.product_types через products.product_type_id
--    (ADR-0004). Ровно то, что делает compile_checklist() в vision: отбор по
--    применимости, уровню упаковки и рынку — ни одного упоминания табака,
--    молока и электроники в теле функции.
--
--    Рынок: rp.markets && p_markets ИЛИ rp.markets = {'ANY'} — 'ANY' в
--    выгрузке (Requirement.markets по умолчанию, models.py) означает
--    «горизонтальная норма, рынок не сужает» и НЕ является реальным кодом
--    рынка, с которым массив можно пересечь оператором && (см.
--    _applies_to_requirement_market в vision/src/ixvision/compiler/checklist.py —
--    тот же особый случай там читается явно, не через &&).
--
--    Уровень упаковки: два НЕЗАВИСИМЫХ фильтра — у требования (rp) и у
--    отдельной проверки (c), как в compile_checklist (там же две проверки:
--    _applies_to_level(req, level) и spec.level not in (level, BOTH)). Без
--    этого разделения SQL завысил бы число пунктов транспортного уровня
--    строками потребительских требований и наоборот.
-- ----------------------------------------------------------------------------
create or replace function public.photo_checklist(
  p_product_id uuid, p_level text, p_markets text[] default '{UZ}')
returns table (rule_ref text, check_id text, kind public.photo_check_kind,
               severity public.photo_severity, group_key text, subject text,
               target text, question_ru text, measure text, params jsonb,
               hint_ru text, title_ru text, requirement_id uuid)
language sql stable
as $$
  select c.rule_ref, c.check_id, c.kind, c.severity, c.group_key, c.subject,
         c.target, c.question_ru, c.measure, c.params, c.hint_ru,
         coalesce(c.title_ru, rp.title_ru), rp.requirement_id
  from public.requirement_photo_checks c
  join public.requirement_photo rp on rp.rule_ref = c.rule_ref
  join public.products p on p.id = p_product_id
  where (rp.markets && p_markets or rp.markets = array['ANY'])
    and (c.packaging_level = 'both' or c.packaging_level::text = p_level)
    and (rp.packaging_level = 'both' or rp.packaging_level::text = p_level)
    and (rp.scope = 'all_products'
         or exists (select 1 from unnest(rp.hs_prefixes) pref
                    where p.hs_code like pref || '%')
         or exists (select 1 from catalog.product_types pt
                    where pt.id = p.product_type_id
                      and exists (select 1 from unnest(rp.hs_prefixes) pref
                                  where pt.hs_code like pref || '%')))
  order by c.group_key, c.severity, c.ord;
$$;
grant execute on function public.photo_checklist(uuid, text, text[]) to anon, authenticated;

comment on function public.photo_checklist is
  'Порождает чек-лист фотоконтроля по товару, уровню упаковки и рынкам — '
  'слепок того же отбора, что compile_checklist() в inspectorx-vision. '
  'Паритет цифра в цифру проверяет scripts/bench_sql_parity.py (vision).';

-- ----------------------------------------------------------------------------
-- 6. Габариты упаковки: вводит пользователь один раз на свой SKU (развилка 4
--    плана фотоконтроля, этап 6). Без них min_size_mm не проверяется —
--    движку не от чего считать миллиметры (см. Задачу 15, шаг 6).
-- ----------------------------------------------------------------------------
create table public.photo_product_dimensions (
  user_id         uuid not null references auth.users(id) on delete cascade,
  product_id      uuid not null references public.products(id) on delete cascade,
  packaging_level text not null check (packaging_level in ('consumer', 'transport')),
  width_mm        numeric(7,1) not null check (width_mm > 0),
  height_mm       numeric(7,1) not null check (height_mm > 0),
  depth_mm        numeric(7,1) check (depth_mm > 0),
  updated_at      timestamptz not null default now(),
  primary key (user_id, product_id, packaging_level)
);
alter table public.photo_product_dimensions enable row level security;
create policy "own all" on public.photo_product_dimensions
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

create trigger set_updated_at before update on public.photo_product_dimensions
  for each row execute function public.set_updated_at();
