#!/usr/bin/env node
/**
 * Сид каталога (ADR-0004): наполняет catalog.product_types + catalog.country_codes
 * из уже существующих public.products (ТН ВЭД-10) и public.services (ОКЭД/ИКПУ),
 * плюс добавляет колонку-мост product_type_id на products/services и заполняет её.
 *
 * Источник данных — локальная БД ПОСЛЕ `supabase db reset --local` (читаем через
 * `supabase db query --local -o json`, а не парсим SQL-файлы миграций текстом —
 * так надёжнее; см. задачу 5, решение контроллера 02.08.2026). Новый npm-пакет
 * для Postgres не добавляем: `supabase db query` уже даёт JSON поверх локального
 * докер-стека.
 *
 * Правила:
 *  - id типов — детерминированный uuid (md5-паттерн, как в generate_services_seed.mjs
 *    и generate_v1_content_migration.mjs), чтобы перегенерация не меняла id;
 *  - товары: тип каталога = HS6-префикс (первые 6 цифр 10-значного ТН ВЭД).
 *    Имя типа — категорийное, из hierarchy_path (fix после ревью задачи 5:
 *    первая версия брала «имя с наименьшей длиной среди товаров группы» и на
 *    части групп давала невыразительное «прочие»/«прочее»). Берём для каждого
 *    товара группы путь [category_name, ...levels] (от общего к частному) и
 *    ищем самый длинный общий префикс путей всех товаров HS6-группы — это и
 *    есть «ближайший к HS6 категорийный уровень, общий для всей группы».
 *    Имя типа = последний элемент этого префикса (для группы из 1 товара он
 *    совпадает с полным путём, включая исходный name_ru). Фолбэк на прежнюю
 *    эвристику (имя с наименьшей длиной) — только если у товаров группы нет
 *    hierarchy_path или общий префикс пуст (в текущих данных не встречается,
 *    но код держит эту ветку на случай будущих товаров без разметки);
 *  - услуги: тип каталога = ОКЭД-код услуги, UNSPSC — из константы
 *    UNSPSC_BY_OKED. ОКЭД без записи в константе получают синтетический
 *    UNSPSC-код с пометкой «уточнить» (выводится в консоль и должно попасть
 *    в отчёт) — так, чтобы миграция не падала на новых услугах;
 *  - country_codes: 'tnved' для каждого товара (полный 10-значный код),
 *    'oked' для каждой услуги, 'ikpu' — только если ikpu_code заполнен
 *    в данных (сейчас у обеих услуг он пуст — не досочиняем).
 *
 * Запуск: node scripts/generate_catalog_seed.mjs
 */
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { writeFileSync } from 'node:fs'

const repoRoot = fileURLToPath(new URL('..', import.meta.url))

const md5 = (s) => createHash('md5').update(s, 'utf8').digest('hex')
const uuid = (key) => {
  const h = md5(`inspectorx-catalog:${key}`)
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20, 32)}`
}
const q = (v) => (v === null || v === undefined ? 'null' : `'${String(v).replaceAll("'", "''")}'`)

// Синтетический 8-значный UNSPSC-заглушка для услуг без записи в UNSPSC_BY_OKED —
// детерминированная (не случайная), чтобы повторный запуск давал тот же код.
const syntheticUnspsc = (okedCode) => {
  const n = parseInt(md5(`unspsc-todo:${okedCode}`).slice(0, 8), 16) % 10000000
  return `9${String(n).padStart(7, '0')}`
}

// --- соответствие ОКЭД -> UNSPSC (константа, расширяется по мере надобности) ---
const UNSPSC_BY_OKED = {
  '47.73': { code: '85121600', label: 'Pharmacists' }, // аптека
  '56.10': { code: '90101600', label: 'Ресторанные услуги' }, // кафе
}

function dbQuery(sql) {
  const raw = execFileSync(
    'supabase',
    ['db', 'query', sql, '--local', '-o', 'json', '--agent=no'],
    { cwd: repoRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
  )
  return JSON.parse(raw)
}

// --- читаем текущие данные из локальной БД ---------------------------------

const products = dbQuery(
  'select hs_code, name_ru, hierarchy_path from public.products order by hs_code;',
)
const services = dbQuery(
  "select oked_code, ikpu_code, name_ru from public.services order by oked_code;",
)

if (products.length === 0)
  throw new Error('public.products пуст — выполните supabase db start && supabase db reset --local')
if (services.length === 0)
  throw new Error('public.services пуст — выполните supabase db start && supabase db reset --local')

for (const p of products)
  if (!/^\d{10}$/.test(p.hs_code)) throw new Error(`hs_code не 10 цифр: ${p.hs_code}`)

// --- типы товаров: группировка по HS6 ---------------------------------------

const goodGroups = new Map() // hs6 -> [{ hs_code, name_ru, hierarchy_path }]
for (const p of products) {
  const hs6 = p.hs_code.slice(0, 6)
  if (!goodGroups.has(hs6)) goodGroups.set(hs6, [])
  goodGroups.get(hs6).push(p)
}

// Прежняя эвристика — теперь только фолбэк, если у группы нет hierarchy_path
// или общего категорийного уровня.
const shortestNameOf = (items) => [...items].sort((a, b) => a.name_ru.length - b.name_ru.length)[0].name_ru

// Путь товара «от общего к частному»: category_name, затем levels (v1-breadcrumb).
const categoryPathOf = (p) => [p.hierarchy_path?.category_name, ...(p.hierarchy_path?.levels ?? [])].filter(Boolean)

// Самый длинный общий префикс путей (поэлементное сравнение строк).
function longestCommonPrefix(paths) {
  if (paths.length === 0) return []
  let prefix = paths[0]
  for (const p of paths.slice(1)) {
    let i = 0
    while (i < prefix.length && i < p.length && prefix[i] === p[i]) i++
    prefix = prefix.slice(0, i)
    if (prefix.length === 0) break
  }
  return prefix
}

const namingSamples = [] // для отчёта: было (старая эвристика) -> стало (категорийное имя)
const goodTypes = new Map() // hs6 -> { id, hs6, name }
for (const [hs6, items] of goodGroups) {
  const paths = items.map(categoryPathOf)
  const lcp = longestCommonPrefix(paths)
  const oldName = shortestNameOf(items)
  const usedFallback = lcp.length === 0
  const name = usedFallback ? oldName : lcp[lcp.length - 1]
  goodTypes.set(hs6, { id: uuid(`product_type:good:${hs6}`), hs6, name })
  if (items.length > 1 && namingSamples.length < 5)
    namingSamples.push({ hs6, count: items.length, oldName, newName: name, usedFallback })
}

// --- типы услуг: ОКЭД -> UNSPSC ---------------------------------------------

const needsReview = [] // услуги без записи в UNSPSC_BY_OKED — в отчёт
const serviceTypes = [] // [{ id, oked, ikpu, unspsc, name }]
for (const s of services) {
  const mapped = UNSPSC_BY_OKED[s.oked_code]
  const unspsc = mapped ? mapped.code : syntheticUnspsc(s.oked_code)
  if (!mapped) needsReview.push({ oked: s.oked_code, name: s.name_ru, syntheticUnspsc: unspsc })
  serviceTypes.push({
    id: uuid(`product_type:service:${s.oked_code}`),
    oked: s.oked_code,
    ikpu: s.ikpu_code,
    unspsc,
    name: s.name_ru,
  })
}

// --- сборка SQL --------------------------------------------------------------

const out = []
out.push('-- ============================================================================')
out.push('-- Сид каталога (ADR-0004): catalog.product_types + catalog.country_codes')
out.push('-- из текущих public.products (ТН ВЭД-10) и public.services (ОКЭД/ИКПУ), плюс')
out.push('-- колонка-мост product_type_id на products/services.')
out.push('-- Сгенерировано scripts/generate_catalog_seed.mjs — правки вносить там.')
out.push(
  `-- Товаров: ${products.length}, HS6-типов: ${goodTypes.size}; услуг: ${services.length}, типов услуг: ${serviceTypes.length}`,
)
out.push('-- ============================================================================')

out.push('\n-- ----------------------------------------------------------------------------')
out.push('-- Мост: product_type_id на public.products / public.services')
out.push('-- ----------------------------------------------------------------------------')
out.push('alter table public.products add column product_type_id uuid references catalog.product_types(id);')
out.push('create index products_product_type_id_idx on public.products (product_type_id);')
out.push('alter table public.services add column product_type_id uuid references catalog.product_types(id);')
out.push('create index services_product_type_id_idx on public.services (product_type_id);')

out.push('\n-- ----------------------------------------------------------------------------')
out.push('-- catalog.product_types — товары (HS6)')
out.push('-- ----------------------------------------------------------------------------')
for (const t of goodTypes.values())
  out.push(
    `insert into catalog.product_types (id, kind, hs_code, name_ru) values (${q(t.id)}, 'good', ${q(t.hs6)}, ${q(t.name)}) on conflict (id) do nothing;`,
  )

out.push('\n-- ----------------------------------------------------------------------------')
out.push('-- catalog.product_types — услуги (UNSPSC)')
out.push('-- ----------------------------------------------------------------------------')
for (const t of serviceTypes) {
  const reviewNote = needsReview.some((r) => r.oked === t.oked)
    ? ' -- уточнить: ОКЭД нет в UNSPSC_BY_OKED, код-заглушка'
    : ''
  out.push(
    `insert into catalog.product_types (id, kind, unspsc_code, name_ru) values (${q(t.id)}, 'service', ${q(t.unspsc)}, ${q(t.name)}) on conflict (id) do nothing;${reviewNote}`,
  )
}

out.push('\n-- ----------------------------------------------------------------------------')
out.push('-- catalog.country_codes — UZ: tnved (товары, полный код) + oked/ikpu (услуги)')
out.push('-- ----------------------------------------------------------------------------')
for (const p of products) {
  const type = goodTypes.get(p.hs_code.slice(0, 6))
  out.push(
    `insert into catalog.country_codes (country, system, code, name, product_type_id) values ('UZ', 'tnved', ${q(p.hs_code)}, ${q(p.name_ru)}, ${q(type.id)}) on conflict (country, system, code) do nothing;`,
  )
}
for (const t of serviceTypes) {
  out.push(
    `insert into catalog.country_codes (country, system, code, name, product_type_id) values ('UZ', 'oked', ${q(t.oked)}, ${q(t.name)}, ${q(t.id)}) on conflict (country, system, code) do nothing;`,
  )
  if (t.ikpu)
    out.push(
      `insert into catalog.country_codes (country, system, code, name, product_type_id) values ('UZ', 'ikpu', ${q(t.ikpu)}, ${q(t.name)}, ${q(t.id)}) on conflict (country, system, code) do nothing;`,
    )
}

out.push('\n-- ----------------------------------------------------------------------------')
out.push('-- Обратная связка: product_type_id на products/services по совпадению кода')
out.push('-- (через только что заполненный catalog.country_codes — он и есть указатель')
out.push('-- нацкода на тип, ADR-0004)')
out.push('-- ----------------------------------------------------------------------------')
out.push(`update public.products p set product_type_id = cc.product_type_id
from catalog.country_codes cc
where cc.country = 'UZ' and cc.system = 'tnved' and cc.code = p.hs_code;`)
out.push(`update public.services s set product_type_id = cc.product_type_id
from catalog.country_codes cc
where cc.country = 'UZ' and cc.system = 'oked' and cc.code = s.oked_code;`)

const target = new URL('../supabase/migrations/20260803110000_catalog_seed.sql', import.meta.url).pathname
writeFileSync(target, out.join('\n') + '\n')

console.log(`OK -> ${target}`)
console.log(
  `products=${products.length} good_types=${goodTypes.size} services=${services.length} service_types=${serviceTypes.length}`,
)
console.log('Категорийные имена типов на группах с >1 товара (было -> стало; примеры):')
for (const s of namingSamples)
  console.log(
    `  hs6=${s.hs6} n=${s.count}${s.usedFallback ? ' [фолбэк]' : ''}: "${s.oldName}" -> "${s.newName}"`,
  )
if (needsReview.length) {
  console.log('УТОЧНИТЬ (ОКЭД без записи в UNSPSC_BY_OKED — код-заглушка):')
  for (const r of needsReview) console.log(`  oked=${r.oked} name="${r.name}" synthetic_unspsc=${r.syntheticUnspsc}`)
} else {
  console.log('УТОЧНИТЬ: нет — все услуги покрыты явным маппингом UNSPSC_BY_OKED')
}
