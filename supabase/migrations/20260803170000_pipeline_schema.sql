-- ============================================================================
-- InspectorX v2 — схема pipeline: runs/items/maps/verdicts/llm_calls
-- Решение и обоснование: docs/adr/0003-agent-flow.md
--
-- Оркестратор Build (Задачи 13–27) отслеживает состояние картирования и
-- обработки контента по айтемам через эти таблицы. Трейсинг LLM-вызовов
-- (Задача 29, контур D) хранится вместе для единого взгляда на жизненный
-- цикл требования.
--
-- Вся схема доступна только service role (RLS deny anon/authenticated):
-- карты утверждаются Cartographer владельцем, запуски управляются бэкендом.
-- ============================================================================

create schema if not exists pipeline;

comment on schema pipeline is
  'Оркестратор Build: учёт картирования и обработки контента по айтемам, '
  'трейсинг LLM-вызовов (ADR-0003). Доступ только для service role.';

-- ============================================================================
-- pipeline.maps — карта двухуровневого картирования (мир → страна)
-- ============================================================================

create table pipeline.maps (
  id uuid primary key default gen_random_uuid(),
  group_ref text not null,                    -- HS6-префикс или UNSPSC-сегмент
  jurisdiction text not null check (jurisdiction ~ '^[A-Z]{2}$'),
  status text not null default 'draft' check (status in ('draft','approved','rejected')),
  payload jsonb not null,                     -- [{expected_item, category_slug, rationale, benchmark_countries}]
  approved_at timestamptz,
  approved_by text,
  created_at timestamptz not null default now(),
  unique (group_ref, jurisdiction)
);

comment on table pipeline.maps is
  'Карта картирования (двухуровневая: мир → страна). Строка утверждается '
  'Cartographer владельцем (approved_at + approved_by); объекты группы по этой карте ждут в draft.';
comment on column pipeline.maps.group_ref is 'HS6-префикс (товары) или UNSPSC-сегмент (услуги)';
comment on column pipeline.maps.jurisdiction is 'ISO 3166-1 alpha-2, напр. UZ, KZ, AE';
comment on column pipeline.maps.payload is 'Массив объектов картирования: expected_item, category_slug, rationale, benchmark_countries';

-- ============================================================================
-- pipeline.runs — запуск конвейера для карты и юрисдикции
-- ============================================================================

create table pipeline.runs (
  id uuid primary key default gen_random_uuid(),
  map_id uuid not null references pipeline.maps(id),
  status text not null default 'running' check (status in ('running','done','failed')),
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

comment on table pipeline.runs is
  'Запуск конвейера обработки для карты (map_id). Жизненный цикл: '
  'running → done | failed; finished_at заполняется при завершении.';
comment on column pipeline.runs.map_id is 'Ссылка на утвёрженную карту (или draft, если перезапуск)';

-- ============================================================================
-- pipeline.items — гранулярность учёта: один айтем = одно требование
-- ============================================================================

create table pipeline.items (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references pipeline.runs(id),
  expected_item text not null,                 -- из карты (payload)
  category_slug text references public.requirement_categories(slug),
  requirement_id uuid references public.requirements(id),
  status text not null default 'pending' check (status in
    ('pending','in_progress','draft_loaded','published','needs_attention','no_norm')),
  retry_count int not null default 0,
  last_error text,
  updated_at timestamptz not null default now()
);

comment on table pipeline.items is
  'Гранулярность учёта конвейера: один айтем = одно требование. Жизненный '
  'цикл: pending → in_progress → draft_loaded → published | needs_attention | no_norm.';
comment on column pipeline.items.expected_item is 'Текст ожидаемого требования из карты';
comment on column pipeline.items.category_slug is 'Категория требования (может быть NULL в draft)';
comment on column pipeline.items.requirement_id is 'Ссылка на опубликованное требование (может быть NULL)';
comment on column pipeline.items.status is 'pending | in_progress | draft_loaded | published | needs_attention | no_norm';
comment on column pipeline.items.retry_count is 'Количество попыток переобработки';
comment on column pipeline.items.last_error is 'Текст ошибки последней попытки';

-- ============================================================================
-- pipeline.verdicts — вердикты Verifier по шагам контроля качества
-- ============================================================================

create table pipeline.verdicts (
  id uuid primary key default gen_random_uuid(),
  item_id uuid not null references pipeline.items(id),
  step text not null,                          -- 'norm' | 'summary' | 'category' | 'rule' | 'sanction' | 'cases' | 'samples' | 'translation'
  verdict text not null check (verdict in ('pass','fail')),
  reason text,
  model text,
  created_at timestamptz not null default now()
);

comment on table pipeline.verdicts is
  'Вердикты Verifier по шагам проверки качества. Один айтем может иметь '
  'несколько вердиктов (по разным шагам).';
comment on column pipeline.verdicts.step is 'Шаг проверки: norm | summary | category | rule | sanction | cases | samples | translation';
comment on column pipeline.verdicts.verdict is 'pass | fail';
comment on column pipeline.verdicts.reason is 'Текст обоснования вердикта';

-- ============================================================================
-- pipeline.llm_calls — трейсинг LLM-вызовов и стоимость (контур D)
-- ============================================================================

create table pipeline.llm_calls (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references pipeline.runs(id),
  item_id uuid references pipeline.items(id),
  role text not null,                          -- 'retriever' | 'verifier' | 'classifier' | …
  model text not null,
  input_tokens int,
  output_tokens int,
  cost_usd numeric(10,5),
  created_at timestamptz not null default now()
);

comment on table pipeline.llm_calls is
  'Трейсинг LLM-вызовов: модель, используемые токены, стоимость. Контур D '
  'оркестратора (Задача 29). Один запрос может иметь вызовы по разным ролям.';
comment on column pipeline.llm_calls.run_id is 'Ссылка на запуск (если запрос на уровне run)';
comment on column pipeline.llm_calls.item_id is 'Ссылка на айтем (если запрос на уровне item)';
comment on column pipeline.llm_calls.role is 'Роль агента: retriever | verifier | classifier | …';
comment on column pipeline.llm_calls.model is 'Идентификатор модели (напр. claude-opus-4-1)';

-- ============================================================================
-- RLS: вся схема доступна только service role
-- ============================================================================

alter table pipeline.maps enable row level security;
alter table pipeline.runs enable row level security;
alter table pipeline.items enable row level security;
alter table pipeline.verdicts enable row level security;
alter table pipeline.llm_calls enable row level security;

-- Явные grants: schema usage для всех, таблицы — только service_role.
-- Анон/authenticated не получают даже usage на схему.
grant usage on schema pipeline to service_role;
grant select, insert, update, delete
  on pipeline.maps, pipeline.runs, pipeline.items, pipeline.verdicts, pipeline.llm_calls
  to service_role;
