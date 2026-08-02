-- ============================================================================
-- InspectorX v2 — фикс check-constraint requirement_applicability под
-- канонический scope='product_type' (ADR-0004)
--
-- Найдено ревью Задачи 26 (Build-конвейер, importer/build/steps_load.py):
-- 20260803130000_scope_product_type.sql добавил колонку product_type_id и
-- enum-значение 'product_type' (канонический путь ADR-0004 — «карточки
-- требований привязываются ТОЛЬКО к product_type_id»), но НЕ обновил старый
-- constraint applicability_code_presence из 20260711120000_initial_schema.sql:
--
--   (scope in ('all_products', 'all_services') and code is null)
--   or (scope not in ('all_products', 'all_services') and code is not null)
--
-- Для НОВОЙ строки scope='product_type' (без легаси code — только
-- product_type_id) второй branch требует code IS NOT NULL, которого у
-- product_type-строки нет и не может быть — INSERT падает с нарушением
-- constraint. Гейт мёржа Блока 1 ещё не пройден (миграции этой ветки в main
-- не попали) — фикс кладём отдельной миграцией, а не правкой уже
-- существующей (никто её ещё не применял на проде).
-- ============================================================================

alter table public.requirement_applicability
  drop constraint applicability_code_presence;

-- code обязателен ТОЛЬКО у точных/префиксных национальных кодов; у
-- all_products/all_services (норма общего действия) и product_type
-- (канонический ADR-0004 путь — точка привязки product_type_id, не code)
-- code остаётся NULL.
alter table public.requirement_applicability
  add constraint applicability_code_presence check (
    (scope in ('hs_code', 'hs_prefix', 'ikpu_code', 'ikpu_prefix', 'oked_code', 'oked_prefix')
      and code is not null)
    or (scope in ('all_products', 'all_services', 'product_type')
      and code is null)
  );

-- scope='product_type' без product_type_id — бессмысленная строка (нет
-- точки привязки вообще, ни code, ни product_type_id).
alter table public.requirement_applicability
  add constraint applicability_product_type_requires_id check (
    scope <> 'product_type' or product_type_id is not null
  );

comment on constraint applicability_code_presence on public.requirement_applicability is
  'code обязателен для scope с национальным кодом (hs_code/hs_prefix/ikpu_code/ikpu_prefix/oked_code/oked_prefix); '
  'NULL для all_products/all_services/product_type (Задача 26, фикс-раунд ревью).';
comment on constraint applicability_product_type_requires_id on public.requirement_applicability is
  'scope=product_type (канонический путь ADR-0004) обязан нести product_type_id — единственную точку привязки.';
