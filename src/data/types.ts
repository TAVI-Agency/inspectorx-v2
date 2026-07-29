/**
 * Доменные типы витрины. Компоненты знают только их —
 * откуда пришли данные (Supabase или мок), решает слой src/data.
 */
import type { RequirementCategory } from './taxonomy'

export type Deontic = 'obligation' | 'prohibition' | 'permission'
export type PartyRole =
  | 'producer'
  | 'importer'
  | 'exporter'
  | 'seller'
  | 'carrier'
  | 'service_provider'
  | 'all'
export type Operation =
  | 'product'
  | 'realization'
  | 'import'
  | 'export'
  | 'transit'
  | 're_export'
  | 're_import'
  | 'service'
/** Вид транспорта — только у трансграничных процедур (иначе не задан) */
export type TransportType = 'avto' | 'train' | 'avia'
export type TrustLabel = 'ai_draft' | 'lawyer_verified' | 'official_answer'
export type Importance = 'high' | 'medium' | 'low'
/** Пометка «разовое действие / постоянная обязанность» (requirements.nature) */
export type RequirementNature = 'one_time' | 'recurring'
export type SearchKind = 'product' | 'service'
/** Режим допуска услуги по ЗРУ-701 — главный бейдж паспорта услуги */
export type AdmissionMode = 'license' | 'permit' | 'notification' | 'free'

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
  codeKind: 'hs' | 'ikpu' | 'oked'
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

// ── Паспорт услуги ─────────────────────────────────────────────────
// Зеркало паспорта товара: ОКЭД вместо ТН ВЭД + режим допуска и лицензиар.

export interface ServicePassport {
  id: string
  displayName: string
  officialName?: string
  /** Код вида деятельности — главная ось поиска услуг */
  okedCode?: string
  /** Фискальный код — второй в шапке, когда известен */
  ikpuCode?: string
  admissionMode?: AdmissionMode
  /** Лицензиар / разрешительный орган */
  authorityName?: string
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
  transport?: TransportType
  authorityName?: string
  sanctionSummary?: string
  status: RequirementStatus
  unread: boolean
  stageId: string
  stageName: string
  stageSortOrder: number
  /** Персистированный род требования (UNCTAD NTM) — приоритетнее эвристики */
  category?: RequirementCategory
  /** разовое действие / постоянная обязанность */
  nature?: RequirementNature
  trustLabel: TrustLabel
  trustDate?: string
  /** review_flag = flagged_by_change → значок «проверяется обновление» */
  underReview: boolean
  /** id карточки изменения (мок-лента) — для сброса непрочитанности при раскрытии */
  changeId?: string
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

// ── Проверка юристом ───────────────────────────────────────────────

/** подтверждаю / есть неточность / устарело / дополнение */
export type ReviewVerdict = 'confirm' | 'inaccurate' | 'outdated' | 'addition'
export type ReviewStatus = 'pending' | 'published' | 'rejected'
export type LawyerStatus = 'pending' | 'verified' | 'rejected'

/** Опубликованное заключение юриста (или своё pending — с пометкой) */
export interface LawyerReview {
  id: string
  requirementId: string
  verdict: ReviewVerdict
  commentText: string
  status: ReviewStatus
  lawyerId: string
  lawyerName: string
  credentials?: string
  officialReply?: string
  officialRepliedAt?: string
  helpful: number
  notHelpful: number
  /** Голос текущего пользователя: 1 — помогло, -1 — не помогло */
  myVote: 1 | -1 | null
  isMine: boolean
  createdAt: string
}

/** Счётчики для бейджа на строке требования */
export interface RequirementReviewStats {
  confirms: number
  disputes: number
  total: number
}

export interface LawyerProfile {
  displayName: string
  credentials: string
  licenseNo?: string
  specializations?: string
  status: LawyerStatus
  verifiedAt?: string
}

export interface LawyerStats {
  requirementsReviewed: number
  reviewsPublished: number
  helpfulTotal: number
  notHelpfulTotal: number
}

export interface LeaderboardEntry {
  lawyerId: string
  displayName: string
  credentials?: string
  requirementsReviewed: number
  reviewsPublished: number
  helpfulTotal: number
  notHelpfulTotal: number
  rank: number
}

export interface LawyerLeaderboard {
  top: LeaderboardEntry[]
  /** Всего юристов в рейтинге */
  total: number
  /** Строка текущего юриста — есть и когда он вне топ-10 */
  me?: LeaderboardEntry
}

export type LawyerNotificationKind =
  | 'review_published'
  | 'review_rejected'
  | 'new_requirement'

export interface LawyerNotification {
  id: string
  kind: LawyerNotificationKind
  requirementId?: string
  requirementTitle?: string
  /** Страница товара/услуги с раскрытым требованием */
  link?: string
  isRead: boolean
  createdAt: string
}

/** Строка очереди «Ждут проверки» */
export interface ReviewQueueItem {
  requirementId: string
  title: string
  publishedAt?: string
  link?: string
  /** Имя товара/услуги, к которому привязано требование */
  targetName?: string
}

/** Строка «Мои заключения» в дешборде юриста */
export interface MyReviewItem {
  id: string
  requirementId: string
  requirementTitle: string
  link?: string
  verdict: ReviewVerdict
  status: ReviewStatus
  helpful: number
  notHelpful: number
  createdAt: string
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
