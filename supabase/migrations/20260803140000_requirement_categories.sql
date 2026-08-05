-- ============================================================================
-- InspectorX v2 — справочник requirement_categories (NTM-базис)
-- Замена enum на таблицу, ось сравнения для Cartographer (Задача 15)
-- ============================================================================

create table public.requirement_categories (
  slug text primary key,
  name_ru text not null,
  name_uz text,
  name_en text,
  definition_ru text,            -- «что сюда входит» — инструкция для Classifier и Cartographer
  sort_order int not null default 0,
  is_active boolean not null default true
);

comment on table public.requirement_categories is
  'UNCTAD NTM (технические барьеры) — 8 категорий: SPS, TBT, маркировка, лицензии, налоги, валюта, таможня, происхождение. '
  'Ось сравнения для Cartographer (задача 15). Требования привязываются через category_slug.';
comment on column public.requirement_categories.slug is 'код категории (sps, tbt, marking, licensing, fiscal, currency, customs, origin)';
comment on column public.requirement_categories.name_ru is 'русское название';
comment on column public.requirement_categories.definition_ru is 'что входит в категорию — инструкция для Classifier и Cartographer';

insert into public.requirement_categories (slug, name_ru, name_en, sort_order) values
  ('sps',      'Санитарные и фитосанитарные', 'Sanitary & phytosanitary', 10),
  ('tbt',      'Техрегламенты и сертификация','Technical regulations & certification', 20),
  ('marking',  'Маркировка и упаковка',       'Marking & packaging', 30),
  ('licensing','Лицензии и разрешения',       'Licensing & permits', 40),
  ('fiscal',   'Налоги и фискальные',         'Fiscal & tax', 50),
  ('currency', 'Валютный контроль',           'Currency control', 60),
  ('customs',  'Таможенные процедуры',        'Customs procedures', 70),
  ('origin',   'Правила происхождения',       'Rules of origin', 80);

-- Добавляем колонку в requirements с FK на requirement_categories
alter table public.requirements
  add column category_slug text references public.requirement_categories(slug);

-- Бэкофилл: переносим значения из enum requirement_category в новую колонку
update public.requirements
  set category_slug = requirement_category::text
  where requirement_category is not null;

-- Включаем RLS: справочник публичен на чтение
alter table public.requirement_categories enable row level security;

create policy "public read" on public.requirement_categories
  for select to anon, authenticated using (true);
