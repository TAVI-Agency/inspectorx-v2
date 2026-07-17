-- Импортёр deep-research отчётов: staging-слой (спека 2026-07-12-report-importer-design.md).
-- import_runs / import_items — аудит, review-очередь и золотой датасет решений.
-- requirement_sources — провенанс «какие модели/отчёты нашли требование».

alter type public.trust_label add value if not exists 'validated';

create table public.import_runs (
  id uuid primary key default gen_random_uuid(),
  file_name text not null,
  file_hash text not null unique,
  subject_kind text not null check (subject_kind in ('product', 'service')),
  subject_slug text not null,
  model text not null,
  status text not null default 'parsed' check (status in ('parsed', 'failed', 'loaded')),
  loaded_count int not null default 0,
  merged_count int not null default 0,
  review_count int not null default 0,
  raw_json jsonb,
  gray_zones text[] not null default '{}',
  error text,
  created_at timestamptz not null default now()
);

create table public.import_items (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.import_runs(id) on delete cascade,
  idx int not null,
  raw jsonb not null,
  status text not null check (status in ('loaded', 'merged', 'review', 'rejected')),
  review_reason text,
  review_detail text,
  requirement_id uuid references public.requirements(id) on delete set null,
  resolution text not null default 'pending'
    check (resolution in ('pending', 'approved', 'fixed', 'rejected')),
  resolved_by uuid references auth.users(id) on delete set null,
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  unique (run_id, idx)
);

create index import_items_review_idx on public.import_items (status) where status = 'review';

create table public.requirement_sources (
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  import_item_id uuid not null references public.import_items(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (requirement_id, import_item_id)
);

-- Только service role: RLS включён, политик нет.
alter table public.import_runs enable row level security;
alter table public.import_items enable row level security;
alter table public.requirement_sources enable row level security;
