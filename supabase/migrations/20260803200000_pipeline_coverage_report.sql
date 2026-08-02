-- ============================================================================
-- InspectorX v2 — pipeline.runs.coverage_report (Задача 27)
--
-- Coverage-отчёт (importer/build/coverage.py:coverage_report) — markdown,
-- посчитанный Orchestrator.run_group ПОСЛЕ цикла по айтемам (и отдельной
-- CLI-командой `build coverage --run <id>` для восстановления по уже
-- завершённому прогону). Персистится, чтобы не пересчитывать при каждом
-- обращении и чтобы оператор видел ровно тот отчёт, что был на момент
-- прогона (verdicts/items с тех пор не меняются задним числом).
-- ============================================================================

alter table pipeline.runs
  add column if not exists coverage_report text;

comment on column pipeline.runs.coverage_report is
  'Markdown coverage-отчёта (карта vs факт, Задача 27) — считается '
  'Orchestrator.run_group после цикла по айтемам и CLI `build coverage --run <id>`.';
