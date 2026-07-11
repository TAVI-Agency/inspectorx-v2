#!/usr/bin/env node
/**
 * Перенос контента InspectorX v1 -> v2 (одноразовый).
 *
 * Вход: JSON-дампы четырёх наборов старой базы (см. README в конце файла),
 * выход: supabase/migrations/20260711130000_v1_content.sql — идемпотентная
 * data-миграция (детерминированные uuid из md5-ключей + on conflict do nothing).
 *
 * Маппинг (решения 11.07.2026, юзер подтвердил «published сразу»):
 *  - строка *_all -> requirements(status=published, trust_label=ai_draft,
 *    origin=migration_v1) + contents(ru) + details(ru) + applicability(hs_code)
 *  - дедуп истинных дублей по (операция, транспорт, заголовок, md5 контента)
 *  - старые категории -> lifecycle_stages (дедуп по названию, правка опечаток)
 *  - source_text/source_link/legislative_excerpt -> acts / act_paragraphs / citations
 *  - деонтика: эвристика по заголовку (запрет/льгота), иначе obligation
 *  - адресат по операции: import->importer, export/re_export->exporter,
 *    re_import->importer, realization->seller, product->producer
 *
 * Запуск: node scripts/generate_v1_content_migration.mjs <папка с дампами>
 */
import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const dumpDir = process.argv[2]
if (!dumpDir) {
  console.error('usage: node generate_v1_content_migration.mjs <dump-dir>')
  process.exit(1)
}

const load = (name) => JSON.parse(readFileSync(join(dumpDir, `v1_${name}.json`), 'utf8'))
const productsIn = load('products')
const aliasesIn = load('aliases')
const categoriesIn = load('categories')
const requirementsIn = load('requirements')

const md5 = (s) => createHash('md5').update(s, 'utf8').digest('hex')
const uuid = (key) => {
  const h = md5(`inspectorx-v1:${key}`)
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20, 32)}`
}
const q = (v) => (v === null || v === undefined ? 'null' : `'${String(v).replaceAll("'", "''")}'`)
const qj = (v) => `${q(JSON.stringify(v))}::jsonb`
const hs10 = (n) => String(n).padStart(10, '0')

// --- lifecycle_stages: дедуп по названию + правка явных опечаток -------------
const TYPO_FIX = {
  'Перечесение границы': 'Пересечение границы',
  'Прохождение таможенного оформления (Врменное хранение)':
    'Прохождение таможенного оформления (Временное хранение)',
  'Подготовка к дсотавке груза ж/д транспортом онлайн':
    'Подготовка к доставке груза ж/д транспортом онлайн',
  'Организация возврат пустых вагонов': 'Организация возврата пустых вагонов',
  'Ценобразования': 'Ценообразование',
  'Правила оптового торговля': 'Правила оптовой торговли',
  'Правила розичного торвголя': 'Правила розничной торговли',
  'Доставка груз на таможенный склад': 'Доставка груза на таможенный склад',
  'Требования для выпуска в обращения': 'Требования для выпуска в обращение',
  'Санитарные, ветеренарные и фитосанитарные нормы':
    'Санитарные, ветеринарные и фитосанитарные нормы',
}
const fixTitle = (t) => {
  const s = (t ?? '').trim()
  return TYPO_FIX[s] ?? s
}

const stages = new Map() // fixedTitle -> {id, sort}
const stageByCat = new Map() // `${src}:${category_id}` -> stage id
for (const c of categoriesIn) {
  const title = fixTitle(c.title)
  if (!title) continue
  if (!stages.has(title)) stages.set(title, { id: uuid(`stage:${title}`), sort: stages.size + 1 })
  stageByCat.set(`${c.src}:${c.category_id}`, stages.get(title).id)
}

// --- products + aliases ------------------------------------------------------
const productByHs = new Map()
for (const p of productsIn) {
  const code = hs10(p.hs_code)
  const levels = []
  for (let i = 1; i <= 10; i++) if (p[`level_${i}`]) levels.push(p[`level_${i}`].trim())
  productByHs.set(code, {
    id: uuid(`product:${code}`),
    code,
    name: (p.product_name ?? 'Без названия').trim(),
    path: { category_name: (p.category_name ?? '').trim(), levels },
    complexity: p.complexity_index == null ? null : Math.min(10, Math.max(1, Math.round(p.complexity_index))),
  })
}

const aliasRows = new Map() // dedupe by (hs, alias, lang)
const skipped = []
for (const a of aliasesIn) {
  const code = hs10(a.hs_code)
  const lang = ['ru', 'uz', 'en'].includes(a.language) ? a.language : 'ru'
  const product = productByHs.get(code)
  if (!product) {
    skipped.push(`alias "${a.alias_name}" -> hs ${code}: товара нет в каталоге`)
    continue
  }
  const key = `${code}|${a.alias_name.trim().toLowerCase()}|${lang}`
  if (!aliasRows.has(key))
    aliasRows.set(key, {
      id: uuid(`alias:${key}`),
      productId: product.id,
      alias: a.alias_name.trim(),
      lang,
      isDefault: a.is_default === true,
    })
}

// --- requirements ------------------------------------------------------------
const ROLES = {
  product: '{producer}',
  import: '{importer}',
  export: '{exporter}',
  re_export: '{exporter}',
  re_import: '{importer}',
  realization: '{seller}',
}
const deonticOf = (title) =>
  /запрет|запрещ/i.test(title) ? 'prohibition' : /льгот|освобожд/i.test(title) ? 'permission' : 'obligation'

const acts = new Map() // actKey -> {id, title, url}
const paragraphs = new Map() // paraKey -> {id, actId, ref, verbatim, deepLink}
const usedRefs = new Map() // actId -> Map(ref -> paraKey)
const reqs = new Map() // dedupeKey -> row
let dupes = 0

for (const r of requirementsIn) {
  const title = (r.item_title ?? r.subcategory_title ?? '').trim()
  if (!title) {
    skipped.push(`требование ${r.src}/${r.id}: нет заголовка`)
    continue
  }
  const description =
    r.description && !/^It is draft/.test(r.description.trim()) ? r.description.trim() : null
  const excerpt = r.legislative_excerpt?.trim() || null
  const recommendation = r.recommendation?.trim() || null
  const sourceText = r.source_text?.trim() || null
  const sourceLink = r.source_link?.trim() || null
  const transport = ['avto', 'avia', 'train'].includes(r.transport_type) ? r.transport_type : null

  const contentHash = md5(
    [r.item_title, r.description, r.legislative_excerpt, r.recommendation, r.source_text, r.source_link]
      .map((x) => x ?? '')
      .join('|'),
  )
  const dedupeKey = `${r.src}|${transport ?? ''}|${title}|${contentHash}`
  if (reqs.has(dedupeKey)) {
    dupes++
    continue
  }

  // источник -> act / paragraph
  let paraId = null
  if (excerpt) {
    const actKey = sourceText ?? (sourceLink ? `link:${sourceLink}` : 'unknown')
    if (!acts.has(actKey))
      acts.set(actKey, {
        id: uuid(`act:${actKey}`),
        title: sourceText ?? (sourceLink ?? 'Источник не указан (перенос из v1)').slice(0, 200),
        url: sourceLink,
      })
    const act = acts.get(actKey)
    if (!act.url && sourceLink) act.url = sourceLink

    const paraKey = `${act.id}|${md5(excerpt)}`
    if (!paragraphs.has(paraKey)) {
      const m = excerpt.match(/^\s*\(?\s*(?:пункт|пукнт|п)\.?\s*№?\s*([0-9][0-9а-яa-z.-]*)/i)
      let ref = m ? `п. ${m[1].replace(/[.)]+$/, '')}` : `фрагмент ${md5(excerpt).slice(0, 8)}`
      const refs = usedRefs.get(act.id) ?? new Map()
      if (refs.has(ref) && refs.get(ref) !== paraKey) ref = `${ref} (${md5(excerpt).slice(0, 4)})`
      refs.set(ref, paraKey)
      usedRefs.set(act.id, refs)
      paragraphs.set(paraKey, { id: uuid(`para:${paraKey}`), actId: act.id, ref, verbatim: excerpt, deepLink: sourceLink })
    }
    paraId = paragraphs.get(paraKey).id
  }

  reqs.set(dedupeKey, {
    id: uuid(`req:${dedupeKey}`),
    externalKey: `v1:${md5(dedupeKey).slice(0, 16)}`,
    src: r.src,
    transport,
    title,
    deontic: deonticOf(title),
    roles: ROLES[r.src],
    stageId: stageByCat.get(`${r.src}:${r.category_id}`) ?? null,
    hsCode: hs10(r.hs_code),
    description,
    recommendation,
    paraId,
  })
}

// --- SQL ----------------------------------------------------------------------
const out = []
out.push(`-- ============================================================================`)
out.push(`-- Контент v1 -> v2 (сгенерировано scripts/generate_v1_content_migration.mjs)`)
out.push(`-- Источник: локальная копия старой базы (supabase_db_meyanvmkjwctcvtwqlvx)`)
out.push(`-- ${productByHs.size} товаров, ${aliasRows.size} алиасов, ${stages.size} этапов,`)
out.push(`-- ${reqs.size} требований (${dupes} истинных дублей отброшено), ${acts.size} актов, ${paragraphs.size} пунктов`)
out.push(`-- ============================================================================`)

out.push(`\n-- Этапы жизненного цикла`)
for (const [title, s] of stages)
  out.push(
    `insert into public.lifecycle_stages (id, code, name_ru, sort_order) values (${q(s.id)}, ${q(`v1-${md5(title).slice(0, 8)}`)}, ${q(title)}, ${s.sort}) on conflict (code) do nothing;`,
  )

out.push(`\n-- Каталог товаров`)
for (const p of productByHs.values())
  out.push(
    `insert into public.products (id, hs_code, name_ru, hierarchy_path, complexity_index) values (${q(p.id)}, ${q(p.code)}, ${q(p.name)}, ${qj(p.path)}, ${p.complexity ?? 'null'}) on conflict (hs_code) do nothing;`,
  )

out.push(`\n-- Алиасы поиска`)
for (const a of aliasRows.values())
  out.push(
    `insert into public.search_aliases (id, product_id, alias, lang, is_default) values (${q(a.id)}, ${q(a.productId)}, ${q(a.alias)}, ${q(a.lang)}, ${a.isDefault}) on conflict (id) do nothing;`,
  )

out.push(`\n-- Акты и пункты`)
for (const a of acts.values())
  out.push(`insert into public.acts (id, title, url) values (${q(a.id)}, ${q(a.title)}, ${q(a.url)}) on conflict (id) do nothing;`)
for (const p of paragraphs.values())
  out.push(
    `insert into public.act_paragraphs (id, act_id, paragraph_ref, verbatim_ru, deep_link_url) values (${q(p.id)}, ${q(p.actId)}, ${q(p.ref)}, ${q(p.verbatim)}, ${q(p.deepLink)}) on conflict (id) do nothing;`,
  )

out.push(`\n-- Требования`)
for (const r of reqs.values()) {
  out.push(
    `insert into public.requirements (id, status, deontic, addressee_roles, operation, transport_type, lifecycle_stage_id, trust_label, origin, external_key, published_at) values (${q(r.id)}, 'published', ${q(r.deontic)}, ${q(r.roles)}, ${q(r.src)}, ${q(r.transport)}, ${q(r.stageId)}, 'ai_draft', 'migration_v1', ${q(r.externalKey)}, now()) on conflict (external_key) do nothing;`,
  )
  out.push(
    `insert into public.requirement_contents (requirement_id, lang, title) values (${q(r.id)}, 'ru', ${q(r.title)}) on conflict do nothing;`,
  )
  if (r.description || r.recommendation)
    out.push(
      `insert into public.requirement_details (requirement_id, lang, description, how_to_comply) values (${q(r.id)}, 'ru', ${q(r.description)}, ${qj(r.recommendation ? [{ step: r.recommendation }] : [])}) on conflict do nothing;`,
    )
  out.push(
    `insert into public.requirement_applicability (requirement_id, scope, code) values (${q(r.id)}, 'hs_code', ${q(r.hsCode)}) on conflict do nothing;`,
  )
  if (r.paraId)
    out.push(
      `insert into public.requirement_citations (requirement_id, paragraph_id, is_primary) values (${q(r.id)}, ${q(r.paraId)}, true) on conflict do nothing;`,
    )
}

const target = new URL('../supabase/migrations/20260711130000_v1_content.sql', import.meta.url).pathname
writeFileSync(target, out.join('\n') + '\n')

console.log(`OK -> ${target}`)
console.log(
  `stages=${stages.size} products=${productByHs.size} aliases=${aliasRows.size} acts=${acts.size} paragraphs=${paragraphs.size} requirements=${reqs.size} dupes_dropped=${dupes}`,
)
if (skipped.length) console.log('SKIPPED:\n  ' + skipped.join('\n  '))

/*
 * Как получить дампы (docker exec в контейнер старой локальной базы):
 * см. историю сессии 11.07.2026 — четыре json_agg-запроса в файлы
 * v1_products.json, v1_aliases.json, v1_categories.json, v1_requirements.json
 */
