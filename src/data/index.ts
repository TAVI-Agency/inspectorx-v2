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
import {
  fetchCardReal,
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
import { readChangeIds } from './mock/read-store'
import { CAFE_SERVICE_ID, PHARMACY_SERVICE_ID } from './cross-links'

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

/** Макс. санкция из ОТКРЫТЫХ строк уровня 0 — то, что аноним и так видит.
 *  Закрывать метрику, когда суммы напечатаны в списке, — ложь интерфейса. */
function maxSanctionFromRows(rows: RequirementRow[]): string | null {
  let max = 0
  for (const r of rows) {
    const m = r.sanctionSummary?.match(/до\s+(\d+)\s*БРВ/i)
    if (m) max = Math.max(max, Number(m[1]))
  }
  return max > 0 ? `до ${max} БРВ` : null
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

  const openMax = maxSanctionFromRows(rows)
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

export async function fetchProductBundle(
  productId: string,
  ctx: DataCtx,
): Promise<ProductBundle | null> {
  // Полностью мок-товар
  if (productId === PARACETAMOL_PRODUCT_ID) {
    const rows = applyChangeOverlay(productId, mockRowsFor(productId))
    return {
      passport: paracetamolPassport,
      rows,
      stages: stagesFromRows(rows),
      metrics: metricsFor(productId, rows, ctx),
    }
  }

  const passport = await fetchPassportReal(productId)
  if (!passport) return null

  // Реальный товар с мок-требованиями (молоко)
  if (productId === MILK_PRODUCT_ID) {
    const rows = applyChangeOverlay(productId, mockRowsFor(productId))
    return {
      passport: { ...passport, ...milkPassportExtras, displayName: passport.displayName },
      rows,
      stages: stagesFromRows(rows),
      metrics: metricsFor(productId, rows, ctx),
    }
  }

  // Живые данные (сигареты и все остальные наполненные товары)
  const list = await fetchRequirementsReal(passport.hsCode)
  const rows = applyChangeOverlay(productId, list.rows)
  return {
    passport: { ...passport, verifiedAt: list.verifiedAt },
    rows,
    stages: stagesFromRows(rows),
    metrics: metricsFor(productId, rows, ctx),
  }
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

  const openMax = maxSanctionFromRows(rows)
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

export async function fetchLawyerReviews(
  requirementId: string,
  userId?: string,
): Promise<LawyerReview[]> {
  // Мок-требования: витринные фикстуры (или пусто), в базу не ходим
  if (isMockRequirementId(requirementId)) {
    return mockLawyerReviews[requirementId] ?? []
  }
  return fetchLawyerReviewsReal(requirementId, userId)
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
    const list = await fetchRequirementsReal('2404110001')
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
    const recent = mine.some((c) => new Date(c.date).getTime() > cutoff30)
    return {
      productId,
      displayName: info.name,
      hsCode: info.hs,
      unreadCount,
      statusKind: nearest ? 'deadline' : recent ? 'noAction' : 'quiet',
      statusLine: nearest?.effectiveDate ?? '',
    }
  })
}
