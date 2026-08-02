-- ============================================================================
-- InspectorX v2 — схема catalog: product_types, country_codes, skus
-- Решение и обоснование: docs/adr/0004-product-catalog.md
--
-- Каталог хранится отдельно от public.products/public.services (v1-модель,
-- строковые коды) и спроектирован отделяемым в отдельный сервис при выходе
-- во вторую страну. Требования продолжают ссылаться на public.products /
-- public.services — миграция scope на product_type_id вынесена в отдельную
-- задачу (см. ADR-0004, «Последствия»).
--
-- Схема не экспоузится через PostgREST (supabase/config.toml: api.schemas =
-- ["public", "graphql_public"]) — витрина будет ходить через представления/
-- джойны в public. Grants здесь нужны на будущее и для прямого psql/service
-- role доступа: RLS-политика сама по себе не даёт select-привилегию.
-- ============================================================================

create schema if not exists catalog;

comment on schema catalog is
  'Товарный каталог (ADR-0004): канонические типы товаров/услуг, национальные '
  'кодировки, SKU. Не экспоузится через PostgREST — доступ через public.';

-- ----------------------------------------------------------------------------
-- product_types — канонические типы товаров и услуг
-- ----------------------------------------------------------------------------

-- Дерево не выдумываем: товары наследуют иерархию HS (WCO, уровень HS6),
-- услуги — сервисные сегменты UNSPSC. Критерий деления узла тоньше HS —
-- только граница, которую провёл закон (см. ADR-0004).
create table catalog.product_types (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('good','service')),
  hs_code text unique check (hs_code ~ '^\d{6}$'),        -- товары: HS6 (WCO)
  unspsc_code text unique check (unspsc_code ~ '^\d{8}$'),-- услуги: UNSPSC
  parent_id uuid references catalog.product_types(id),
  name_ru text not null, name_uz text, name_en text,
  created_at timestamptz not null default now(),
  check ((kind = 'good' and hs_code is not null and unspsc_code is null)
      or (kind = 'service' and unspsc_code is not null and hs_code is null))
);

comment on table catalog.product_types is
  'Канонические типы товаров (HS6) и услуг (UNSPSC). Единственная точка '
  'привязки требований (ADR-0004, «Ключевое правило») — гос-коды и SKU на неё '
  'только указывают.';
comment on column catalog.product_types.kind is 'good | service';
comment on column catalog.product_types.hs_code is 'HS6 (WCO), заполнен только у товаров';
comment on column catalog.product_types.unspsc_code is 'UNSPSC, заполнен только у услуг';
comment on column catalog.product_types.parent_id is 'Родительский узел дерева HS/UNSPSC';

-- ----------------------------------------------------------------------------
-- country_codes — национальные слои кодов (ИКПУ / ТН ВЭД / ОКЭД / HTS / …)
-- ----------------------------------------------------------------------------

-- Ни один национальный классификатор не становится осью каталога —
-- это просто строки-указатели на product_type (ADR-0004, раздел 2).
create table catalog.country_codes (        -- национальные слои кодов
  id uuid primary key default gen_random_uuid(),
  country text not null check (country ~ '^[A-Z]{2}$'),
  system text not null,                     -- 'ikpu' | 'tnved' | 'oked' | 'hts' | …
  code text not null,
  name text,
  product_type_id uuid references catalog.product_types(id),
  unique (country, system, code)
);
create index on catalog.country_codes (product_type_id);

comment on table catalog.country_codes is
  'Национальные кодировки (ИКПУ/ТН ВЭД/ОКЭД/HTS/NAICS/…), привязанные к '
  'catalog.product_types. Отсутствие строк для страны/системы — норма, а не дефект.';
comment on column catalog.country_codes.country is 'ISO 3166-1 alpha-2, напр. UZ, KZ, AE';
comment on column catalog.country_codes.system is 'ikpu | tnved | oked | hts | naics | …';

-- ----------------------------------------------------------------------------
-- skus — конкретные товары (только страны с фискальным каталогом)
-- ----------------------------------------------------------------------------

-- Привязка к типу — по префиксу кода (первые 11 цифр ИКПУ = субпозиция).
-- Требования к SKU не привязываются никогда (ADR-0004, раздел 3).
create table catalog.skus (                 -- только товары, только страны с фискальным каталогом
  id uuid primary key default gen_random_uuid(),
  country text not null default 'UZ' check (country ~ '^[A-Z]{2}$'),
  ikpu_code text not null check (ikpu_code ~ '^\d{17}$'),
  brand text, attribute text, barcode text,
  product_type_id uuid not null references catalog.product_types(id),
  unique (country, ikpu_code)
);

comment on table catalog.skus is
  'Конкретные товары (17-значный ИКПУ), только страны с фискальным каталогом. '
  'Назначение: резолв штрихкода в фото-чеке, вход по коду ИКПУ, фискальные фичи. '
  'Требования к SKU не привязываются никогда — только к product_type_id.';
comment on column catalog.skus.attribute is 'Фасовка/атрибут SKU';

-- ----------------------------------------------------------------------------
-- RLS: справочники публичны на чтение, запись — только service role
-- ----------------------------------------------------------------------------

alter table catalog.product_types enable row level security;
alter table catalog.country_codes enable row level security;
alter table catalog.skus          enable row level security;

create policy "public read" on catalog.product_types
  for select to anon, authenticated using (true);

create policy "public read" on catalog.country_codes
  for select to anon, authenticated using (true);

create policy "public read" on catalog.skus
  for select to anon, authenticated using (true);

-- RLS-политика не даёт привилегию сама по себе — нужны явные grants.
-- Схема catalog создана этой миграцией, а не входит в дефолтные привилегии
-- public/extensions/…, поэтому даже service_role (bypass RLS, но не bypass
-- GRANT) без явного usage не видит объекты схемы — grant нужен и ему.
grant usage on schema catalog to anon, authenticated, service_role;
grant select on catalog.product_types, catalog.country_codes, catalog.skus
  to anon, authenticated;
grant select, insert, update, delete
  on catalog.product_types, catalog.country_codes, catalog.skus
  to service_role;
