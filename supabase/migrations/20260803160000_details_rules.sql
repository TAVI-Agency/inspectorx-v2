-- Расширение requirement_details и создание requirement_rules (Задача 10)

-- Добавляем новые колонки к requirement_details
alter table public.requirement_details
  add column court_cases jsonb,         -- [{case_url, case_title, summary, outcome, amount}] ≤5, снапшот SudX
  add column templates jsonb,           -- [{name, source_url, note}] от Template hunter
  add column lawyer_instruction jsonb,  -- {verdict, steps: [text]} от In-house lawyer
  add column status_note text;          -- пояснение юриста к бейджу статуса («что успеть до даты X»)

comment on column public.requirement_details.court_cases is 'Снимок релевантных судебных кейсов (≤5) из SudX';
comment on column public.requirement_details.templates is 'Шаблоны документов от Template hunter';
comment on column public.requirement_details.lawyer_instruction is 'Рекомендации in-house юриста: {verdict, steps: [text]}';
comment on column public.requirement_details.status_note is 'Пояснение юриста к бейджу статуса';

-- Создаём таблицу machine-readable правил (пишут Задачи 19, 22–24, 26; читает витрина Задача 31)
create table public.requirement_rules (
  id uuid primary key default gen_random_uuid(),
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  rule jsonb not null,                  -- {"field":"состав","lang":"uz","required":true} | {"barcode":"EAN-13"} | …
  verified boolean not null default false,
  created_at timestamptz not null default now()
);

comment on table public.requirement_rules is 'Machine-readable правила проверки: логика обогащения, валидация, инструкции Rule-maker';
comment on column public.requirement_rules.requirement_id is 'Ссылка на требование';
comment on column public.requirement_rules.rule is 'Структурированное правило (поле, формат, условие и т.п.)';
comment on column public.requirement_rules.verified is 'Флаг верификации юристом';
comment on column public.requirement_rules.created_at is 'Время создания';

-- Включаем RLS
alter table public.requirement_rules enable row level security;

-- Политика чтения requirement_rules: как requirement_details (подписчики и верифицированные юристы)
create policy "subscriber read" on public.requirement_rules
  for select to authenticated
  using (
    (public.is_subscriber() or public.is_verified_lawyer())
    and exists (
      select 1 from public.requirements r
      where r.id = requirement_id and r.status = 'published'
    )
  );

-- Запись: только service_role (нет политики — по умолчанию запрещено всем кроме service_role)
