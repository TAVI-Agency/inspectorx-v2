-- ============================================================================
-- InspectorX v2 — модуль услуг: схема (строго аддитивно)
-- Основа: docs/SERVICES_PASSPORT_PROPOSAL.md (утверждено фаундером 12.07.2026)
-- Формула паспорта услуги: режим допуска × 6 этапов жизни бизнеса.
-- Товары и RLS не трогаем: новые колонки nullable, enum'ы расширяются,
-- политики services/lifecycle_stages/authorities уже дают public read.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Режим допуска (ЗРУ-701): лицензия / разрешение / уведомление / свободно
-- ----------------------------------------------------------------------------

create type public.admission_mode as enum ('license', 'permit', 'notification', 'free');

-- Пометка «разовое действие / постоянная обязанность» на карточке (§4 предложения)
create type public.requirement_nature as enum ('one_time', 'recurring');

-- ----------------------------------------------------------------------------
-- services: паспортные поля (зеркало products: код оси поиска + сложность)
-- ОКЭД — главный код услуги (вид деятельности), ИКПУ остаётся вторым в шапке.
-- ----------------------------------------------------------------------------

-- ИКПУ перестаёт быть обязательным: главная ось поиска услуг — ОКЭД,
-- фискальный код показываем в шапке, когда он известен (не досочиняем).
alter table public.services alter column ikpu_code drop not null;

alter table public.services
  add column oked_code text check (oked_code ~ '^[0-9]{2}(\.[0-9]{1,2})?$'),
  add column admission_mode public.admission_mode,
  add column authority_id uuid references public.authorities(id) on delete set null,
  add column complexity_index int check (complexity_index between 1 and 10);

comment on column public.services.oked_code is
  'Код вида деятельности ОКЭД (главная ось поиска услуг, аналог ТН ВЭД). Формат NN или NN.NN.';
comment on column public.services.admission_mode is
  'Режим допуска по ЗРУ-701: license/permit/notification/free. Главный бейдж паспорта услуги.';
comment on column public.services.authority_id is
  'Лицензиар / разрешительный орган услуги.';

create index services_oked_code_idx on public.services (oked_code);

-- ----------------------------------------------------------------------------
-- Расширение существующих enum'ов (значения используются со следующей миграции)
-- ----------------------------------------------------------------------------

alter type public.operation_domain add value if not exists 'service';
alter type public.party_role add value if not exists 'service_provider';
alter type public.applicability_scope add value if not exists 'oked_code';
alter type public.applicability_scope add value if not exists 'oked_prefix';

-- ----------------------------------------------------------------------------
-- requirement_applicability: код ОКЭД содержит точку (47.73) — расширяем
-- формат кода; правило наличия кода для новых scope то же (код обязателен).
-- ----------------------------------------------------------------------------

alter table public.requirement_applicability
  drop constraint requirement_applicability_code_check;
alter table public.requirement_applicability
  add constraint requirement_applicability_code_check
  check (code ~ '^[0-9]+(\.[0-9]+)?$');

-- ----------------------------------------------------------------------------
-- requirements: пометка «разовое / постоянное» (nullable — старые карточки без неё)
-- ----------------------------------------------------------------------------

alter table public.requirements
  add column nature public.requirement_nature;

comment on column public.requirements.nature is
  'one_time — разовое действие (получить лицензию), recurring — постоянная обязанность (вести журнал).';

-- ----------------------------------------------------------------------------
-- lifecycle_stages: 6 этапов жизни бизнеса (маршрут услуги, дизайн C).
-- Товарные этапы (sort 1–36) не трогаем; сервисные — блок 101–106.
-- ----------------------------------------------------------------------------

insert into public.lifecycle_stages (id, code, name_ru, name_uz, name_en, sort_order) values
  ('a1b90d21-5c01-4d10-9a01-000000000001', 'svc-01-start',     'Старт и допуск',         'Boshlash va ruxsat',        'Start & admission',      101),
  ('a1b90d21-5c01-4d10-9a01-000000000002', 'svc-02-premises',  'Помещение и запуск',     'Bino va ishga tushirish',   'Premises & launch',      102),
  ('a1b90d21-5c01-4d10-9a01-000000000003', 'svc-03-operations','Текущая работа',         'Kundalik faoliyat',         'Day-to-day operations',  103),
  ('a1b90d21-5c01-4d10-9a01-000000000004', 'svc-04-inspections','Проверки',              'Tekshiruvlar',              'Inspections',            104),
  ('a1b90d21-5c01-4d10-9a01-000000000005', 'svc-05-changes',   'Изменения и продление',  'O''zgarishlar va uzaytirish','Changes & renewal',      105),
  ('a1b90d21-5c01-4d10-9a01-000000000006', 'svc-06-closure',   'Прекращение',            'Faoliyatni tugatish',       'Closure',                106)
on conflict (code) do nothing;
