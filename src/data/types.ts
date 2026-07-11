/**
 * Доменные типы витрины. Компоненты знают только их —
 * откуда пришли данные (Supabase или мок), решает слой src/data.
 */

export type Deontic = 'obligation' | 'prohibition' | 'permission'
export type PartyRole =
  | 'producer'
  | 'importer'
  | 'exporter'
  | 'seller'
  | 'carrier'
  | 'all'
export type Operation =
  | 'product'
  | 'realization'
  | 'import'
  | 'export'
  | 'transit'
  | 're_export'
  | 're_import'
export type TrustLabel = 'ai_draft' | 'lawyer_verified' | 'official_answer'
export type Importance = 'high' | 'medium' | 'low'
export type SearchKind = 'product' | 'service'

/** Поле за пейволлом: сервер (RLS) не отдал → locked, рисуем блюр + CTA. */
export type Gated<T> = { state: 'ok'; value: T } | { state: 'locked' }

export const locked = { state: 'locked' } as const
export function ok<T>(value: T): Gated<T> {
  return { state: 'ok', value }
}

// ── Поиск ──────────────────────────────────────────────────────────

export interface SearchHit {
  id: string
  kind: SearchKind
  /** Человекочитаемое имя (default-алиас) */
  displayName: string
  /** Полное официальное название кода — для самопроверки кода пользователем */
  officialName: string
  code: string
  codeKind: 'hs' | 'ikpu'
  categoryName?: string
}

// ── Паспорт товара ─────────────────────────────────────────────────

export interface ProductPassport {
  id: string
  displayName: string
  officialName: string
  hsCode: string
  /** В схеме БД колонки нет — только у мок-товаров (см. docs/QUESTIONS.md №1) */
  ikpuCode?: string
  categoryName?: string
  hierarchyLevels: string[]
  complexity?: number
  verifiedAt?: string
}

export interface SummaryMetrics {
  requirements: number
  documents: Gated<number>
  maxSanction: Gated<string>
  changes30d: number
}

// ── Требование: уровень 0 (строка) ─────────────────────────────────

export type RequirementStatus =
  | { kind: 'active' }
  | { kind: 'changed'; date: string }
  | { kind: 'upcoming'; date: string }

export interface StageInfo {
  id: string
  name: string
  sortOrder: number
  count: number
  unreadCount: number
}

export interface RequirementRow {
  id: string
  title: string
  deontic: Deontic
  roles: PartyRole[]
  operation: Operation
  authorityName?: string
  sanctionSummary?: string
  status: RequirementStatus
  unread: boolean
  stageId: string
  stageName: string
  stageSortOrder: number
  trustLabel: TrustLabel
  trustDate?: string
  /** review_flag = flagged_by_change → значок «проверяется обновление» */
  underReview: boolean
}

// ── Требование: уровень 1 (карточка) ───────────────────────────────

export interface HowToStep {
  text: string
  term?: string
  cost?: string
}

export interface RequiredDocument {
  name: string
  where?: string
}

export interface SanctionItem {
  text: string
  article?: string
  extra?: string
}

export interface FaqItem {
  question: string
  answer: string
  trustLabel: TrustLabel
}

export interface RequirementDetail {
  description?: string
  steps: HowToStep[]
  documents: RequiredDocument[]
  sanctions: SanctionItem[]
}

export interface AuthorityInfo {
  name: string
  phone?: string
  website?: string
}

// ── Требование: уровень 2 (юридический слой) ───────────────────────

export interface Citation {
  actTitle: string
  actNumber?: string
  paragraphRef: string
  versionDate?: string
  verbatimRu?: string
  verbatimUz?: string
  deepLink?: string
  isPrimary: boolean
}

export interface HistoryEntry {
  date: string
  title: string
  was?: string
  now?: string
}

export interface RequirementCard {
  requirementId: string
  authority?: AuthorityInfo
  detail: Gated<RequirementDetail>
  citations: Gated<Citation[]>
  faqs: Gated<FaqItem[]>
  history: Gated<HistoryEntry[]>
}

// ── Кабинет: портфель и лента изменений ────────────────────────────

export interface PortfolioItem {
  productId: string
  displayName: string
  hsCode: string
  unreadCount: number
  /** «дедлайн 01.09» / «действий не требуется» / «без изменений 30 дней» */
  statusLine: string
  statusKind: 'deadline' | 'noAction' | 'quiet'
}

export interface ChangeCard {
  id: string
  importance: Importance
  productId: string
  productName: string
  stageName?: string
  date: string
  title: string
  was?: string
  now?: string
  effectiveDate?: string
  action?: string
  inFavor?: boolean
  requirementId?: string
  /** Проект НПА — приглушённая карточка, ещё не право */
  isDraftNpa?: boolean
  discussionUrl?: string
  unread: boolean
}

export interface WeekSummary {
  changes: number
  actionsRequired: number
  nearestDeadline?: string
}

// ── Телеметрия шапки ───────────────────────────────────────────────

export interface TelemetryStats {
  actsCount: number
  updatedAt: string
  weeklyChanges: number
}
