-- ============================================================================
-- InspectorX v2 — начальная схема
-- Контракт данных: docs/TARGET_FORMAT.md §4 (три уровня раскрытия требования)
-- Дизайн-решения: см. docs/SESSION_SUMMARY_2026-07-11.md и ревью схемы 11.07.2026
-- ============================================================================

create extension if not exists pg_trgm with schema extensions;

-- ----------------------------------------------------------------------------
-- ENUMS
-- ----------------------------------------------------------------------------

create type public.lang_code as enum ('ru', 'uz', 'en');

-- Жизненный цикл карточки (§5b): draft -> in_review -> published.
-- flagged_by_change — НЕ статус, а флаг поверх published (карточка остаётся
-- на витрине со значком «проверяется обновление»), см. review_flag.
create type public.requirement_status as enum ('draft', 'in_review', 'published', 'archived');
create type public.review_flag as enum ('none', 'flagged_by_change');

-- Деонтика (§4, уровень 0): обязанность / запрет / разрешение-льгота
create type public.deontic_type as enum ('obligation', 'prohibition', 'permission');

-- Адресат требования (§2 П6): «это про меня?»
create type public.party_role as enum ('producer', 'importer', 'exporter', 'seller', 'carrier', 'all');

-- Домен операции (бывшие таблицы *_all старой базы)
create type public.operation_domain as enum
  ('product', 'realization', 'import', 'export', 'transit', 're_export', 're_import');
create type public.transport_type as enum ('avto', 'avia', 'train');

-- Слой доверия (§5a): каждый контентный блок несёт метку
create type public.trust_label as enum ('ai_draft', 'lawyer_verified', 'official_answer');

-- Происхождение карточки: перенос из v1 / конвейер Bridge / ручной ввод
create type public.requirement_origin as enum ('migration_v1', 'ai_pipeline', 'manual');

-- Применимость: точный код / класс-префикс / все товары / все услуги
create type public.applicability_scope as enum
  ('hs_code', 'hs_prefix', 'ikpu_code', 'ikpu_prefix', 'all_products', 'all_services');

create type public.act_status as enum ('active', 'repealed', 'pending');

-- Конвейер изменений (§5): источник -> событие -> затронутые требования -> уведомления
create type public.change_source as enum ('jurisbase', 'manual');
create type public.change_event_type as enum ('new', 'amended', 'repealed', 'effective_soon');
create type public.importance_level as enum ('high', 'medium', 'low');
create type public.impact_status as enum ('pending_review', 'confirmed', 'dismissed');

create type public.subscription_request_status as enum ('new', 'contacted', 'activated', 'rejected');
create type public.content_request_kind as enum ('fill_product', 'missing_product', 'missing_section');
create type public.content_request_status as enum ('new', 'planned', 'done');

-- Воронка вопросов (§5a): AI -> эксперт -> GR-запрос госоргану
create type public.question_status as enum
  ('new', 'ai_answered', 'expert_answered', 'gr_sent', 'gr_answered', 'closed');

-- ----------------------------------------------------------------------------
-- Служебные функции
-- ----------------------------------------------------------------------------

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ----------------------------------------------------------------------------
-- КАТАЛОГ
-- ----------------------------------------------------------------------------

-- Этапы жизненного цикла товара (сертификация, маркировка, реализация, ...).
-- Справочник; сеется при переносе из старых *_procedure_categories.
create table public.lifecycle_stages (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name_ru text not null,
  name_uz text,
  name_en text,
  sort_order int not null default 0,
  created_at timestamptz not null default now()
);

-- Ведомства («к кому идти», §4 уровень 1)
create table public.authorities (
  id uuid primary key default gen_random_uuid(),
  code text unique,
  name_ru text not null,
  name_uz text,
  name_en text,
  contacts jsonb not null default '{}'::jsonb,
  website text,
  created_at timestamptz not null default now()
);

-- Товары (ТН ВЭД). Код — text: старый int терял ведущие нули.
-- parent_id — задел под дерево каталога (браузинг, §3b п.2в);
-- hierarchy_path — мигрированный breadcrumb level_1..10 из старой базы.
create table public.products (
  id uuid primary key default gen_random_uuid(),
  hs_code text not null unique check (hs_code ~ '^[0-9]{2,10}$'),
  parent_id uuid references public.products(id) on delete set null,
  name_ru text not null,
  name_uz text,
  name_en text,
  hierarchy_path jsonb not null default '[]'::jsonb,
  complexity_index int check (complexity_index between 1 and 10),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index products_parent_id_idx on public.products (parent_id);
create index products_name_ru_trgm_idx on public.products using gin (name_ru extensions.gin_trgm_ops);

-- Услуги (ИКПУ). Каталог и поиск — с первого дня; паспорт услуги — отдельная задача (§3b п.1).
create table public.services (
  id uuid primary key default gen_random_uuid(),
  ikpu_code text not null unique check (ikpu_code ~ '^[0-9]{3,17}$'),
  name_ru text not null,
  name_uz text,
  name_en text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Алиасы поиска на 3 языках (§3b п.4), включая «возможно, вы имели в виду»
create table public.search_aliases (
  id uuid primary key default gen_random_uuid(),
  product_id uuid references public.products(id) on delete cascade,
  service_id uuid references public.services(id) on delete cascade,
  alias text not null,
  lang public.lang_code not null default 'ru',
  is_default boolean not null default false,
  created_at timestamptz not null default now(),
  constraint search_aliases_one_target check (num_nonnulls(product_id, service_id) = 1)
);

create index search_aliases_product_id_idx on public.search_aliases (product_id);
create index search_aliases_service_id_idx on public.search_aliases (service_id);
create index search_aliases_alias_trgm_idx on public.search_aliases using gin (alias extensions.gin_trgm_ops);

-- ----------------------------------------------------------------------------
-- ИСТОЧНИКИ (фундамент уведомлений «изменилось ваше требование»)
-- ----------------------------------------------------------------------------

create table public.acts (
  id uuid primary key default gen_random_uuid(),
  jurisbase_act_id text unique,
  title text not null,
  act_type text,
  number text,
  adopted_date date,
  status public.act_status not null default 'active',
  url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Пункты актов. Пока текстовая ссылка (paragraph_ref + version_date);
-- когда JurisBase даст стабильные ID пунктов — добавится колонка, ссылки не ломаются.
create table public.act_paragraphs (
  id uuid primary key default gen_random_uuid(),
  act_id uuid not null references public.acts(id) on delete cascade,
  paragraph_ref text not null,
  version_date date,
  verbatim_uz text,
  verbatim_ru text,
  verbatim_en text,
  deep_link_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index act_paragraphs_ref_version_uidx
  on public.act_paragraphs (act_id, paragraph_ref, coalesce(version_date, '0001-01-01'::date));

-- Событие изменения источника (из JurisBase-diff или вручную)
create table public.change_events (
  id uuid primary key default gen_random_uuid(),
  source public.change_source not null default 'manual',
  act_id uuid references public.acts(id) on delete set null,
  paragraph_id uuid references public.act_paragraphs(id) on delete set null,
  event_type public.change_event_type not null,
  title text not null,
  summary text,
  was_text text,
  now_text text,
  importance public.importance_level not null default 'medium',
  effective_date date,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- ТРЕБОВАНИЯ (ядро). Машинные атрибуты здесь; весь текст — в contents/details.
-- ----------------------------------------------------------------------------

create table public.requirements (
  id uuid primary key default gen_random_uuid(),
  status public.requirement_status not null default 'draft',
  -- флаг «источник изменился, проверяется обновление» поверх published (§5b)
  review_flag public.review_flag not null default 'none',
  flagged_at timestamptz,
  flagged_by_event_id uuid references public.change_events(id) on delete set null,
  deontic public.deontic_type not null,
  addressee_roles public.party_role[] not null default '{}',
  operation public.operation_domain not null,
  transport_type public.transport_type,
  lifecycle_stage_id uuid references public.lifecycle_stages(id) on delete set null,
  authority_id uuid references public.authorities(id) on delete set null,
  confidence_score numeric(3,2) check (confidence_score between 0 and 1),
  trust_label public.trust_label not null default 'ai_draft',
  origin public.requirement_origin not null default 'manual',
  -- идемпотентный ключ конвейера Bridge — защита от дублей
  external_key text unique,
  -- аудит-след ревью
  created_by uuid references auth.users(id) on delete set null,
  reviewed_by uuid references auth.users(id) on delete set null,
  reviewed_at timestamptz,
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- §2 П6: требование без адресата не публикуется
  constraint requirements_published_needs_roles
    check (status <> 'published' or cardinality(addressee_roles) > 0)
);

create index requirements_status_idx on public.requirements (status);
create index requirements_review_flag_idx on public.requirements (review_flag) where review_flag <> 'none';
create index requirements_operation_idx on public.requirements (operation);
create index requirements_lifecycle_stage_idx on public.requirements (lifecycle_stage_id);

-- Уровень 0 — тизер (бесплатный): заголовок-глагол + санкция одной строкой.
-- Мультиязычность: по строке на язык.
create table public.requirement_contents (
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  lang public.lang_code not null,
  title text not null,
  sanction_summary text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (requirement_id, lang)
);

-- Уровень 1 — платный: описание, шаги исполнения, документы, полные санкции.
-- Отдельная таблица = серверная граница пейволла (RLS), не фронт-гейт.
create table public.requirement_details (
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  lang public.lang_code not null,
  description text,
  -- [{ "step": text, "deadline": text|null, "cost": text|null }]
  how_to_comply jsonb not null default '[]'::jsonb,
  -- [{ "name": text, "where_to_get": text|null, "note": text|null }]
  documents jsonb not null default '[]'::jsonb,
  -- [{ "amount": text, "article": text|null, "extra": text|null }]
  sanctions jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (requirement_id, lang)
);

-- Применимость: requirement <-> код/класс/все товары (двойная индексация ТН ВЭД + ИКПУ)
create table public.requirement_applicability (
  id uuid primary key default gen_random_uuid(),
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  scope public.applicability_scope not null,
  code text check (code ~ '^[0-9]+$'),
  created_at timestamptz not null default now(),
  constraint applicability_code_presence check (
    (scope in ('all_products', 'all_services') and code is null)
    or (scope not in ('all_products', 'all_services') and code is not null)
  )
);

create index requirement_applicability_req_idx on public.requirement_applicability (requirement_id);
create index requirement_applicability_scope_code_idx on public.requirement_applicability (scope, code);
create unique index requirement_applicability_uidx
  on public.requirement_applicability (requirement_id, scope, coalesce(code, ''));

-- Уровень 2 — юридический слой: requirement <-> пункт акта
create table public.requirement_citations (
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  paragraph_id uuid not null references public.act_paragraphs(id) on delete restrict,
  is_primary boolean not null default false,
  sort_order int not null default 0,
  created_at timestamptz not null default now(),
  primary key (requirement_id, paragraph_id)
);

-- обратный поиск: «какие требования цитируют этот пункт» — сердце конвейера уведомлений
create index requirement_citations_paragraph_idx on public.requirement_citations (paragraph_id);

-- История: jsonb-снапшот всей карточки при каждой публикации.
-- Закрывает «было/стало» уровня 2 и аудит-след ревью.
create table public.requirement_revisions (
  id uuid primary key default gen_random_uuid(),
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  revision_no int not null,
  snapshot jsonb not null,
  change_note text,
  change_event_id uuid references public.change_events(id) on delete set null,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (requirement_id, revision_no)
);

-- ----------------------------------------------------------------------------
-- ПОЛЬЗОВАТЕЛИ
-- ----------------------------------------------------------------------------

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text not null default '',
  phone text,
  company text,
  is_subscribed boolean not null default false,
  subscribed_until timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, full_name, phone)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'full_name', ''),
    new.raw_user_meta_data ->> 'phone'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Избранное («мои товары») — источник персональных уведомлений
create table public.chosen_products (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  product_id uuid references public.products(id) on delete cascade,
  service_id uuid references public.services(id) on delete cascade,
  created_at timestamptz not null default now(),
  constraint chosen_products_one_target check (num_nonnulls(product_id, service_id) = 1)
);

create unique index chosen_products_user_product_uidx
  on public.chosen_products (user_id, product_id) where product_id is not null;
create unique index chosen_products_user_service_uidx
  on public.chosen_products (user_id, service_id) where service_id is not null;

-- Заявки на подписку (ручная активация до подключения Click)
create table public.subscription_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  full_name text not null,
  contact text not null,
  company text,
  status public.subscription_request_status not null default 'new',
  note text,
  handled_at timestamptz,
  created_at timestamptz not null default now()
);

-- Заявки «наполните этот товар / раздел в работе» — приоритет №1 очереди наполнения (§5b)
create table public.content_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  kind public.content_request_kind not null,
  product_id uuid references public.products(id) on delete set null,
  service_id uuid references public.services(id) on delete set null,
  query_text text,
  comment text,
  status public.content_request_status not null default 'new',
  created_at timestamptz not null default now()
);

-- Вопросы пользователей — воронка AI -> эксперт -> GR (§5a). user_id обязателен.
create table public.user_questions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  requirement_id uuid references public.requirements(id) on delete set null,
  product_id uuid references public.products(id) on delete set null,
  question_text text not null,
  is_urgent boolean not null default false,
  legal_review_only boolean not null default false,
  allow_official_request boolean not null default false,
  status public.question_status not null default 'new',
  answer_text text,
  answered_at timestamptz,
  response_file_url text,
  created_at timestamptz not null default now()
);

create index user_questions_user_idx on public.user_questions (user_id);
create index user_questions_requirement_idx on public.user_questions (requirement_id);

-- FAQ требования. source_question_id: официальный GR-ответ обезличенно обогащает FAQ (§5a)
create table public.requirement_faqs (
  id uuid primary key default gen_random_uuid(),
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  lang public.lang_code not null default 'ru',
  question text not null,
  answer text not null,
  trust_label public.trust_label not null default 'ai_draft',
  source_question_id uuid references public.user_questions(id) on delete set null,
  sort_order int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index requirement_faqs_req_lang_idx on public.requirement_faqs (requirement_id, lang);

-- ----------------------------------------------------------------------------
-- ИЗМЕНЕНИЯ -> ЗАТРОНУТЫЕ ТРЕБОВАНИЯ -> ПЕРСОНАЛЬНЫЕ УВЕДОМЛЕНИЯ
-- ----------------------------------------------------------------------------

-- Ревьюерское решение «это событие затрагивает это требование»
create table public.requirement_change_impacts (
  id uuid primary key default gen_random_uuid(),
  change_event_id uuid not null references public.change_events(id) on delete cascade,
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  status public.impact_status not null default 'pending_review',
  action_required text,
  is_in_favor boolean,
  reviewed_by uuid references auth.users(id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (change_event_id, requirement_id)
);

create index requirement_change_impacts_req_idx on public.requirement_change_impacts (requirement_id);

-- Материализованные per-user уведомления: read-статус и каскад счётчиков
-- (лента -> товар -> строка требования) требуют строки на пользователя.
create table public.user_notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  impact_id uuid not null references public.requirement_change_impacts(id) on delete cascade,
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  product_id uuid references public.products(id) on delete set null,
  service_id uuid references public.services(id) on delete set null,
  is_read boolean not null default false,
  read_at timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, impact_id)
);

create index user_notifications_user_read_idx on public.user_notifications (user_id, is_read);

-- ----------------------------------------------------------------------------
-- updated_at триггеры
-- ----------------------------------------------------------------------------

do $$
declare
  t text;
begin
  foreach t in array array[
    'products', 'services', 'acts', 'act_paragraphs', 'requirements',
    'requirement_contents', 'requirement_details', 'requirement_faqs', 'profiles'
  ]
  loop
    execute format(
      'create trigger set_updated_at before update on public.%I
         for each row execute function public.set_updated_at()',
      t
    );
  end loop;
end;
$$;
