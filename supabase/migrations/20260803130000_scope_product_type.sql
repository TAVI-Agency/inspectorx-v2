-- ============================================================================
-- InspectorX v2 — scope требований → product_type_id (ADR-0004)
-- Мост между старой строковой применимостью (hs_code/hs_prefix/ikpu_code/
-- ikpu_prefix/oked_code/oked_prefix/all_products/all_services) и каноническим
-- catalog.product_types. Старые колонки scope/code НЕ удаляются — переходный
-- период; удаление отдельной миграцией после приёмки Блока 4.
--
-- ВАЖНО (ограничение Postgres): добавленное enum-значение нельзя использовать
-- в той же транзакции, где оно создано, а каждая supabase-миграция катится в
-- своей транзакции. Поэтому эта миграция только добавляет значение
-- 'product_type' в enum на будущее (канонический scope, ADR-0004) и НЕ
-- проставляет его существующим строкам — scope старых строк не меняется,
-- меняется только колонка product_type_id.
-- ============================================================================

alter table public.requirement_applicability
  add column product_type_id uuid references catalog.product_types(id);
create index requirement_applicability_product_type_idx
  on public.requirement_applicability (product_type_id);

comment on column public.requirement_applicability.product_type_id is
  'Канонический тип (ADR-0004). Бэкофилл из scope/code этой же миграцией; '
  'NULL у all_products/all_services (нет типа-цели) и у широких *_prefix, '
  'которые покрывают больше одного product_type — см. отчёт задачи 7.';

alter type public.applicability_scope add value if not exists 'product_type';

-- ----------------------------------------------------------------------------
-- Бэкофилл: точные коды (hs_code/ikpu_code/oked_code) — прямое совпадение
-- code в catalog.country_codes. Страна берётся из requirements.jurisdiction
-- (сейчас везде 'UZ' по умолчанию, см. 20260803120000_jurisdiction.sql).
-- ----------------------------------------------------------------------------
update public.requirement_applicability ra
set product_type_id = cc.product_type_id
from public.requirements r, catalog.country_codes cc
where ra.requirement_id = r.id
  and ra.scope in ('hs_code', 'ikpu_code', 'oked_code')
  and cc.country = r.jurisdiction
  and cc.system = case ra.scope
        when 'hs_code' then 'tnved'
        when 'ikpu_code' then 'ikpu'
        when 'oked_code' then 'oked'
      end
  and cc.code = ra.code;

-- ----------------------------------------------------------------------------
-- Бэкофилл: префиксные scope (hs_prefix/ikpu_prefix/oked_prefix) — только
-- если префикс однозначно указывает на один product_type (все код-строки
-- catalog.country_codes, начинающиеся с этого префикса, ведут к одному и
-- тому же product_type_id). Если префикс шире одного типа — намеренно
-- оставляем NULL: широкие scope выше HS6 закроются логикой конвейера позже
-- (см. отчёт задачи 7 для фактического числа таких строк).
-- ----------------------------------------------------------------------------
-- uuid не поддерживает min()/max() — однозначность префикса проверяем через
-- array_agg(distinct …): ровно один элемент значит один product_type.
update public.requirement_applicability ra
set product_type_id = (
  select s.ids[1]
  from (
    select array_agg(distinct cc.product_type_id) as ids
    from catalog.country_codes cc
    where cc.country = r.jurisdiction
      and cc.system = case ra.scope
            when 'hs_prefix' then 'tnved'
            when 'ikpu_prefix' then 'ikpu'
            when 'oked_prefix' then 'oked'
          end
      and cc.code like ra.code || '%'
  ) s
  where array_length(s.ids, 1) = 1
)
from public.requirements r
where ra.requirement_id = r.id
  and ra.scope in ('hs_prefix', 'ikpu_prefix', 'oked_prefix');
