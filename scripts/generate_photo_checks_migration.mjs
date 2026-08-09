#!/usr/bin/env node
/**
 * Генератор миграции-контента requirement_photo* из выгрузки vision
 * (Задача 15, этап 6 плана фотоконтроля, «правила как данные»).
 *
 * Вход:  JSON `scripts/export_checks.py` (inspectorx-vision), контракт —
 *        {ruleset_sha256, schema, requirements: [{rule_ref, pack, title_ru,
 *        checkability, packaging_level, why, markets, applicability,
 *        source, checks: [...], [requirement_id]}]}.
 * Выход: SQL в stdout — `insert into requirement_photo ... on conflict
 *        (rule_ref) do update` и `insert into requirement_photo_checks ...
 *        on conflict (rule_ref, check_id) do update`.
 *
 * ВЫГРУЗКА ОДНОСТОРОННЯЯ И ИДЕМПОТЕНТНАЯ: правка контента в базе руками
 * запрещена — следующий прогон этого генератора её перетрёт (`do update`
 * пишет ПОВЕРХ существующей строки, не пропускает её). DELETE намеренно не
 * печатается: требование, исчезнувшее из YAML, здесь не убирается — уборка
 * осиротевших rule_ref их не в этом скрипте (следующий разбор).
 *
 * Запуск:
 *   cd inspectorx-vision && ./.venv/bin/python -m ixvision export --out runs/checks_export.json
 *   cd inspector-x-final
 *   node scripts/generate_photo_checks_migration.mjs \
 *     ../inspectorx-vision/runs/checks_export.json \
 *     > supabase/migrations/20260810140000_photo_checks_content.sql
 */
import { readFileSync } from 'node:fs'

const srcPath = process.argv[2]
if (!srcPath) {
  console.error('использование: node generate_photo_checks_migration.mjs <checks_export.json>')
  process.exit(2)
}

const doc = JSON.parse(readFileSync(srcPath, 'utf8'))

// Строки со спецсимволами (кавычки, обратные слэши, переносы в цитатах из
// закона) — через dollar-quoting, а не удвоение кавычек: юридические цитаты
// бьют наивное экранирование чаще, чем кажется. Тег подбирается так, чтобы
// он не встречался в самой строке (на практике всегда $txt$ с первой попытки).
function sqlText(v) {
  if (v === null || v === undefined) return 'null'
  const s = String(v)
  let tag = 'txt'
  let n = 0
  while (s.includes(`$${tag}$`)) tag = `txt${n++}`
  return `$${tag}$${s}$${tag}$`
}

function sqlJson(v) {
  return `${sqlText(JSON.stringify(v ?? {}))}::jsonb`
}

function sqlTextArray(arr) {
  const items = (arr ?? []).map((v) => sqlText(v))
  return `array[${items.join(', ')}]::text[]`
}

function sqlEnum(v, type) {
  if (v === null || v === undefined) return 'null'
  return `${sqlText(v)}::public.${type}`
}

function emitRequirement(out, r) {
  const app = r.applicability ?? { scope: 'hs_prefix', hs_prefixes: [] }
  const reqId = r.requirement_id ? `${sqlText(r.requirement_id)}::uuid` : 'null'
  out.push(
    `insert into public.requirement_photo ` +
      `(rule_ref, requirement_id, pack, title_ru, checkability, packaging_level, why, ` +
      `markets, scope, hs_prefixes, source, ruleset_sha256) values (` +
      `${sqlText(r.rule_ref)}, ${reqId}, ${sqlText(r.pack)}, ${sqlText(r.title_ru)}, ` +
      `${sqlEnum(r.checkability, 'photo_checkability')}, ` +
      `${sqlEnum(r.packaging_level, 'photo_packaging_level')}, ${sqlText(r.why)}, ` +
      `${sqlTextArray(r.markets)}, ${sqlText(app.scope)}, ${sqlTextArray(app.hs_prefixes)}, ` +
      `${sqlJson(r.source)}, ${sqlText(doc.ruleset_sha256)}` +
      `)\n  on conflict (rule_ref) do update set ` +
      `requirement_id = excluded.requirement_id, pack = excluded.pack, ` +
      `title_ru = excluded.title_ru, checkability = excluded.checkability, ` +
      `packaging_level = excluded.packaging_level, why = excluded.why, ` +
      `markets = excluded.markets, scope = excluded.scope, ` +
      `hs_prefixes = excluded.hs_prefixes, source = excluded.source, ` +
      `ruleset_sha256 = excluded.ruleset_sha256;`
  )
}

function emitCheck(out, r, c, ord) {
  out.push(
    `insert into public.requirement_photo_checks ` +
      `(rule_ref, check_id, ord, kind, severity, group_key, subject, packaging_level, ` +
      `target, question_ru, measure, params, hint_ru, title_ru) values (` +
      `${sqlText(r.rule_ref)}, ${sqlText(c.id)}, ${ord}, ` +
      `${sqlEnum(c.kind, 'photo_check_kind')}, ${sqlEnum(c.severity, 'photo_severity')}, ` +
      `${sqlText(c.group)}, ${sqlText(c.subject)}, ` +
      `${sqlEnum(c.level, 'photo_packaging_level')}, ` +
      `${sqlText(c.target)}, ${sqlText(c.question_ru)}, ${sqlText(c.measure)}, ` +
      `${sqlJson(c.params)}, ${sqlText(c.hint_ru)}, ${sqlText(c.title_ru)}` +
      `)\n  on conflict (rule_ref, check_id) do update set ` +
      `ord = excluded.ord, kind = excluded.kind, severity = excluded.severity, ` +
      `group_key = excluded.group_key, subject = excluded.subject, ` +
      `packaging_level = excluded.packaging_level, target = excluded.target, ` +
      `question_ru = excluded.question_ru, measure = excluded.measure, ` +
      `params = excluded.params, hint_ru = excluded.hint_ru, title_ru = excluded.title_ru;`
  )
}

const out = []
out.push('-- Сгенерировано scripts/generate_photo_checks_migration.mjs — не редактировать руками.')
out.push(`-- Источник: ruleset_sha256=${doc.ruleset_sha256}, требований=${doc.requirements.length}.`)
out.push(
  '-- Односторонняя выгрузка YAML-пакетов inspectorx-vision → requirement_photo*.'
)
out.push(
  '-- Идемпотентно (on conflict … do update): следующий прогон перетирает ручные правки.'
)
out.push('')

for (const r of doc.requirements) {
  emitRequirement(out, r)
  r.checks.forEach((c, i) => emitCheck(out, r, c, i))
  out.push('')
}

process.stdout.write(out.join('\n') + '\n')
