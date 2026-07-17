-- Фаза 2 UZ-first (спека 2026-07-16 §2): признак происхождения текста строки.
-- 'verbatim' — дословный текст источника/отчёта; 'machine' — машинный перевод.
-- Старые строки остаются NULL (легаси до фазы 2). Аддитивно, RLS не меняется.

create type public.translation_origin as enum ('verbatim', 'machine');

alter table public.requirement_contents
  add column if not exists translation_origin public.translation_origin;

alter table public.requirement_details
  add column if not exists translation_origin public.translation_origin;
