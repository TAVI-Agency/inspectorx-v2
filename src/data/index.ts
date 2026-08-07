/**
 * Публичный API слоя данных. Компоненты вызывают только эти функции
 * (через hooks.ts) и не знают, что пришло из Supabase, а что из моков.
 *
 * Правила композиции:
 * — Сигареты: живые данные Supabase + мок-оверлей изменений.
 * — Молоко: реальный товар, требования из фикстур (в базе их нет).
 * — Парацетамол: полностью мок.
 * — Закрытое RLS → Gated 'locked'; мок-подписчик получает демо-шаблон details.
 */
import {
  locked,
  ok,
  type ChangeCard,
  type ComparisonMatrix,
  type CountryCoverage,
  type Gated,
  type LawyerReview,
  type PortfolioItem,
  type ProductPassport,
  type RequirementCard,
  type RequirementReviewStats,
  type RequirementRow,
  type SearchHit,
  type SearchKind,
  type ServicePassport,
  type StageInfo,
  type SummaryMetrics,
  type TelemetryStats,
  type WeekSummary,
} from './types'
import { COUNTRIES, type CountryCode, type LifecycleStatus } from './countries'
import { categoryChipOf } from './taxonomy'
import { formatFine, type Fine } from '@/i18n/format'
import {
  createCalendarTokenReal,
  deleteCalendarTokenReal,
  fetchCalendarTokenReal,
  fetchCardReal,
  fetchComparisonReal,
  fetchLawyerReviewsReal,
  fetchPassportReal,
  fetchRequirementsReal,
  fetchReviewStatsReal,
  fetchServiceDocumentsCountReal,
  fetchServicePassportReal,
  fetchServiceRequirementsReal,
  fetchTelemetryReal,
  searchProductsReal,
  searchServicesReal,
  setReviewVoteReal,
  worseLifecycle,
  type CalendarTokenRow,
} from './real'
import {
  CIGARETTES_PRODUCT_ID,
  MILK_PRODUCT_ID,
  PARACETAMOL_PRODUCT_ID,
  changeFixtures,
  cigaretteChangeSlots,
  demoDetailFor,
  isMockRequirementId,
  milkPassportExtras,
  mockCardFor,
  mockLawyerReviews,
  mockMetrics,
  mockReviewStats,
  mockRowsFor,
  mockWeeklyChangesCount,
  paracetamolHit,
  paracetamolMatches,
  paracetamolPassport,
  stagesFromRows,
} from './mock/fixtures'
import { loadMockReviewVotes, readChangeIds, saveMockReviewVote } from './mock/read-store'
import { CAFE_SERVICE_ID, PHARMACY_SERVICE_ID } from './cross-links'
import { isKzRequirementId, kzCardFor, kzCodesFor, kzRowsFor, kzStagesFor } from './mock/kz-fixtures'

export interface DataCtx {
  /** Реальная подписка (profiles.is_subscribed под сессией) */
  realSubscriber: boolean
  /** Тумблер dev-меню «я подписчик» */
  mockSubscriber: boolean
  /** Верифицированный юрист: RLS даёт ему details наравне с подписчиком */
  verifiedLawyer: boolean
}

export function effectiveSubscriber(ctx: DataCtx): boolean {
  return ctx.realSubscriber || ctx.mockSubscriber || ctx.verifiedLawyer
}

/** Кому сервер (RLS) реально отдаёт закрытый контент */
function serverAccess(ctx: DataCtx): boolean {
  return ctx.realSubscriber || ctx.verifiedLawyer
}

// ── Телеметрия ─────────────────────────────────────────────────────

export async function fetchTelemetry(): Promise<TelemetryStats> {
  const real = await fetchTelemetryReal()
  return {
    actsCount: real.actsCount,
    updatedAt: real.updatedAt ?? new Date().toISOString(),
    weeklyChanges: mockWeeklyChangesCount,
  }
}

// ── Поиск ──────────────────────────────────────────────────────────

export async function search(query: string, kind: SearchKind): Promise<SearchHit[]> {
  if (kind === 'service') return searchServicesReal(query)
  const hits = await searchProductsReal(query)
  if (paracetamolMatches(query) && !hits.some((h) => h.id === PARACETAMOL_PRODUCT_ID)) {
    hits.unshift(paracetamolHit)
  }
  return hits.slice(0, 8)
}

/** Примеры в реестре: 2 товара + 2 услуги. Счётчики статичны для витрины
 *  (177 = published-строки сигарет после фильтра мусора/дублей переноса v1). */
export const exampleHits: (SearchHit & { requirementsCount: number })[] = [
  {
    id: CIGARETTES_PRODUCT_ID,
    kind: 'product',
    displayName: 'Стики IQOS',
    officialName:
      'продукция, содержащая «гомогенизированный» или «восстановленный» табак',
    code: '2404110001',
    codeKind: 'hs',
    categoryName: 'Табак и промышленные заменители табака',
    requirementsCount: 177,
  },
  {
    id: MILK_PRODUCT_ID,
    kind: 'product',
    displayName: 'Молоко',
    officialName: 'молоко в первичных упаковках нетто-объёмом не более 2 л',
    code: '0401201100',
    codeKind: 'hs',
    categoryName: 'Молочная продукция',
    requirementsCount: 7,
  },
  {
    id: PHARMACY_SERVICE_ID,
    kind: 'service',
    displayName: 'Розничная аптека',
    officialName: 'услуга с лицензией: маршрут из 6 этапов — от допуска до закрытия',
    code: '47.73',
    codeKind: 'oked',
    categoryName: 'Услуги · режим допуска: лицензия',
    requirementsCount: 36,
  },
  {
    id: CAFE_SERVICE_ID,
    kind: 'service',
    displayName: 'Кафе (общественное питание)',
    officialName: 'услуга без лицензии: санитарка, маркировка и алкогольные уведомления',
    code: '56.10',
    codeKind: 'oked',
    categoryName: 'Услуги · режим допуска: свободно',
    requirementsCount: 35,
  },
]

// ── Страница товара ────────────────────────────────────────────────

export interface ProductBundle {
  passport: ProductPassport
  rows: RequirementRow[]
  stages: StageInfo[]
  metrics: SummaryMetrics
}

function applyChangeOverlay(productId: string, rows: RequirementRow[]): RequirementRow[] {
  const read = readChangeIds()

  if (productId === CIGARETTES_PRODUCT_ID) {
    for (const slot of cigaretteChangeSlots) {
      const idx = rows.findIndex((r) =>
        slot.titleIncludes.some((t) => r.title.toLowerCase().includes(t)),
      )
      const row = rows[idx >= 0 ? idx : slot.fallbackIndex]
      if (row) {
        row.status = slot.status
        row.unread = !read.has(slot.changeId)
        row.changeId = slot.changeId
      }
    }
    return rows
  }

  // Мок-товары: непрочитанность из фикстур ленты
  for (const fx of changeFixtures) {
    if (fx.productId !== productId || fx.isDraftNpa || !fx.requirementId) continue
    const row = rows.find((r) => r.id === fx.requirementId)
    if (row) {
      row.unread = !read.has(fx.id)
      row.changeId = fx.id
    }
  }
  return rows
}

function changes30dFor(productId: string): number {
  const cutoff = Date.now() - 30 * 86_400_000
  return changeFixtures.filter(
    (c) => c.productId === productId && !c.isDraftNpa && new Date(c.date).getTime() > cutoff,
  ).length
}

/**
 * Единицы санкций, которые конвейер уже писал в открытый текст (регистр
 * источника не важен — «до 200 брв» встречается наравне с «БРВ»). Список не
 * заменяет общий разбор ниже, а расширяет его: новую/незнакомую единицу
 * будущей страны код всё равно подхватит по общему правилу «слово заглавными
 * буквами сразу после числа» — сюда добавляются только единицы, которые
 * встречались НЕ заглавными в реальном контенте (иначе делать регистр
 * нечувствительным для них не нужно).
 */
const KNOWN_FINE_UNITS = new Set(['БРВ', 'МРП', 'AED'])

/**
 * Разбор «сумма + единица» из открытого текста уровня 0 (sanction_summary):
 * не завязан на конкретную единицу измерения — конвейер пишет её как есть,
 * своя для каждой юрисдикции, код её не выбирает и не хардкодит
 * (TARGET_FORMAT §4, доп. 02.08.2026 «Санкции — структура»). Единица —
 * слово из 3–6 букв сразу после числа (`\p{L}`, не `\b`: латиница и
 * кириллица вперемешку, а `\b` в JS не видит границы слова у кириллицы),
 * которое либо входит в KNOWN_FINE_UNITS (регистр не важен), либо целиком
 * заглавное в исходном тексте — так отсекаются обычные слова рядом с числом
 * («до 5 лет», «в течение 30 дней»: пишутся строчными и не входят в список)
 * и смешанный регистр отсылок к кодексу («ст. 128 КоАО»), но не отсекаются
 * будущие незнакомые единицы других юрисдикций, если конвейер напишет их
 * заглавными — тем же способом, каким уже пишет БРВ/МРП.
 */
function extractMaxFine(text: string | undefined): Fine | null {
  if (!text) return null
  let best: Fine | null = null
  for (const m of text.matchAll(/(\d+)\s*(\p{L}{3,6})(?!\p{L})/gu)) {
    const amount = Number(m[1])
    if (amount <= 0) continue
    const raw = m[2]
    const unit = raw.toUpperCase()
    const looksLikeUnit = KNOWN_FINE_UNITS.has(unit) || raw === unit
    if (looksLikeUnit && (!best || amount > best.amount)) best = { amount, unit }
  }
  return best
}

/** Макс. санкция из ОТКРЫТЫХ строк уровня 0 — то, что аноним и так видит.
 *  Закрывать метрику, когда суммы напечатаны в списке, — ложь интерфейса. */
function maxSanctionFromRows(rows: RequirementRow[], country: CountryCode): string | null {
  let max: Fine | null = null
  for (const r of rows) {
    const fine = extractMaxFine(r.sanctionSummary)
    if (fine && (!max || fine.amount > max.amount)) max = fine
  }
  return max ? formatFine(max, country) : null
}

function metricsFor(
  productId: string,
  rows: RequirementRow[],
  ctx: DataCtx,
): SummaryMetrics {
  const subscriber = effectiveSubscriber(ctx)
  const mock = mockMetrics[productId]
  let documents: Gated<number> = locked
  if (subscriber && mock) documents = ok(mock.documents)

  // metricsFor зовётся только для УЗ-ветки бандла (previewMetrics — для KZ/AE)
  const openMax = maxSanctionFromRows(rows, 'UZ')
  let maxSanction: Gated<string> = openMax
    ? ok(openMax)
    : subscriber && mock
      ? ok(mock.maxSanction)
      : locked

  return {
    requirements: rows.length,
    documents,
    maxSanction,
    changes30d: changes30dFor(productId),
  }
}

/** Метрики для превью-стран (KZ/AE) — без подписочного оверлея, санкции только из открытых строк. */
function previewMetrics(rows: RequirementRow[], country: CountryCode): SummaryMetrics {
  const openMax = maxSanctionFromRows(rows, country)
  return {
    requirements: rows.length,
    documents: locked,
    maxSanction: openMax ? ok(openMax) : locked,
    changes30d: 0,
  }
}

function emptyMetrics(): SummaryMetrics {
  return { requirements: 0, documents: locked, maxSanction: locked, changes30d: 0 }
}

/** Состояние страны фиксировано (стадия раскатки), published — per-товар. */
const COUNTRY_STATE: Record<CountryCode, CountryCoverage['state']> = {
  UZ: 'live',
  KZ: 'preview',
  AE: 'none',
}

function countriesCoverage(productId: string, uzPublished: number): CountryCoverage[] {
  return COUNTRIES.map((country) => ({
    country,
    published:
      country === 'UZ' ? uzPublished : country === 'KZ' ? kzRowsFor(productId).length : 0,
    state: COUNTRY_STATE[country],
  }))
}

export async function fetchProductBundle(
  productId: string,
  ctx: DataCtx,
  country: CountryCode = 'UZ',
): Promise<ProductBundle | null> {
  // Полностью мок-товар (UZ-only; для KZ/AE у него ещё нет требований)
  if (productId === PARACETAMOL_PRODUCT_ID) {
    const uzRows = mockRowsFor(productId)
    const countries = countriesCoverage(productId, uzRows.length)
    if (country === 'UZ') {
      const rows = applyChangeOverlay(productId, uzRows)
      return {
        passport: { ...paracetamolPassport, countries },
        rows,
        stages: stagesFromRows(rows),
        metrics: metricsFor(productId, rows, ctx),
      }
    }
    const rows = country === 'KZ' ? kzRowsFor(productId) : []
    return {
      passport: { ...paracetamolPassport, countries, codes: kzCodesFor(productId) },
      rows,
      stages: kzStagesFor(productId),
      metrics: previewMetrics(rows, country),
    }
  }

  const passport = await fetchPassportReal(productId, country)
  if (!passport) return null

  // Реальный товар с мок-требованиями (молоко) — тоже UZ-only демо
  if (productId === MILK_PRODUCT_ID) {
    const uzRows = mockRowsFor(productId)
    const countries = countriesCoverage(productId, uzRows.length)
    // ИКПУ молока — мок-поле (в схеме БД его нет, см. milkPassportExtras),
    // остальные коды (ТН ВЭД) уже пришли из catalog.country_codes реальным
    // паспортом; KZ/AE-ветка ниже полностью заменяет codes на kzCodesFor —
    // ИКПУ (фискальный код УЗ) там ни при чём, перезапишется корректно.
    const milkPassport = {
      ...passport,
      ...milkPassportExtras,
      displayName: passport.displayName,
      codes: [...passport.codes, { system: 'ikpu', code: milkPassportExtras.ikpuCode }],
    }
    if (country === 'UZ') {
      const rows = applyChangeOverlay(productId, uzRows)
      return {
        passport: { ...milkPassport, countries },
        rows,
        stages: stagesFromRows(rows),
        metrics: metricsFor(productId, rows, ctx),
      }
    }
    const rows = country === 'KZ' ? kzRowsFor(productId) : []
    return {
      passport: { ...milkPassport, countries, codes: kzCodesFor(productId) },
      rows,
      stages: kzStagesFor(productId),
      metrics: previewMetrics(rows, country),
    }
  }

  // Живые данные (сигареты и все остальные наполненные товары)
  const uzList = await fetchRequirementsReal(passport.hsCode, 'UZ')
  const countries = countriesCoverage(productId, uzList.rows.length)

  if (country === 'KZ') {
    const rows = kzRowsFor(productId)
    return {
      passport: { ...passport, countries, codes: kzCodesFor(productId) },
      rows,
      stages: kzStagesFor(productId),
      metrics: previewMetrics(rows, country),
    }
  }
  if (country === 'AE') {
    return {
      passport: { ...passport, countries, codes: [] },
      rows: [],
      stages: [],
      metrics: emptyMetrics(),
    }
  }

  const rows = applyChangeOverlay(productId, uzList.rows)
  return {
    passport: { ...passport, verifiedAt: uzList.verifiedAt, countries },
    rows,
    stages: stagesFromRows(rows),
    metrics: metricsFor(productId, rows, ctx),
  }
}

// ── Матрица сравнения стран (Задача 32, Блок 4) ────────────────────

/** Категория + lifecycle из произвольного набора строк (мок или KZ-превью) — тем же правилом «худшести», что и real.ts. */
function aggregateRowsByCategory(
  rows: RequirementRow[],
): Record<string, { count: number; worstLifecycle: LifecycleStatus }> {
  const out: Record<string, { count: number; worstLifecycle: LifecycleStatus }> = {}
  for (const row of rows) {
    const slug = categoryChipOf(row)
    if (!slug) continue
    const existing = out[slug]
    if (existing) {
      existing.count += 1
      existing.worstLifecycle = worseLifecycle(existing.worstLifecycle, row.lifecycle)
    } else {
      out[slug] = { count: 1, worstLifecycle: row.lifecycle }
    }
  }
  return out
}

/**
 * Матрица сравнения стран — бесплатный тизер: только category_slug +
 * lifecycle, без деталей/цитат за пейволлом (решение грила №4). УЗ — из БД
 * (fetchComparisonReal) для живых товаров; для мок-товаров (молоко/парацетамол,
 * для них в базе требований ещё нет) — из их фикстурных rows. КЗ — превью-
 * фикстуры kz-fixtures (сейчас есть только по сигаретам/стикам). ОАЭ —
 * раскатки ещё нет, все ячейки 'absent'.
 */
export async function fetchComparisonMatrix(productId: string): Promise<ComparisonMatrix> {
  const { categories, uz: dbUz } = await fetchComparisonReal(productId)
  const isFixtureOnly = productId === MILK_PRODUCT_ID || productId === PARACETAMOL_PRODUCT_ID
  const uz = isFixtureOnly ? aggregateRowsByCategory(mockRowsFor(productId)) : dbUz
  const kz = aggregateRowsByCategory(kzRowsFor(productId))

  const cells: ComparisonMatrix['cells'] = {}
  for (const cat of categories) {
    const uzAgg = uz[cat.slug]
    const kzAgg = kz[cat.slug]
    cells[cat.slug] = {
      UZ: uzAgg ? { state: 'present', worstLifecycle: uzAgg.worstLifecycle } : { state: 'absent' },
      KZ: kzAgg ? { state: 'preview', worstLifecycle: kzAgg.worstLifecycle } : { state: 'absent' },
      AE: { state: 'absent' },
    }
  }

  return { categories, countries: [...COUNTRIES], cells }
}

// ── Страница услуги ────────────────────────────────────────────────
// Зеркало товарного бандла: паспорт + строки по 6 этапам жизни бизнеса.

export interface ServiceBundle {
  passport: ServicePassport
  rows: RequirementRow[]
  stages: StageInfo[]
  metrics: SummaryMetrics
}

export async function fetchServiceBundle(
  serviceId: string,
): Promise<ServiceBundle | null> {
  const passport = await fetchServicePassportReal(serviceId)
  if (!passport) return null

  const list = await fetchServiceRequirementsReal(passport.okedCode ?? null)
  const rows = list.rows

  // Документы: считаем из details — RLS отдаёт их только подписчику
  const docsCount = await fetchServiceDocumentsCountReal(rows.map((r) => r.id))
  const documents: Gated<number> = docsCount === null ? locked : ok(docsCount)

  // Услуги пока UZ-only (ADR-0004: многострановый пока только товарный каталог)
  const openMax = maxSanctionFromRows(rows, 'UZ')
  return {
    passport: { ...passport, verifiedAt: list.verifiedAt },
    rows,
    stages: list.stages,
    metrics: {
      requirements: rows.length,
      documents,
      maxSanction: openMax ? ok(openMax) : locked,
      changes30d: 0, // конвейер изменений для услуг ещё не наполнялся
    },
  }
}

// ── Карточка требования ────────────────────────────────────────────

export async function fetchCard(
  requirementId: string,
  ctx: DataCtx,
  row?: RequirementRow,
): Promise<RequirementCard> {
  const subscriber = effectiveSubscriber(ctx)

  if (isKzRequirementId(requirementId)) {
    const card = kzCardFor(requirementId)
    if (!card) throw new Error(`Unknown KZ mock requirement: ${requirementId}`)
    if (subscriber) return card
    // Превью-страна тоже за пейволлом — тизер честный, детали закрыты
    return { ...card, detail: locked, citations: locked, faqs: locked, history: locked }
  }

  if (isMockRequirementId(requirementId)) {
    const card = mockCardFor(requirementId)
    if (!card) throw new Error(`Unknown mock requirement: ${requirementId}`)
    if (subscriber) return card
    // Аноним видит пейволл и на мок-товарах — единообразно с реальными
    return { ...card, detail: locked, citations: locked, faqs: locked, history: locked }
  }

  const card = await fetchCardReal(requirementId, serverAccess(ctx))
  // Мок-подписчик без реального доступа: сервер не отдал — показываем демо-шаблон
  if (!serverAccess(ctx) && ctx.mockSubscriber && card.detail.state === 'locked' && row) {
    const demo = demoDetailFor(row)
    return { ...demo, authority: card.authority ?? demo.authority }
  }
  return card
}

// ── Заключения юристов ─────────────────────────────────────────────

export function isMockReviewId(reviewId: string): boolean {
  return reviewId.startsWith('mock-')
}

export async function fetchLawyerReviews(
  requirementId: string,
  userId?: string,
): Promise<LawyerReview[]> {
  // Мок-требования: витринные фикстуры (или пусто), в базу не ходим.
  // Голос залогиненного пользователя — локальный оверлей, чтобы демо жило.
  if (isMockRequirementId(requirementId)) {
    const votes = userId ? loadMockReviewVotes() : {}
    return (mockLawyerReviews[requirementId] ?? []).map((r) => {
      const myVote = votes[r.id] ?? null
      return {
        ...r,
        myVote,
        helpful: r.helpful + (myVote === 1 ? 1 : 0),
        notHelpful: r.notHelpful + (myVote === -1 ? 1 : 0),
      }
    })
  }
  return fetchLawyerReviewsReal(requirementId, userId)
}

/** Голос: демо-заключения пишем в localStorage, реальные — в review_votes */
export async function setReviewVote(
  reviewId: string,
  vote: 1 | -1 | null,
  userId: string,
  hadVote: boolean,
): Promise<void> {
  if (isMockReviewId(reviewId)) {
    saveMockReviewVote(reviewId, vote)
    return
  }
  return setReviewVoteReal(reviewId, vote, userId, hadVote)
}

/** Счётчики бейджей: реальные строки из view + мок-оверлей для демо-строк */
export async function fetchReviewStats(
  requirementIds: string[],
): Promise<Record<string, RequirementReviewStats>> {
  const realIds = requirementIds.filter((id) => !isMockRequirementId(id))
  const real = realIds.length > 0 ? await fetchReviewStatsReal(realIds) : {}
  const out: Record<string, RequirementReviewStats> = { ...real }
  for (const id of requirementIds) {
    if (isMockRequirementId(id) && mockReviewStats[id]) out[id] = mockReviewStats[id]
  }
  return out
}

// ── Кабинет: портфель и лента ──────────────────────────────────────

export interface FeedBundle {
  items: ChangeCard[]
  week: WeekSummary
}

async function resolveCigaretteSlotIds(): Promise<Map<string, string>> {
  // requirementId для изменений по сигаретам — из живых строк
  const map = new Map<string, string>()
  try {
    const list = await fetchRequirementsReal('2404110001', 'UZ')
    for (const slot of cigaretteChangeSlots) {
      const row =
        list.rows.find((r) =>
          slot.titleIncludes.some((t) => r.title.toLowerCase().includes(t)),
        ) ?? list.rows[slot.fallbackIndex]
      if (row) map.set(slot.changeId, row.id)
    }
  } catch {
    // сеть упала — лента останется без ссылок «К требованию» по сигаретам
  }
  return map
}

export async function fetchChangeFeed(productIds: string[]): Promise<FeedBundle> {
  const read = readChangeIds()
  const needCigarettes = productIds.includes(CIGARETTES_PRODUCT_ID)
  const slotIds = needCigarettes ? await resolveCigaretteSlotIds() : new Map<string, string>()

  const items: ChangeCard[] = changeFixtures
    .filter((fx) => productIds.includes(fx.productId))
    .map((fx) => ({
      ...fx,
      requirementId: fx.cigaretteSlot ? slotIds.get(fx.cigaretteSlot) : fx.requirementId,
      unread: !fx.isDraftNpa && !read.has(fx.id),
    }))
    .sort((a, b) => {
      if (Boolean(a.isDraftNpa) !== Boolean(b.isDraftNpa)) return a.isDraftNpa ? 1 : -1
      return new Date(b.date).getTime() - new Date(a.date).getTime()
    })

  const weekCutoff = Date.now() - 7 * 86_400_000
  const weekItems = items.filter(
    (i) => !i.isDraftNpa && new Date(i.date).getTime() > weekCutoff,
  )
  const withDeadline = weekItems
    .filter((i) => i.action && i.effectiveDate)
    .sort(
      (a, b) => new Date(a.effectiveDate!).getTime() - new Date(b.effectiveDate!).getTime(),
    )
  return {
    items,
    week: {
      changes: weekItems.length,
      actionsRequired: withDeadline.length,
      nearestDeadline: withDeadline[0]?.effectiveDate,
    },
  }
}

const PRODUCT_NAMES: Record<string, { name: string; hs: string }> = {
  [CIGARETTES_PRODUCT_ID]: { name: 'Стики IQOS', hs: '2404110001' },
  [MILK_PRODUCT_ID]: { name: 'Молоко', hs: '0401201100' },
  [PARACETAMOL_PRODUCT_ID]: { name: 'Парацетамол', hs: '3004900002' },
}

/** Демо-портфель для кабинета без chosen_products (мок-подписчик без входа) */
export const demoPortfolioIds = [
  CIGARETTES_PRODUCT_ID,
  MILK_PRODUCT_ID,
  PARACETAMOL_PRODUCT_ID,
]

export function buildPortfolio(productIds: string[], feed: ChangeCard[]): PortfolioItem[] {
  return productIds.map((productId) => {
    const info = PRODUCT_NAMES[productId] ?? { name: 'Товар', hs: '' }
    const mine = feed.filter((c) => c.productId === productId && !c.isDraftNpa)
    const unreadCount = mine.filter((c) => c.unread).length
    const nearest = mine
      .filter((c) => c.effectiveDate && new Date(c.effectiveDate).getTime() > Date.now())
      .sort(
        (a, b) => new Date(a.effectiveDate!).getTime() - new Date(b.effectiveDate!).getTime(),
      )[0]
    const cutoff30 = Date.now() - 30 * 86_400_000
    const recentList = mine.filter((c) => new Date(c.date).getTime() > cutoff30)
    const recent = recentList.length > 0
    return {
      productId,
      displayName: info.name,
      hsCode: info.hs,
      unreadCount,
      recentCount: recentList.length,
      allInFavor: recentList.length > 0 && recentList.every((c) => c.inFavor),
      statusKind: nearest ? 'deadline' : recent ? 'noAction' : 'quiet',
      statusLine: nearest?.effectiveDate ?? '',
    }
  })
}

// ── Календарь дедлайнов (Блок 5) ────────────────────────────────────
// Чистый проброс к real.ts: данные всегда настоящие (своя строка юзера),
// мок-оверлея нет — демо-состояние без сессии рисует сам компонент
// (см. CSettingsPage), в слой данных не заходя.

export type { CalendarTokenRow }

export async function fetchCalendarToken(): Promise<CalendarTokenRow | null> {
  return fetchCalendarTokenReal()
}

export async function createCalendarToken(userId: string): Promise<CalendarTokenRow> {
  return createCalendarTokenReal(userId)
}

export async function deleteCalendarToken(userId: string): Promise<void> {
  return deleteCalendarTokenReal(userId)
}

// ── Фотоконтроль упаковки (Волна 1, Задача 11) ──────────────────────
// Полностью реальные данные — мок-оверлея нет, единственный источник —
// src/data/vision.ts (RLS own-read + api/vision/* из Задачи 10).
export type {
  ChecklistCounters,
  ChecklistGroup,
  ChecklistItem,
  InspectionBundle,
  PackagingChecklist,
  PackagingLevel,
  PhotoAssetRow,
  PhotoFactRow,
  PhotoFindingQueueItem,
  PhotoFindingReviewItem,
  PhotoFindingRow,
  PhotoInspectionEventRow,
  PhotoInspectionRow,
  PhotoNotCheckableRow,
  PhotoProductDimensionsRow,
} from './vision'
export {
  buildIdempotencyKey,
  fetchEvidenceCropUrls,
  fetchFindingReviews,
  fetchInspectionBundle,
  fetchInspectionEvents,
  fetchLawyerName,
  fetchPackagingChecklist,
  fetchPhotoFacts,
  fetchPhotoReviewQueue,
  fetchProductDimensions,
  groupRetakeBySurface,
  isPreliminary,
  needsHumanFinding,
  reportCounters,
  requestRetake,
  signInspection,
  startInspection,
  submitFactOverride,
  submitFindingAction,
  submitPhotoFindingReview,
  uploadAndRequestInspection,
  upsertProductDimensions,
} from './vision'
