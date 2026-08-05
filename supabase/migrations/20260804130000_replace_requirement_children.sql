-- ============================================================================
-- InspectorX v2 — гейт первого живого прогона, пункт 1 (docs/LAUNCH_CHECKLIST.md
-- «Гейт первого живого прогона»): транзакционность `save_requirement_draft`.
--
-- ПРОБЛЕМА. `SupabaseBuildStore.save_requirement_draft` (`importer/build/
-- orchestrator.py`) заменяет дочерние строки требования (`requirement_contents`/
-- `requirement_details`/`requirement_applicability`/`requirement_rules`)
-- четырьмя НЕЗАВИСИМЫМИ парами delete+insert через PostgREST — восемь
-- отдельных HTTP-вызовов, каждый в СВОЕЙ транзакции. Сбой сети/процесса
-- посередине (например, между `delete` и `insert` для `requirement_details`
-- уже `published`-требования) оставляет строку `requirements` в статусе
-- `published`, но без контента: RLS-таблицы (`requirement_contents`/
-- `requirement_details`) отдают пусто, карточка МОЛЧА исчезает с витрины,
-- хотя формально существует (`requirements.status = 'published'`).
--
-- ФИКС. Одна SQL-функция `replace_requirement_children`, вызываемая ОДНИМ
-- PostgREST RPC (`.rpc(...).execute()` — один HTTP-запрос, одна Postgres-
-- транзакция на весь вызов функции): delete+insert по всем 4 таблицам
-- атомарны вместе — либо все восемь операций применяются, либо ни одна.
--
-- Формат jsonb-параметров — ТЕ ЖЕ построчные dict'ы, что раньше собирал и
-- передавал в PostgREST insert Python-код (`SupabaseBuildStore.
-- save_requirement_draft`) — функция явно перечисляет только реально
-- используемые колонки (см. `importer/build/assembler.py:_build_card`),
-- НЕ полагаясь на `jsonb_populate_recordset` со всем составом строки:
-- отсутствующие в JSON колонки со значением по умолчанию (`created_at`/
-- `updated_at`/`id`) обязаны получить DEFAULT, а не явный NULL — явный
-- список колонок в INSERT это гарантирует, `jsonb_populate_recordset`
-- поверх `null::table_type` — нет (пишет NULL в отсутствующие ключи и
-- ломает NOT NULL DEFAULT now()).
-- ============================================================================

create or replace function public.replace_requirement_children(
  p_requirement_id uuid,
  p_contents jsonb,       -- [{"lang", "title", "sanction_summary", "translation_origin"}]
  p_details jsonb,        -- [{"lang", "description", "how_to_comply", "documents",
                           --   "sanctions", "court_cases", "templates",
                           --   "lawyer_instruction", "status_note", "translation_origin"}]
  p_applicability jsonb,  -- {"scope", "code", "product_type_id"} | null (0..1 строка,
                           --   ровно семантика старого кода: `if applicability: insert`)
  p_rules jsonb           -- [{"rule", "verified"}]
)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  -- requirement_contents — replace-семантика (докстринг steps_load.py):
  -- полностью пересобираем набор строк требования на каждый вызов.
  delete from public.requirement_contents where requirement_id = p_requirement_id;
  insert into public.requirement_contents (requirement_id, lang, title, sanction_summary, translation_origin)
  select
    p_requirement_id,
    (elem ->> 'lang')::public.lang_code,
    elem ->> 'title',
    elem ->> 'sanction_summary',
    (elem ->> 'translation_origin')::public.translation_origin
  from jsonb_array_elements(coalesce(p_contents, '[]'::jsonb)) as elem;

  delete from public.requirement_details where requirement_id = p_requirement_id;
  insert into public.requirement_details (
    requirement_id, lang, description, how_to_comply, documents, sanctions,
    court_cases, templates, lawyer_instruction, status_note, translation_origin
  )
  select
    p_requirement_id,
    (elem ->> 'lang')::public.lang_code,
    elem ->> 'description',
    coalesce(elem -> 'how_to_comply', '[]'::jsonb),
    coalesce(elem -> 'documents', '[]'::jsonb),
    coalesce(elem -> 'sanctions', '[]'::jsonb),
    elem -> 'court_cases',
    elem -> 'templates',
    elem -> 'lawyer_instruction',
    elem ->> 'status_note',
    (elem ->> 'translation_origin')::public.translation_origin
  from jsonb_array_elements(coalesce(p_details, '[]'::jsonb)) as elem;

  -- requirement_applicability — старый код вставлял МАКСИМУМ одну строку
  -- (`applicability = card.get("applicability"); if applicability: insert`,
  -- см. докстринг `save_requirement_draft`) — та же семантика: `p_applicability`
  -- НЕ массив, а один объект либо SQL/jsonb NULL.
  delete from public.requirement_applicability where requirement_id = p_requirement_id;
  if p_applicability is not null and p_applicability <> 'null'::jsonb then
    insert into public.requirement_applicability (requirement_id, scope, code, product_type_id)
    values (
      p_requirement_id,
      (p_applicability ->> 'scope')::public.applicability_scope,
      p_applicability ->> 'code',
      nullif(p_applicability ->> 'product_type_id', '')::uuid
    );
  end if;

  delete from public.requirement_rules where requirement_id = p_requirement_id;
  insert into public.requirement_rules (requirement_id, rule, verified)
  select
    p_requirement_id,
    elem -> 'rule',
    coalesce((elem ->> 'verified')::boolean, false)
  from jsonb_array_elements(coalesce(p_rules, '[]'::jsonb)) as elem;
end;
$$;

comment on function public.replace_requirement_children(uuid, jsonb, jsonb, jsonb, jsonb) is
  'Гейт живого прогона, пункт 1 (LAUNCH_CHECKLIST.md): атомарная замена '
  'requirement_contents/_details/_applicability/_rules ОДНОЙ транзакцией — '
  'вызывается SupabaseBuildStore.save_requirement_draft вместо 4×(delete+insert) '
  'отдельными PostgREST-запросами, чтобы сбой посередине не оставлял '
  'published-требование без контента на витрине.';

-- Вызывается ТОЛЬКО из importer/ (SupabaseBuildStore, service-ключ) — тот же
-- паттерн explicit revoke/grant, что и 20260804110000_ingest_change_event.sql
-- (default ACL схемы public иначе выдал бы EXECUTE anon/authenticated/
-- service_role автоматически на каждую новую функцию).
revoke all on function public.replace_requirement_children(uuid, jsonb, jsonb, jsonb, jsonb) from public;
revoke all on function public.replace_requirement_children(uuid, jsonb, jsonb, jsonb, jsonb) from anon, authenticated;
grant execute on function public.replace_requirement_children(uuid, jsonb, jsonb, jsonb, jsonb) to service_role;
