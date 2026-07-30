/**
 * Реальный источник: Supabase (anon key, RLS решает, что отдать).
 * Пейволл серверный: закрытые таблицы возвращают 0 строк анониму —
 * здесь это превращается в Gated { state: 'locked' }.
 */
import { supabase } from '@/lib/supabase'
import type { Json } from '@/lib/database.types'
import { ru } from '@/i18n/ru'
import { PHARMACY_SERVICE_ID } from './cross-links'
import { CIGARETTES_PRODUCT_ID } from './mock/fixtures'
import {
  locked,
  ok,
  type AuthorityInfo,
  type Citation,
  type FaqItem,
  type Gated,
  type HistoryEntry,
  type HowToStep,
  type LawyerLeaderboard,
  type LawyerNotification,
  type LawyerProfile,
  type LawyerReview,
  type LawyerStats,
  type LeaderboardEntry,
  type MyReviewItem,
  type RequiredDocument,
  type RequirementCard,
  type RequirementDetail,
  type RequirementReviewStats,
  type RequirementRow,
  type ReviewQueueItem,
  type ReviewVerdict,
  type SanctionItem,
  type SearchHit,
  type ProductPassport,
  type ServicePassport,
  type StageInfo,
  type UserQuestion,
} from './types'

// ── Разбор сырых полей ─────────────────────────────────────────────

/** В БД есть ещё 'validated' (гейт импорт-конвейера) — для витрины это
 *  не юрвычитка, показываем как AI-черновик. */
type DbTrustLabel = RequirementRow['trustLabel'] | 'validated'

function normalizeTrust(label: DbTrustLabel): RequirementRow['trustLabel'] {
  return label === 'validated' ? 'ai_draft' : label
}

interface HierarchyPath {
  levels?: string[]
  category_name?: string
}

function parseHierarchy(json: Json): HierarchyPath {
  if (json && typeof json === 'object' && !Array.isArray(json)) {
    const o = json as Record<string, Json | undefined>
    return {
      levels: Array.isArray(o.levels)
        ? o.levels.filter((l): l is string => typeof l === 'string')
        : undefined,
      category_name:
        typeof o.category_name === 'string' ? o.category_name : undefined,
    }
  }
  return {}
}

/** «0401 20 110 0 | в первичных упаковках…» → официальное название после «|» */
function officialFromRaw(nameRu: string): string {
  const idx = nameRu.indexOf('|')
  return idx >= 0 ? nameRu.slice(idx + 1).trim() : nameRu.trim()
}

function categoryShort(h: HierarchyPath): string | undefined {
  if (!h.category_name) return undefined
  return officialFromRaw(h.category_name)
}

function parseSteps(json: Json): HowToStep[] {
  if (!Array.isArray(json)) return []
  return json.flatMap((item): HowToStep[] => {
    if (typeof item === 'string') return item.trim() ? [{ text: item }] : []
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const o = item as Record<string, Json | undefined>
      const text = typeof o.step === 'string' ? o.step : typeof o.text === 'string' ? o.text : ''
      if (!text.trim()) return []
      return [
        {
          text,
          term: typeof o.term === 'string' ? o.term : undefined,
          cost: typeof o.cost === 'string' ? o.cost : undefined,
        },
      ]
    }
    return []
  })
}

function parseDocuments(json: Json): RequiredDocument[] {
  if (!Array.isArray(json)) return []
  return json.flatMap((item): RequiredDocument[] => {
    if (typeof item === 'string') return item.trim() ? [{ name: item }] : []
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const o = item as Record<string, Json | undefined>
      const name = typeof o.name === 'string' ? o.name : typeof o.doc === 'string' ? o.doc : ''
      if (!name.trim()) return []
      return [{ name, where: typeof o.where === 'string' ? o.where : undefined }]
    }
    return []
  })
}

function parseSanctions(json: Json): SanctionItem[] {
  if (!Array.isArray(json)) return []
  return json.flatMap((item): SanctionItem[] => {
    if (typeof item === 'string') return item.trim() ? [{ text: item }] : []
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const o = item as Record<string, Json | undefined>
      const text = typeof o.text === 'string' ? o.text : typeof o.amount === 'string' ? o.amount : ''
      if (!text.trim()) return []
      return [
        {
          text,
          article: typeof o.article === 'string' ? o.article : undefined,
          extra: typeof o.extra === 'string' ? o.extra : undefined,
        },
      ]
    }
    return []
  })
}

function parseContacts(json: Json): { phone?: string } {
  if (json && typeof json === 'object' && !Array.isArray(json)) {
    const o = json as Record<string, Json | undefined>
    return { phone: typeof o.phone === 'string' ? o.phone : undefined }
  }
  return {}
}

// ── Телеметрия ─────────────────────────────────────────────────────

export async function fetchTelemetryReal(): Promise<{
  actsCount: number
  updatedAt: string | null
}> {
  const [acts, latest] = await Promise.all([
    supabase.from('acts').select('id', { count: 'exact', head: true }),
    supabase
      .from('requirements')
      .select('published_at')
      .eq('status', 'published')
      .not('published_at', 'is', null)
      .order('published_at', { ascending: false })
      .limit(1),
  ])
  return {
    actsCount: acts.count ?? 0,
    updatedAt: latest.data?.[0]?.published_at ?? null,
  }
}

// ── Поиск ──────────────────────────────────────────────────────────

interface RawProduct {
  id: string
  name_ru: string
  hs_code: string
  hierarchy_path: Json
}

async function defaultAliases(productIds: string[]): Promise<Map<string, string>> {
  if (productIds.length === 0) return new Map()
  const { data } = await supabase
    .from('search_aliases')
    .select('product_id, alias, is_default')
    .in('product_id', productIds)
    .eq('is_default', true)
  const map = new Map<string, string>()
  for (const row of data ?? []) {
    if (row.product_id) map.set(row.product_id, row.alias)
  }
  return map
}

function toHit(p: RawProduct, alias?: string): SearchHit {
  const h = parseHierarchy(p.hierarchy_path)
  const official = officialFromRaw(p.name_ru)
  return {
    id: p.id,
    kind: 'product',
    displayName: alias ?? official,
    officialName: official,
    code: p.hs_code,
    codeKind: 'hs',
    categoryName: categoryShort(h),
  }
}

export async function searchProductsReal(query: string): Promise<SearchHit[]> {
  const q = query.trim()
  if (q.length < 2) return []
  const pattern = `%${q.replaceAll('%', '').replaceAll(',', '')}%`
  const digits = q.replace(/\D/g, '')

  const [aliasRes, nameRes, codeRes] = await Promise.all([
    supabase
      .from('search_aliases')
      .select('product_id, products(id, name_ru, hs_code, hierarchy_path)')
      .ilike('alias', pattern)
      .not('product_id', 'is', null)
      .limit(8),
    supabase
      .from('products')
      .select('id, name_ru, hs_code, hierarchy_path')
      .eq('is_active', true)
      .ilike('name_ru', pattern)
      .limit(8),
    digits.length >= 2
      ? supabase
          .from('products')
          .select('id, name_ru, hs_code, hierarchy_path')
          .eq('is_active', true)
          .like('hs_code', `${digits}%`)
          .limit(8)
      : Promise.resolve({ data: [] as RawProduct[] }),
  ])

  const byId = new Map<string, RawProduct>()
  for (const row of aliasRes.data ?? []) {
    const p = row.products
    if (p) byId.set(p.id, p)
  }
  for (const p of [...(nameRes.data ?? []), ...(codeRes.data ?? [])]) {
    if (!byId.has(p.id)) byId.set(p.id, p)
  }

  const ids = [...byId.keys()]
  const aliases = await defaultAliases(ids)
  return ids.slice(0, 8).map((id) => toHit(byId.get(id)!, aliases.get(id)))
}

// ── Паспорт товара ─────────────────────────────────────────────────

export async function fetchPassportReal(
  productId: string,
): Promise<ProductPassport | null> {
  const { data: p } = await supabase
    .from('products')
    .select('id, name_ru, hs_code, complexity_index, hierarchy_path')
    .eq('id', productId)
    .maybeSingle()
  if (!p) return null
  const aliases = await defaultAliases([p.id])
  const h = parseHierarchy(p.hierarchy_path)
  const official = officialFromRaw(p.name_ru)
  return {
    id: p.id,
    displayName: aliases.get(p.id) ?? official,
    officialName: official,
    hsCode: p.hs_code,
    categoryName: categoryShort(h),
    hierarchyLevels: h.levels ?? [],
    complexity: p.complexity_index ?? undefined,
  }
}

// ── Поиск и паспорт услуги ─────────────────────────────────────────

interface RawService {
  id: string
  name_ru: string
  oked_code: string | null
  ikpu_code: string | null
}

function toServiceHit(s: RawService): SearchHit {
  return {
    id: s.id,
    kind: 'service',
    displayName: s.name_ru,
    officialName: s.name_ru,
    code: s.oked_code ?? s.ikpu_code ?? '',
    codeKind: s.oked_code ? 'oked' : 'ikpu',
  }
}

export async function searchServicesReal(query: string): Promise<SearchHit[]> {
  const q = query.trim()
  if (q.length < 2) return []
  const pattern = `%${q.replaceAll('%', '').replaceAll(',', '')}%`
  const digits = q.replace(/\D/g, '')
  const codeFilters: string[] = []
  if (/^[0-9][0-9.]*$/.test(q)) codeFilters.push(`oked_code.like.${q}%`)
  if (digits.length >= 2) codeFilters.push(`ikpu_code.like.${digits}%`)

  const [aliasRes, nameRes, codeRes] = await Promise.all([
    supabase
      .from('search_aliases')
      .select('service_id, services(id, name_ru, oked_code, ikpu_code)')
      .ilike('alias', pattern)
      .not('service_id', 'is', null)
      .limit(8),
    supabase
      .from('services')
      .select('id, name_ru, oked_code, ikpu_code')
      .eq('is_active', true)
      .ilike('name_ru', pattern)
      .limit(8),
    codeFilters.length > 0
      ? supabase
          .from('services')
          .select('id, name_ru, oked_code, ikpu_code')
          .eq('is_active', true)
          .or(codeFilters.join(','))
          .limit(8)
      : Promise.resolve({ data: [] as RawService[] }),
  ])

  const byId = new Map<string, RawService>()
  for (const row of aliasRes.data ?? []) {
    const s = row.services
    if (s) byId.set(s.id, s)
  }
  for (const s of [...(nameRes.data ?? []), ...(codeRes.data ?? [])]) {
    if (!byId.has(s.id)) byId.set(s.id, s)
  }
  return [...byId.values()].slice(0, 8).map(toServiceHit)
}

export async function fetchServicePassportReal(
  serviceId: string,
): Promise<ServicePassport | null> {
  const { data: s } = await supabase
    .from('services')
    .select('id, name_ru, oked_code, ikpu_code, admission_mode, complexity_index, authorities(name_ru)')
    .eq('id', serviceId)
    .maybeSingle()
  if (!s) return null
  return {
    id: s.id,
    displayName: s.name_ru,
    okedCode: s.oked_code ?? undefined,
    ikpuCode: s.ikpu_code ?? undefined,
    admissionMode: s.admission_mode ?? undefined,
    authorityName: s.authorities?.name_ru ?? undefined,
    complexity: s.complexity_index ?? undefined,
  }
}

/** Метрика «документов собрать»: details закрыты RLS — анониму вернётся 0 строк → null (locked) */
export async function fetchServiceDocumentsCountReal(
  requirementIds: string[],
): Promise<number | null> {
  if (requirementIds.length === 0) return null
  const { data } = await supabase
    .from('requirement_details')
    .select('documents')
    .in('requirement_id', requirementIds)
  if (!data || data.length === 0) return null
  let count = 0
  for (const row of data) count += parseDocuments(row.documents).length
  return count
}

// ── Список требований (уровень 0) ──────────────────────────────────

export interface RequirementListReal {
  rows: RequirementRow[]
  stages: StageInfo[]
  verifiedAt?: string
}

const REQUIREMENT_LIST_SELECT = `id, deontic, operation, transport_type, addressee_roles, trust_label, review_flag, reviewed_at, published_at, requirement_category, nature,
       lifecycle_stages(id, name_ru, sort_order),
       authorities(name_ru),
       requirement_contents(lang, title, sanction_summary),
       requirement_applicability!inner(code, scope)`

interface RawListRow {
  id: string
  deontic: RequirementRow['deontic']
  operation: RequirementRow['operation']
  transport_type: RequirementRow['transport'] | null
  addressee_roles: RequirementRow['roles']
  trust_label: DbTrustLabel
  review_flag: 'none' | 'flagged_by_change'
  reviewed_at: string | null
  published_at: string | null
  requirement_category: NonNullable<RequirementRow['category']> | null
  nature: NonNullable<RequirementRow['nature']> | null
  lifecycle_stages: { id: string; name_ru: string; sort_order: number } | null
  authorities: { name_ru: string } | null
  requirement_contents: { lang: string; title: string; sanction_summary: string | null }[]
}

export async function fetchRequirementsReal(
  hsCode: string,
): Promise<RequirementListReal> {
  const { data, error } = await supabase
    .from('requirements')
    .select(REQUIREMENT_LIST_SELECT)
    .eq('status', 'published')
    .or(`code.eq.${hsCode},scope.eq.all_products`, {
      referencedTable: 'requirement_applicability',
    })
  if (error) throw error
  return listFromData(data ?? [])
}

/** Требования услуги: точный код ОКЭД + классы-префиксы + общие для всех услуг */
export async function fetchServiceRequirementsReal(
  okedCode: string | null,
): Promise<RequirementListReal> {
  const filters = ['scope.eq.all_services']
  if (okedCode) {
    filters.push(`and(scope.eq.oked_code,code.eq.${okedCode})`)
    const prefixes = okedPrefixes(okedCode)
    if (prefixes.length > 0)
      filters.push(`and(scope.eq.oked_prefix,code.in.(${prefixes.join(',')}))`)
  }
  const { data, error } = await supabase
    .from('requirements')
    .select(REQUIREMENT_LIST_SELECT)
    .eq('status', 'published')
    .or(filters.join(','), { referencedTable: 'requirement_applicability' })
  if (error) throw error
  return listFromData(data ?? [])
}

/** «47.73» → ['47', '47.7', '47.73'] — иерархия классов ОКЭД */
function okedPrefixes(okedCode: string): string[] {
  const out: string[] = []
  for (let len = 2; len <= okedCode.length; len++) {
    const p = okedCode.slice(0, len)
    if (/^[0-9]{2}(\.[0-9]{1,2})?$/.test(p)) out.push(p)
  }
  return out
}

function listFromData(data: RawListRow[]): RequirementListReal {
  const rows: RequirementRow[] = []
  const seen = new Set<string>()
  for (const r of data) {
    const content =
      r.requirement_contents.find((c) => c.lang === 'ru') ??
      r.requirement_contents[0]
    if (!content) continue
    // Мусор миграции v1: строки-заглушки не показываем (правило «пустое не рендерится»)
    const title = content.title.trim()
    if (!title || ['none', 'null', '-', '—'].includes(title.toLowerCase())) continue
    // Дубли переноса: одинаковые (заголовок+этап+тип+роли) неотличимы для пользователя
    const dedupeKey = [
      title.toLowerCase().replace(/\s+/g, ' '),
      r.lifecycle_stages?.id ?? '',
      r.deontic,
      [...r.addressee_roles].sort().join(','),
      r.operation,
      r.transport_type ?? '',
    ].join('|')
    if (seen.has(dedupeKey)) continue
    seen.add(dedupeKey)
    const stage = r.lifecycle_stages
    rows.push({
      id: r.id,
      title,
      deontic: r.deontic,
      roles: r.addressee_roles,
      operation: r.operation,
      transport: r.transport_type ?? undefined,
      authorityName: r.authorities?.name_ru ?? undefined,
      sanctionSummary: content.sanction_summary ?? undefined,
      status: { kind: 'active' },
      unread: false,
      stageId: stage?.id ?? 'no-stage',
      stageName: stage?.name_ru ?? 'Общие требования',
      stageSortOrder: stage?.sort_order ?? 999,
      category: r.requirement_category ?? undefined,
      nature: r.nature ?? undefined,
      trustLabel: normalizeTrust(r.trust_label),
      trustDate: r.reviewed_at ?? undefined,
      underReview: r.review_flag === 'flagged_by_change',
    })
  }

  rows.sort(
    (a, b) => a.stageSortOrder - b.stageSortOrder || a.title.localeCompare(b.title, 'ru'),
  )

  const stageMap = new Map<string, StageInfo>()
  for (const row of rows) {
    const s = stageMap.get(row.stageId)
    if (s) s.count += 1
    else
      stageMap.set(row.stageId, {
        id: row.stageId,
        name: row.stageName,
        sortOrder: row.stageSortOrder,
        count: 1,
        unreadCount: 0,
      })
  }

  const published = data
    .map((r) => r.published_at)
    .filter((d): d is string => Boolean(d))
    .sort()
  return {
    rows,
    stages: [...stageMap.values()].sort((a, b) => a.sortOrder - b.sortOrder),
    verifiedAt: published.at(-1),
  }
}

// ── Карточка требования (уровни 1–2) ───────────────────────────────

export async function fetchCardReal(
  requirementId: string,
  isSubscriber: boolean,
): Promise<RequirementCard> {
  const [req, details, cits, faqs, revs] = await Promise.all([
    supabase
      .from('requirements')
      .select('authorities(name_ru, contacts, website)')
      .eq('id', requirementId)
      .maybeSingle(),
    supabase
      .from('requirement_details')
      .select('lang, description, how_to_comply, documents, sanctions')
      .eq('requirement_id', requirementId),
    supabase
      .from('requirement_citations')
      .select(
        'is_primary, sort_order, act_paragraphs(paragraph_ref, version_date, verbatim_ru, verbatim_uz, deep_link_url, acts(title, number))',
      )
      .eq('requirement_id', requirementId)
      .order('sort_order'),
    supabase
      .from('requirement_faqs')
      .select('question, answer, trust_label, lang, sort_order')
      .eq('requirement_id', requirementId)
      .order('sort_order'),
    supabase
      .from('requirement_revisions')
      .select('revision_no, change_note, created_at, change_events(title, was_text, now_text)')
      .eq('requirement_id', requirementId)
      .order('revision_no', { ascending: false }),
  ])

  let authority: AuthorityInfo | undefined
  const a = req.data?.authorities
  if (a) {
    authority = {
      name: a.name_ru,
      phone: parseContacts(a.contacts).phone,
      website: a.website ?? undefined,
    }
  }

  let detail: Gated<RequirementDetail> = locked
  const d =
    details.data?.find((x) => x.lang === 'ru') ?? details.data?.[0]
  if (d) {
    detail = ok({
      description: d.description ?? undefined,
      steps: parseSteps(d.how_to_comply),
      documents: parseDocuments(d.documents),
      sanctions: parseSanctions(d.sanctions),
    })
  } else if (isSubscriber) {
    detail = ok({ description: undefined, steps: [], documents: [], sanctions: [] })
  }

  let citations: Gated<Citation[]> = locked
  if ((cits.data ?? []).length > 0) {
    citations = ok(
      (cits.data ?? []).flatMap((c): Citation[] => {
        const p = c.act_paragraphs
        if (!p) return []
        return [
          {
            actTitle: p.acts?.title.split('\n')[0] ?? 'Акт',
            actNumber: p.acts?.number ?? undefined,
            paragraphRef: p.paragraph_ref,
            versionDate: p.version_date ?? undefined,
            verbatimRu: p.verbatim_ru ?? undefined,
            verbatimUz: p.verbatim_uz ?? undefined,
            deepLink: p.deep_link_url ?? undefined,
            isPrimary: c.is_primary,
          },
        ]
      }),
    )
  } else if (isSubscriber) {
    citations = ok([])
  }

  let faqList: Gated<FaqItem[]> = locked
  if ((faqs.data ?? []).length > 0) {
    faqList = ok(
      (faqs.data ?? [])
        .filter((f) => f.lang === 'ru')
        .map((f) => ({
          question: f.question,
          answer: f.answer,
          trustLabel: normalizeTrust(f.trust_label),
        })),
    )
  } else if (isSubscriber) {
    faqList = ok([])
  }

  let history: Gated<HistoryEntry[]> = locked
  if ((revs.data ?? []).length > 0) {
    history = ok(
      (revs.data ?? []).map((r) => ({
        date: r.created_at,
        title: r.change_events?.title ?? r.change_note ?? 'Редакция обновлена',
        was: r.change_events?.was_text ?? undefined,
        now: r.change_events?.now_text ?? undefined,
      })),
    )
  } else if (isSubscriber) {
    history = ok([])
  }

  return { requirementId, authority, detail, citations, faqs: faqList, history }
}

// ── Проверка юристом ───────────────────────────────────────────────

/** Заголовки-заглушки переноса v1 — правило то же, что в listFromData */
function isJunkTitle(title: string): boolean {
  const t = title.trim()
  return !t || ['none', 'null', '-', '—'].includes(t.toLowerCase())
}

interface RequirementLinkInfo {
  title?: string
  link?: string
  targetName?: string
}

/**
 * Требование → страница товара/услуги (маршрут + ?req= для раскрытия строки).
 * Точный код → своя страница; класс-префикс → первый подходящий товар/услуга;
 * «для всех» → витринная страница, где требование реально видно (IQOS/аптека).
 * Требования без единой страницы в каталоге остаются без ссылки —
 * очередь «Ждут проверки» такие строки не показывает.
 */
async function resolveRequirementLinks(
  requirementIds: string[],
): Promise<Map<string, RequirementLinkInfo>> {
  const out = new Map<string, RequirementLinkInfo>()
  if (requirementIds.length === 0) return out

  const { data } = await supabase
    .from('requirements')
    .select('id, requirement_contents(lang, title), requirement_applicability(scope, code)')
    .in('id', requirementIds)
  const reqs = data ?? []

  const hsCodes = new Set<string>()
  const hsPrefixes = new Set<string>()
  const okedCodes = new Set<string>()
  const okedPrefixSet = new Set<string>()
  let needAllProducts = false
  let needAllServices = false
  for (const r of reqs) {
    for (const a of r.requirement_applicability) {
      if (a.scope === 'hs_code' && a.code) hsCodes.add(a.code)
      if (a.scope === 'hs_prefix' && a.code) hsPrefixes.add(a.code)
      if (a.scope === 'oked_code' && a.code) okedCodes.add(a.code)
      if (a.scope === 'oked_prefix' && a.code) okedPrefixSet.add(a.code)
      if (a.scope === 'all_products') needAllProducts = true
      if (a.scope === 'all_services') needAllServices = true
    }
  }

  const productFilters = [...hsCodes].map((c) => `hs_code.eq.${c}`)
  for (const p of hsPrefixes) productFilters.push(`hs_code.like.${p}*`)
  const serviceFilters = [...okedCodes].map((c) => `oked_code.eq.${c}`)
  for (const p of okedPrefixSet) serviceFilters.push(`oked_code.like.${p}*`)

  const [productsRes, servicesRes] = await Promise.all([
    productFilters.length > 0
      ? supabase
          .from('products')
          .select('id, name_ru, hs_code')
          .or(productFilters.join(','))
          .eq('is_active', true)
      : Promise.resolve({ data: [] }),
    serviceFilters.length > 0
      ? supabase
          .from('services')
          .select('id, name_ru, oked_code')
          .or(serviceFilters.join(','))
          .eq('is_active', true)
      : Promise.resolve({ data: [] }),
  ])

  const products = productsRes.data ?? []
  const services = servicesRes.data ?? []
  const productByHs = new Map(products.map((p) => [p.hs_code, p] as const))
  const aliases = await defaultAliases(products.map((p) => p.id))
  const serviceByOked = new Map(
    services.flatMap((s) => (s.oked_code ? [[s.oked_code, s] as const] : [])),
  )

  const productLink = (p: { id: string; name_ru: string }, reqId: string) => ({
    link: `/product/${p.id}?req=${reqId}`,
    targetName: aliases.get(p.id) ?? officialFromRaw(p.name_ru),
  })
  const serviceLink = (s: { id: string; name_ru: string }, reqId: string) => ({
    link: `/service/${s.id}?req=${reqId}`,
    targetName: s.name_ru,
  })

  for (const r of reqs) {
    const content =
      r.requirement_contents.find((c) => c.lang === 'ru') ?? r.requirement_contents[0]
    const info: RequirementLinkInfo = { title: content?.title }

    // Точный код — самый конкретный маршрут
    for (const a of r.requirement_applicability) {
      if (info.link) break
      if (a.scope === 'hs_code' && a.code) {
        const p = productByHs.get(a.code)
        if (p) Object.assign(info, productLink(p, r.id))
      }
      if (a.scope === 'oked_code' && a.code) {
        const s = serviceByOked.get(a.code)
        if (s) Object.assign(info, serviceLink(s, r.id))
      }
    }
    // Класс-префикс — первый подходящий из каталога
    for (const a of r.requirement_applicability) {
      if (info.link) break
      if (a.scope === 'hs_prefix' && a.code) {
        const p = products.find((x) => x.hs_code.startsWith(a.code!))
        if (p) Object.assign(info, productLink(p, r.id))
      }
      if (a.scope === 'oked_prefix' && a.code) {
        const s = services.find((x) => x.oked_code?.startsWith(a.code!))
        if (s) Object.assign(info, serviceLink(s, r.id))
      }
    }
    // «Для всех» — витринная страница: требование там реально в списке
    if (!info.link) {
      const scopes = r.requirement_applicability.map((a) => a.scope)
      if (needAllProducts && scopes.includes('all_products')) {
        info.link = `/product/${CIGARETTES_PRODUCT_ID}?req=${r.id}`
        info.targetName = ru.cabinet.lawyer.queueAllProducts
      } else if (needAllServices && scopes.includes('all_services')) {
        info.link = `/service/${PHARMACY_SERVICE_ID}?req=${r.id}`
        info.targetName = ru.cabinet.lawyer.queueAllServices
      }
    }
    out.set(r.id, info)
  }
  return out
}

const REVIEW_SELECT =
  'id, requirement_id, lawyer_id, verdict, comment_text, status, official_reply, official_replied_at, created_at, lawyer_profiles(display_name, credentials)'

async function voteCountsFor(
  reviewIds: string[],
): Promise<Map<string, { helpful: number; notHelpful: number }>> {
  const map = new Map<string, { helpful: number; notHelpful: number }>()
  if (reviewIds.length === 0) return map
  const { data } = await supabase
    .from('review_vote_counts')
    .select('review_id, helpful, not_helpful')
    .in('review_id', reviewIds)
  for (const row of data ?? []) {
    if (row.review_id)
      map.set(row.review_id, {
        helpful: row.helpful ?? 0,
        notHelpful: row.not_helpful ?? 0,
      })
  }
  return map
}

/** Заключения по требованию: published для всех + свои pending для юриста */
export async function fetchLawyerReviewsReal(
  requirementId: string,
  userId?: string,
): Promise<LawyerReview[]> {
  const { data, error } = await supabase
    .from('requirement_reviews')
    .select(REVIEW_SELECT)
    .eq('requirement_id', requirementId)
    .order('created_at', { ascending: false })
  if (error) throw error
  const rows = (data ?? []).filter(
    (r) => r.status === 'published' || (userId && r.lawyer_id === userId && r.status === 'pending'),
  )
  const ids = rows.map((r) => r.id)

  const [counts, myVotes] = await Promise.all([
    voteCountsFor(ids),
    userId && ids.length > 0
      ? supabase.from('review_votes').select('review_id, vote').in('review_id', ids)
      : Promise.resolve({ data: [] }),
  ])
  const myVoteById = new Map(
    (myVotes.data ?? []).map((v) => [v.review_id, v.vote] as const),
  )

  const reviews = rows.map((r): LawyerReview => {
    const c = counts.get(r.id)
    return {
      id: r.id,
      requirementId: r.requirement_id,
      verdict: r.verdict,
      commentText: r.comment_text,
      status: r.status,
      lawyerId: r.lawyer_id,
      lawyerName: r.lawyer_profiles?.display_name ?? 'Юрист',
      credentials: r.lawyer_profiles?.credentials ?? undefined,
      officialReply: r.official_reply ?? undefined,
      officialRepliedAt: r.official_replied_at ?? undefined,
      helpful: c?.helpful ?? 0,
      notHelpful: c?.notHelpful ?? 0,
      myVote: (myVoteById.get(r.id) as 1 | -1 | undefined) ?? null,
      isMine: Boolean(userId && r.lawyer_id === userId),
      createdAt: r.created_at,
    }
  })

  // Свои «на модерации» — сверху, published — по полезности, затем по дате
  return reviews.sort((a, b) => {
    if ((a.status === 'pending') !== (b.status === 'pending'))
      return a.status === 'pending' ? -1 : 1
    const score = b.helpful - b.notHelpful - (a.helpful - a.notHelpful)
    if (score !== 0) return score
    return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
  })
}

/**
 * Поставить/сменить или снять (null → delete) голос.
 * Не upsert: PostgREST разворачивает его в ON CONFLICT DO UPDATE по всем
 * колонкам пейлоада, а UPDATE-грант колоночный (только vote) — получился бы
 * вечный 42501. Поэтому детерминированно: INSERT или UPDATE по hadVote,
 * с перекрёстным фолбэком на случай устаревшего кеша.
 */
export async function setReviewVoteReal(
  reviewId: string,
  vote: 1 | -1 | null,
  userId: string,
  hadVote: boolean,
): Promise<void> {
  if (vote === null) {
    const { error } = await supabase
      .from('review_votes')
      .delete()
      .eq('review_id', reviewId)
      .eq('user_id', userId)
    if (error) throw error
    return
  }

  const insertVote = () =>
    supabase.from('review_votes').insert({ review_id: reviewId, user_id: userId, vote })
  const updateVote = () =>
    supabase
      .from('review_votes')
      .update({ vote })
      .eq('review_id', reviewId)
      .eq('user_id', userId)
      .select('review_id')

  if (hadVote) {
    const upd = await updateVote()
    if (upd.error) throw upd.error
    if ((upd.data ?? []).length > 0) return
    // голос успели снять в другой вкладке — вставляем заново
    const ins = await insertVote()
    if (ins.error) throw ins.error
    return
  }

  const ins = await insertVote()
  if (!ins.error) return
  if (ins.error.code === '23505') {
    // голос уже есть (устаревший кеш) — меняем значение
    const upd = await updateVote()
    if (upd.error) throw upd.error
    return
  }
  throw ins.error
}

export async function submitLawyerReviewReal(input: {
  requirementId: string
  verdict: ReviewVerdict
  commentText: string
  userId: string
}): Promise<void> {
  const { error } = await supabase.from('requirement_reviews').insert({
    requirement_id: input.requirementId,
    lawyer_id: input.userId,
    verdict: input.verdict,
    comment_text: input.commentText,
  })
  if (error) throw error
}

/**
 * Заявка юриста; повторная подача после отказа — UPDATE той же строки
 * (триггер в базе вернёт статус в pending). Не upsert — см. setReviewVoteReal.
 */
export async function submitLawyerApplicationReal(input: {
  displayName: string
  credentials: string
  licenseNo?: string
  specializations?: string
  userId: string
  hasProfile: boolean
}): Promise<void> {
  const fields = {
    display_name: input.displayName,
    credentials: input.credentials,
    license_no: input.licenseNo || null,
    specializations: input.specializations || null,
  }

  if (input.hasProfile) {
    const upd = await supabase
      .from('lawyer_profiles')
      .update(fields)
      .eq('user_id', input.userId)
      .select('user_id')
    if (upd.error) throw upd.error
    if ((upd.data ?? []).length > 0) return
  }

  const ins = await supabase
    .from('lawyer_profiles')
    .insert({ user_id: input.userId, ...fields })
  if (ins.error?.code === '23505') {
    const upd = await supabase
      .from('lawyer_profiles')
      .update(fields)
      .eq('user_id', input.userId)
    if (upd.error) throw upd.error
    return
  }
  if (ins.error) throw ins.error
}

export async function fetchMyLawyerProfileReal(
  userId: string,
): Promise<LawyerProfile | null> {
  const { data } = await supabase
    .from('lawyer_profiles')
    .select('display_name, credentials, license_no, specializations, status, verified_at')
    .eq('user_id', userId)
    .maybeSingle()
  if (!data) return null
  return {
    displayName: data.display_name,
    credentials: data.credentials,
    licenseNo: data.license_no ?? undefined,
    specializations: data.specializations ?? undefined,
    status: data.status,
    verifiedAt: data.verified_at ?? undefined,
  }
}

export async function fetchLawyerStatsReal(userId: string): Promise<LawyerStats> {
  const { data } = await supabase
    .from('lawyer_stats')
    .select('requirements_reviewed, reviews_published, helpful_total, not_helpful_total')
    .eq('lawyer_id', userId)
    .maybeSingle()
  return {
    requirementsReviewed: data?.requirements_reviewed ?? 0,
    reviewsPublished: data?.reviews_published ?? 0,
    helpfulTotal: data?.helpful_total ?? 0,
    notHelpfulTotal: data?.not_helpful_total ?? 0,
  }
}

interface RawLeaderboardRow {
  lawyer_id: string | null
  display_name: string | null
  credentials: string | null
  requirements_reviewed: number | null
  reviews_published: number | null
  helpful_total: number | null
  not_helpful_total: number | null
  rank: number | null
}

function toLeaderboardEntry(r: RawLeaderboardRow): LeaderboardEntry {
  return {
    lawyerId: r.lawyer_id ?? '',
    displayName: r.display_name ?? 'Юрист',
    credentials: r.credentials ?? undefined,
    requirementsReviewed: r.requirements_reviewed ?? 0,
    reviewsPublished: r.reviews_published ?? 0,
    helpfulTotal: r.helpful_total ?? 0,
    notHelpfulTotal: r.not_helpful_total ?? 0,
    rank: r.rank ?? 0,
  }
}

export async function fetchLeaderboardReal(
  userId?: string,
): Promise<LawyerLeaderboard> {
  const [topRes, countRes, meRes] = await Promise.all([
    supabase
      .from('lawyer_leaderboard')
      .select('*')
      .order('rank', { ascending: true })
      .limit(10),
    supabase
      .from('lawyer_leaderboard')
      .select('lawyer_id', { count: 'exact', head: true }),
    userId
      ? supabase.from('lawyer_leaderboard').select('*').eq('lawyer_id', userId).maybeSingle()
      : Promise.resolve({ data: null }),
  ])
  return {
    top: (topRes.data ?? []).map(toLeaderboardEntry),
    total: countRes.count ?? 0,
    me: meRes.data ? toLeaderboardEntry(meRes.data) : undefined,
  }
}

/** Счётчики бейджей одним запросом по requirement_ids страницы */
export async function fetchReviewStatsReal(
  requirementIds: string[],
): Promise<Record<string, RequirementReviewStats>> {
  if (requirementIds.length === 0) return {}
  const { data } = await supabase
    .from('requirement_review_stats')
    .select('requirement_id, confirms, disputes, total')
    .in('requirement_id', requirementIds)
  const out: Record<string, RequirementReviewStats> = {}
  for (const row of data ?? []) {
    if (row.requirement_id)
      out[row.requirement_id] = {
        confirms: row.confirms ?? 0,
        disputes: row.disputes ?? 0,
        total: row.total ?? 0,
      }
  }
  return out
}

/**
 * Очередь «Ждут проверки»: свежие published-требования без видимых заключений
 * (чужие pending скрыты RLS — это ожидаемая граница видимости).
 */
export async function fetchReviewQueueReal(): Promise<ReviewQueueItem[]> {
  const { data, error } = await supabase
    .from('requirements')
    .select(
      'id, published_at, requirement_contents(lang, title), requirement_reviews(id, status)',
    )
    .eq('status', 'published')
    .order('published_at', { ascending: false, nullsFirst: false })
    .limit(60)
  if (error) throw error

  const candidates = (data ?? []).filter((r) => {
    if (r.requirement_reviews.length > 0) return false
    const content =
      r.requirement_contents.find((c) => c.lang === 'ru') ?? r.requirement_contents[0]
    return content && !isJunkTitle(content.title)
  })

  // Ссылки резолвим до среза: строки, которым некуда вести (в каталоге нет
  // такой страницы), в очередь не попадают — юристу нечего было бы открыть
  const links = await resolveRequirementLinks(candidates.map((r) => r.id))
  return candidates
    .filter((r) => links.get(r.id)?.link)
    .slice(0, 10)
    .map((r) => {
      const content =
        r.requirement_contents.find((c) => c.lang === 'ru') ?? r.requirement_contents[0]
      const info = links.get(r.id)
      return {
        requirementId: r.id,
        title: content?.title ?? '—',
        publishedAt: r.published_at ?? undefined,
        link: info?.link,
        targetName: info?.targetName,
      }
    })
}

export async function fetchMyReviewsReal(userId: string): Promise<MyReviewItem[]> {
  const { data, error } = await supabase
    .from('requirement_reviews')
    .select('id, requirement_id, verdict, status, created_at')
    .eq('lawyer_id', userId)
    .order('created_at', { ascending: false })
    .limit(10)
  if (error) throw error
  const rows = data ?? []
  const [counts, links] = await Promise.all([
    voteCountsFor(rows.map((r) => r.id)),
    resolveRequirementLinks(rows.map((r) => r.requirement_id)),
  ])
  return rows.map((r) => {
    const c = counts.get(r.id)
    const info = links.get(r.requirement_id)
    return {
      id: r.id,
      requirementId: r.requirement_id,
      requirementTitle: info?.title ?? 'Требование',
      link: info?.link,
      verdict: r.verdict,
      status: r.status,
      helpful: c?.helpful ?? 0,
      notHelpful: c?.notHelpful ?? 0,
      createdAt: r.created_at,
    }
  })
}

export async function fetchLawyerNotificationsReal(): Promise<LawyerNotification[]> {
  const { data, error } = await supabase
    .from('lawyer_notifications')
    .select('id, kind, requirement_id, review_id, is_read, created_at')
    .order('created_at', { ascending: false })
    .limit(30)
  if (error) throw error
  const rows = data ?? []
  const reqIds = [...new Set(rows.flatMap((r) => (r.requirement_id ? [r.requirement_id] : [])))]
  const links = await resolveRequirementLinks(reqIds)
  return rows.map((r) => {
    const info = r.requirement_id ? links.get(r.requirement_id) : undefined
    return {
      id: r.id,
      kind: r.kind,
      requirementId: r.requirement_id ?? undefined,
      requirementTitle: info?.title,
      link: info?.link,
      isRead: r.is_read,
      createdAt: r.created_at,
    }
  })
}

export async function markLawyerNotificationReadReal(id: string): Promise<void> {
  const { error } = await supabase
    .from('lawyer_notifications')
    .update({ is_read: true, read_at: new Date().toISOString() })
    .eq('id', id)
  if (error) throw error
}

// ── Мои вопросы (user_questions, RLS: own read) ────────────────────

export async function fetchMyQuestionsReal(): Promise<UserQuestion[]> {
  const { data, error } = await supabase
    .from('user_questions')
    .select(
      'id, question_text, status, answer_text, answered_at, created_at, is_urgent, legal_review_only, product_id, requirement_id',
    )
    .order('created_at', { ascending: false })
    .limit(50)
  if (error) throw error
  return (data ?? []).map((r) => ({
    id: r.id,
    questionText: r.question_text,
    status: r.status,
    answerText: r.answer_text ?? undefined,
    answeredAt: r.answered_at ?? undefined,
    createdAt: r.created_at,
    isUrgent: r.is_urgent,
    legalReviewOnly: r.legal_review_only,
    productId: r.product_id ?? undefined,
    requirementId: r.requirement_id ?? undefined,
  }))
}

// ── Профиль (grant update: full_name, phone, company) ──────────────

export async function updateProfileReal(
  userId: string,
  input: { fullName: string; phone?: string; company?: string },
): Promise<void> {
  const { error } = await supabase
    .from('profiles')
    .update({
      full_name: input.fullName,
      phone: input.phone || null,
      company: input.company || null,
    })
    .eq('id', userId)
  if (error) throw error
}

// ── Формы (RLS: anyone insert) ─────────────────────────────────────

export async function submitSubscriptionRequest(input: {
  fullName: string
  contact: string
  company?: string
  userId?: string
}): Promise<void> {
  const { error } = await supabase.from('subscription_requests').insert({
    full_name: input.fullName,
    contact: input.contact,
    company: input.company || null,
    user_id: input.userId ?? null,
  })
  if (error) throw error
}

export async function submitContentRequest(input: {
  kind: 'fill_product' | 'missing_product' | 'missing_section'
  queryText?: string
  productId?: string
  comment?: string
  userId?: string
}): Promise<void> {
  const { error } = await supabase.from('content_requests').insert({
    kind: input.kind,
    query_text: input.queryText ?? null,
    product_id: input.productId ?? null,
    comment: input.comment ?? null,
    user_id: input.userId ?? null,
  })
  if (error) throw error
}

// ── Админка: входящие заявки (чтение по RLS admin) ────────────────

export interface SubscriptionRequestRow {
  id: string
  fullName: string
  contact: string
  company: string | null
  status: string
  note: string | null
  createdAt: string
}

export async function fetchSubscriptionRequests(): Promise<SubscriptionRequestRow[]> {
  const { data } = await supabase
    .from('subscription_requests')
    .select('id, full_name, contact, company, status, note, created_at')
    .order('created_at', { ascending: false })
    .limit(100)
  return (data ?? []).map((r) => ({
    id: r.id,
    fullName: r.full_name,
    contact: r.contact,
    company: r.company,
    status: r.status,
    note: r.note,
    createdAt: r.created_at,
  }))
}

export interface ContentRequestRow {
  id: string
  kind: string
  queryText: string | null
  status: string
  comment: string | null
  createdAt: string
}

export async function fetchContentRequests(): Promise<ContentRequestRow[]> {
  const { data } = await supabase
    .from('content_requests')
    .select('id, kind, query_text, status, comment, created_at')
    .order('created_at', { ascending: false })
    .limit(100)
  return (data ?? []).map((r) => ({
    id: r.id,
    kind: r.kind,
    queryText: r.query_text,
    status: r.status,
    comment: r.comment,
    createdAt: r.created_at,
  }))
}

// ── Портфель (chosen_products, только для залогиненных) ────────────

export async function fetchChosenReal(): Promise<
  { id: string; productId: string }[]
> {
  const { data } = await supabase
    .from('chosen_products')
    .select('id, product_id')
  return (data ?? []).flatMap((r) =>
    r.product_id ? [{ id: r.id, productId: r.product_id }] : [],
  )
}

export async function addChosenReal(userId: string, productId: string): Promise<void> {
  const { error } = await supabase
    .from('chosen_products')
    .insert({ user_id: userId, product_id: productId })
  if (error) throw error
}

export async function removeChosenReal(chosenId: string): Promise<void> {
  const { error } = await supabase.from('chosen_products').delete().eq('id', chosenId)
  if (error) throw error
}
