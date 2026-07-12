/**
 * Реальный источник: Supabase (anon key, RLS решает, что отдать).
 * Пейволл серверный: закрытые таблицы возвращают 0 строк анониму —
 * здесь это превращается в Gated { state: 'locked' }.
 */
import { supabase } from '@/lib/supabase'
import type { Json } from '@/lib/database.types'
import {
  locked,
  ok,
  type AuthorityInfo,
  type Citation,
  type FaqItem,
  type Gated,
  type HistoryEntry,
  type HowToStep,
  type RequiredDocument,
  type RequirementCard,
  type RequirementDetail,
  type RequirementRow,
  type SanctionItem,
  type SearchHit,
  type ProductPassport,
  type ServicePassport,
  type StageInfo,
} from './types'

// ── Разбор сырых полей ─────────────────────────────────────────────

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
  trust_label: RequirementRow['trustLabel']
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
      trustLabel: r.trust_label,
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
          trustLabel: f.trust_label,
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
