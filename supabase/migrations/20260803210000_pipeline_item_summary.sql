-- ============================================================================
-- InspectorX v2 — pipeline.items.summary_text (Задача 27, фикс-раунд ревью)
--
-- Дедуп (шаг 'dedup', importer/build/steps_dedup.py) сравнивает ТЕКУЩИЙ
-- айтем прогона по его саммари с УЖЕ ОБРАБОТАННЫМИ айтемами того же
-- прогона (BuildStore.list_run_item_texts). Раньше pipeline.items не хранил
-- summary вообще — кандидаты всегда отдавались по expected_item (входной
-- текст карты), а текущий айтем сравнивался по summary (если шаг 'summary'
-- уже отработал) — асимметричное сравнение summary-vs-expected_item срывало
-- дедуп парафразов одного требования (найдено фикс-раундом ревью Задачи 27,
-- Important №3).
--
-- summary_text — персистентная колонка, которую пишет шаг 'summary'
-- (steps_norm.py:SummaryStep, через BuildStore.set_item_summary) сразу
-- после успешной верификации саммари. list_run_item_texts теперь отдаёт
-- coalesce(summary_text, expected_item) — симметричное сравнение
-- summary-vs-summary там, где summary уже есть, с честным фолбэком на
-- expected_item для айтемов, которые до 'summary' ещё не дошли.
--
-- Примечание про имя файла: timestamp этой миграции НЕ совпадает с
-- 20260803200000_pipeline_coverage_report.sql (первый коммит Задачи 27) —
-- намеренно; два файла с байт-в-байт идентичным timestamp-префиксом рискуют
-- версионным конфликтом в supabase_migrations.schema_migrations
-- (PostgREST/Supabase CLI ключуют применённые миграции по version).
-- ============================================================================

alter table pipeline.items
  add column if not exists summary_text text;

comment on column pipeline.items.summary_text is
  'Саммари требования (шаг ''summary'', steps_norm.py:SummaryStep) — пишется '
  'через BuildStore.set_item_summary сразу после успешной верификации. '
  'Используется list_run_item_texts как приоритетный текст сравнения для '
  'дедупа (шаг ''dedup''), coalesce с expected_item, если summary ещё не '
  'произведён.';
