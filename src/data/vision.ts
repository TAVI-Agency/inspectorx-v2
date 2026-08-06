/**
 * Фотоконтроль упаковки — единственная дверь фронта к photo_* (Волна 1,
 * Задача 11). Полностью реальные данные, мок-оверлея нет: RLS own-read на
 * photo_inspections/photo_findings/photo_not_checkable/photo_assets
 * (20260810100000_photo_runtime.sql) и три Vercel-эндпоинта из Задачи 10
 * (`api/vision/check|checklist|rejudge.ts`) — тот же контракт, что и там.
 * Компоненты сюда не заходят напрямую — только через `src/data/hooks.ts`.
 */
import { supabase } from '@/lib/supabase'
import { prepareImageForUpload } from '@/lib/image'
import type { Database } from '@/lib/database.types'

export type PhotoInspectionRow = Database['public']['Tables']['photo_inspections']['Row']
export type PhotoFindingRow = Database['public']['Tables']['photo_findings']['Row']
export type PhotoNotCheckableRow = Database['public']['Tables']['photo_not_checkable']['Row']
export type PhotoAssetRow = Database['public']['Tables']['photo_assets']['Row']
export type PhotoInspectionEventRow =
  Database['public']['Tables']['photo_inspection_events']['Row']

/** packaging_inspections.packaging_level — CHECK-констрейнт в 20260810100000_photo_runtime.sql */
export type PackagingLevel = 'consumer' | 'transport'

export interface ChecklistCounters {
  checkable: number
  partial: number
  notCheckable: number
  noGold: number
}

/**
 * Состав пункта чек-листа и группы решает воркер (`GET /api/checklist`,
 * `compiler/checklist.py`) — контракт не документирован для витрины на
 * момент этой задачи, поэтому item типизирован структурно-открытым: любые
 * дополнительные поля воркера доезжают без потери, обязателен только `key`.
 */
export interface ChecklistItem {
  key: string
  title?: string
  [extra: string]: unknown
}

export interface ChecklistGroup {
  key: string
  title?: string
  items: ChecklistItem[]
}

/**
 * `title` — не в исходном наброске интерфейса брифа, но фактический ответ
 * `GET /api/vision/checklist` (Задача 10, `api/vision/checklist.ts:64`)
 * его отдаёт (`{ profile, ...body }`, где `body.title` — из воркера).
 * Отбрасывать доехавшее поле было бы немотивированной потерей данных —
 * решение зафиксировано в отчёте Задачи 11 как расхождение брифа с фактом.
 */
export interface PackagingChecklist {
  profile: string
  title: string
  counters: ChecklistCounters
  groups: ChecklistGroup[]
}

export interface InspectionBundle {
  inspection: PhotoInspectionRow
  findings: PhotoFindingRow[]
  notCheckable: PhotoNotCheckableRow[]
  assets: PhotoAssetRow[]
}

async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', data)
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
}

/**
 * Ключ идемпотентности заявки: sha256 отсортированных sha256 файлов + уровень
 * упаковки + отсортированные рынки (план §4). Порядок файлов и рынков на
 * входе не важен — сортируем перед склейкой, чтобы одна и та же заявка,
 * собранная в другом порядке, не превратилась во вторую единицу квоты.
 * Набор действующих правил (`ruleset_versions.is_current`) в ключ не входит —
 * его добавляет сервер внутри RPC `request_photo_inspection`.
 */
export async function buildIdempotencyKey(
  files: ArrayBuffer[],
  level: string,
  markets: string[],
): Promise<string> {
  const hashes = await Promise.all(files.map(sha256Hex))
  const material = [...hashes].sort().join('|') + `|${level}|${[...markets].sort().join(',')}`
  return sha256Hex(new TextEncoder().encode(material).buffer as ArrayBuffer)
}

/**
 * Публичный тизер: что движок вообще умеет проверить у товара до загрузки
 * фото. Авторизация не нужна (см. `api/vision/checklist.ts`). 404 `no_checklist`
 * (товар вне трёх профилей движка) — легитимный результат, не исключение.
 */
export async function fetchPackagingChecklist(
  productId: string,
  level: PackagingLevel,
): Promise<PackagingChecklist | null> {
  const res = await fetch(
    `/api/vision/checklist?product=${encodeURIComponent(productId)}&level=${encodeURIComponent(level)}`,
  )
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`checklist_failed_${res.status}`)
  const body = (await res.json()) as {
    profile: string
    title: string
    groups: ChecklistGroup[]
    counters: ChecklistCounters
  }
  return { profile: body.profile, title: body.title, counters: body.counters, groups: body.groups }
}

/**
 * Заливка кадров/макета в приватный бакет своего префикса + резерв прогона
 * (RPC `request_photo_inspection`, платит квоту). Путь ОБЯЗАН начинаться с
 * `<uid>/` — этого требуют и Storage-политики, и сама RPC (план §4).
 *
 * `input.faces` пока не долетает до `photo_assets.face_name`: у клиента нет
 * UPDATE-гранта на photo_assets (снят явно в 20260810100000_photo_runtime.sql),
 * а сама RPC такого аргумента не принимает — имя грани воркер проставляет
 * позже сам, в `finalize_photo_inspection` из тела своего ответа. Поле в
 * сигнатуре сохранено дословно по брифу для будущего экрана (Волна 3, когда
 * воркер подключится и сможет подтверждать/поправлять грань на превью).
 */
export async function uploadAndRequestInspection(input: {
  productId: string
  level: PackagingLevel
  sourceKind: 'photo' | 'master_pdf'
  files: File[]
  faces?: string[]
}): Promise<string> {
  const { data: auth } = await supabase.auth.getUser()
  if (!auth.user) throw new Error('not_authenticated')
  const uid = auth.user.id
  const folder = crypto.randomUUID()
  const bucket = input.sourceKind === 'master_pdf' ? 'packaging-artwork' : 'packaging-photos'
  const paths: string[] = []
  const buffers: ArrayBuffer[] = []
  for (let i = 0; i < input.files.length; i += 1) {
    const blob =
      input.sourceKind === 'photo'
        ? await prepareImageForUpload(input.files[i])
        : input.files[i]
    const ext = input.sourceKind === 'master_pdf' ? 'pdf' : 'jpg'
    const path = `${uid}/${folder}/${i}.${ext}`
    const { error } = await supabase.storage.from(bucket).upload(path, blob)
    if (error) throw error
    paths.push(path)
    buffers.push(await blob.arrayBuffer())
  }
  const key = await buildIdempotencyKey(buffers, input.level, ['UZ'])
  const { data, error } = await supabase.rpc('request_photo_inspection', {
    p_product_id: input.productId,
    p_level: input.level,
    p_markets: ['UZ'],
    p_source_kind: input.sourceKind,
    p_asset_paths: paths,
    p_idempotency_key: key,
  })
  if (error) throw error
  return data
}

/**
 * Запуск синхронного прогона (`POST /api/vision/check`, Задача 10). Эндпоинт
 * всегда отвечает 200 с `{status: 'done' | 'failed', reason?}` для легитимных
 * бизнес-исходов — это не исключения, поллинг `useInspectionBundle` их и ждёт.
 * Настоящие ошибки (401 протухший токен, 404 чужая/неизвестная проверка,
 * 409 уже запущена, 503 воркер не подключён) — другой канал: бросаем
 * исключение, чтобы `useMutation` отличил их от штатного «не читается».
 * Бриф давал `return res.json()` без разбора кода ответа — тело ошибки
 * несёт только `reason` без `status`, что разошлось бы с типом; разбор
 * добавлен по факту контракта Задачи 10.
 */
export async function startInspection(
  inspectionId: string,
): Promise<{ status: string; reason?: string }> {
  const { data: session } = await supabase.auth.getSession()
  const jwt = session.session?.access_token
  if (!jwt) throw new Error('not_authenticated')
  const res = await fetch('/api/vision/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${jwt}` },
    body: JSON.stringify({ inspectionId }),
  })
  const body = (await res.json().catch(() => null)) as
    | { status: 'done' | 'failed'; reason?: string; inspectionId?: string }
    | { reason: string }
    | null
  if (!res.ok || !body || !('status' in body)) {
    const reason = body && 'reason' in body ? body.reason : `check_failed_${res.status}`
    throw new Error(reason)
  }
  return body
}

/** Четыре собственные строки проверки — RLS own-read решает видимость. */
export async function fetchInspectionBundle(id: string): Promise<InspectionBundle | null> {
  const [insRes, findingsRes, notCheckableRes, assetsRes] = await Promise.all([
    supabase.from('photo_inspections').select('*').eq('id', id).maybeSingle(),
    supabase.from('photo_findings').select('*').eq('inspection_id', id),
    supabase.from('photo_not_checkable').select('*').eq('inspection_id', id),
    supabase.from('photo_assets').select('*').eq('inspection_id', id).order('idx'),
  ])
  if (insRes.error) throw insRes.error
  if (!insRes.data) return null
  if (findingsRes.error) throw findingsRes.error
  if (notCheckableRes.error) throw notCheckableRes.error
  if (assetsRes.error) throw assetsRes.error
  return {
    inspection: insRes.data,
    findings: findingsRes.data ?? [],
    notCheckable: notCheckableRes.data ?? [],
    assets: assetsRes.data ?? [],
  }
}

export async function fetchInspectionEvents(id: string): Promise<PhotoInspectionEventRow[]> {
  const { data, error } = await supabase
    .from('photo_inspection_events')
    .select('*')
    .eq('inspection_id', id)
    .order('at')
  if (error) throw error
  return data ?? []
}

/**
 * Пересуд правленого факта (`POST /api/vision/rejudge`, Задача 10). Ни
 * одного сетевого вызова к моделям — только перепрогон правил; результат
 * уезжает новой ревизией, старая не переписывается.
 */
export async function submitFactOverride(
  inspectionId: string,
  overrides: { slotId: string; payload: unknown; note?: string }[],
): Promise<string> {
  const { data: session } = await supabase.auth.getSession()
  const jwt = session.session?.access_token
  if (!jwt) throw new Error('not_authenticated')
  const res = await fetch('/api/vision/rejudge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${jwt}` },
    body: JSON.stringify({ inspectionId, overrides }),
  })
  const body = (await res.json().catch(() => null)) as
    | { inspectionId: string }
    | { reason: string }
    | null
  if (!res.ok || !body || !('inspectionId' in body)) {
    const reason = body && 'reason' in body ? body.reason : `rejudge_failed_${res.status}`
    throw new Error(reason)
  }
  return body.inspectionId
}

/**
 * Досъёмка: новые кадры того же макета + RPC `request_photo_retake` (без
 * повторного резерва квоты — план §6, механизм 5). `faces` (грань каждого
 * нового кадра) в `photo_assets.face_name` не попадает — тем же ограничением,
 * что и у `uploadAndRequestInspection` (нет UPDATE-гранта у клиента, RPC
 * такого параметра не принимает); участвует только в ключе идемпотентности,
 * чтобы повторная досъёмка того же набора граней не расходовала лишний
 * прогон при повторном сабмите формы.
 */
export async function requestRetake(
  inspectionId: string,
  files: File[],
  faces: string[],
): Promise<string> {
  const { data: auth } = await supabase.auth.getUser()
  if (!auth.user) throw new Error('not_authenticated')
  const uid = auth.user.id
  const folder = crypto.randomUUID()
  const paths: string[] = []
  const buffers: ArrayBuffer[] = []
  for (let i = 0; i < files.length; i += 1) {
    const blob = await prepareImageForUpload(files[i])
    const path = `${uid}/${folder}/${i}.jpg`
    const { error } = await supabase.storage.from('packaging-photos').upload(path, blob)
    if (error) throw error
    paths.push(path)
    buffers.push(await blob.arrayBuffer())
  }
  const key = await buildIdempotencyKey(buffers, 'retake', faces)
  const { data, error } = await supabase.rpc('request_photo_retake', {
    p_inspection_id: inspectionId,
    p_new_asset_paths: paths,
    p_idempotency_key: key,
  })
  if (error) throw error
  return data
}

/** Действие юзера по находке (RPC `record_finding_action`, SECURITY DEFINER, own-only). */
export async function submitFindingAction(
  findingId: string,
  action: 'fixed' | 'accepted_with_reason' | 'escalated',
  reason?: string,
): Promise<void> {
  const { error } = await supabase.rpc('record_finding_action', {
    p_finding_id: findingId,
    p_action: action,
    p_reason: reason,
  })
  if (error) throw error
}

/** Находки для пересъёмки, сгруппированные по грани — самая проблемная грань первой. */
export function groupRetakeBySurface(
  findings: PhotoFindingRow[],
): { surface: string; findings: PhotoFindingRow[] }[] {
  const bySurface = new Map<string, PhotoFindingRow[]>()
  for (const f of findings) {
    const list = bySurface.get(f.surface)
    if (list) list.push(f)
    else bySurface.set(f.surface, [f])
  }
  return [...bySurface.entries()]
    .map(([surface, list]) => ({ surface, findings: list }))
    .sort((a, b) => b.findings.length - a.findings.length)
}

export function reportCounters(bundle: InspectionBundle): {
  violations: number
  decided: number
  checked: number
  needsHuman: number
} {
  return {
    violations: bundle.findings.filter((f) => f.status === 'fail').length,
    decided: bundle.inspection.decided ?? 0,
    checked: bundle.inspection.checked ?? 0,
    needsHuman: bundle.findings.filter((f) => f.confidence_class === 'needs_human').length,
  }
}

/**
 * Вердикт с `overall = 'fail'` или с любой критичной находкой не окончателен,
 * пока не проставлен `signed_by` (план §8, `sign_photo_inspection`).
 */
export function isPreliminary(bundle: InspectionBundle): boolean {
  if (bundle.inspection.signed_by) return false
  if (bundle.inspection.overall === 'fail') return true
  return bundle.findings.some((f) => f.severity === 'critical')
}
