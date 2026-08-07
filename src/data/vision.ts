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
import type { ReviewVerdict } from './types'

export type PhotoInspectionRow = Database['public']['Tables']['photo_inspections']['Row']
export type PhotoFindingRow = Database['public']['Tables']['photo_findings']['Row']
export type PhotoNotCheckableRow = Database['public']['Tables']['photo_not_checkable']['Row']
export type PhotoAssetRow = Database['public']['Tables']['photo_assets']['Row']
export type PhotoInspectionEventRow =
  Database['public']['Tables']['photo_inspection_events']['Row']
export type PhotoFactRow = Database['public']['Tables']['photo_facts']['Row']
export type PhotoProductDimensionsRow =
  Database['public']['Tables']['photo_product_dimensions']['Row']

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
 *
 * `hints` — добавлено в Задаче 12 (экран загрузки, сценарий съёмки).
 * Contract воркера (`compiler/checklist.py`, вне этого репозитория) на
 * момент задачи не задокументирован; план (`docs/PHOTOCONTROL_INTEGRATION_PLAN.md:123`)
 * называет поле профиля `photo_hints_ru` и отмечает известный баг дня 1
 * (подсказка объявлена на верхнем уровне профиля, а лежит внутри
 * `levels.<level>`, из-за чего сценарий съёмки сейчас всегда пуст). Раз имя
 * и форма поля не подтверждены тестом/фикстурой (в отличие от `title`),
 * поле необязательно и типизировано широко — строка или список строк;
 * отсутствие или неожиданная форма просто не рендерит блок подсказки,
 * не роняет экран.
 */
export interface PackagingChecklist {
  profile: string
  title: string
  counters: ChecklistCounters
  groups: ChecklistGroup[]
  hints?: string | string[]
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
 * Заливка без `upsert` (Storage-политика "photo owners upload" не выдаёт
 * update) на уже занятый путь отвечает 409 `Duplicate`. Путь у нас
 * sha256-детерминирован (см. `objectPath`), поэтому «уже есть» означает
 * «тот же файл уже долетел раньше» — легитимный успех повторной попытки,
 * а не конфликт. Проверяем и по `status`/`statusCode` (устойчиво к точной
 * формулировке `message`), и по тексту — на случай будущей смены API Storage.
 */
export function isDuplicateUploadError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const e = error as { message?: string; statusCode?: string; status?: number }
  if (e.status === 409 || e.statusCode === '409') return true
  return typeof e.message === 'string' && /already exists|duplicate/i.test(e.message)
}

/**
 * Детерминированный путь объекта: `<uid>/<sha256-содержимого>.<ext>`. Тот же
 * файл (то же изображение после сжатия, тот же PDF) у того же пользователя
 * всегда ложится в один и тот же объект бакета — повторная попытка после
 * сетевого сбоя переливает поверх себя (см. `isDuplicateUploadError`), а не
 * плодит новый файл-сироту при каждом ретрае. Полностью сирот это не убирает
 * (см. комментарий у `uploadAndRequestInspection`), но ограничивает их число
 * количеством различных загруженных файлов, а не количеством попыток.
 */
export function objectPath(uid: string, sha256: string, ext: string): string {
  return `${uid}/${sha256}.${ext}`
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
    hints?: unknown
  }
  const hints =
    typeof body.hints === 'string' || Array.isArray(body.hints) ? body.hints : undefined
  return {
    profile: body.profile,
    title: body.title,
    counters: body.counters,
    groups: body.groups,
    hints: hints as string | string[] | undefined,
  }
}

/**
 * Заливка кадров/макета в приватный бакет своего префикса + резерв прогона
 * (RPC `request_photo_inspection`, платит квоту). Путь ОБЯЗАН начинаться с
 * `<uid>/` — этого требуют и Storage-политики, и сама RPC (план §4).
 *
 * **Файлы-сироты возможны и это осознанный компромисс, не баг.** Между
 * успешной заливкой в Storage (шаг 1) и успешной RPC (шаг 2, единственное
 * место, где путь попадает в `photo_assets`) есть окно: сеть может упасть,
 * вкладку могут закрыть, `not_subscriber`/`quota_exhausted`/`no_checklist`
 * может прервать RPC уже ПОСЛЕ заливки. Объект в бакете при этом остаётся
 * навсегда никем не удалённым: `authenticated` у Storage-политик
 * (`20260810110000_photo_storage.sql`) есть только `select`/`insert` под
 * своим префиксом — ни `delete`, ни `update` не выданы (кадры immutable по
 * дизайну, чистит только ретеншн-джоба), поэтому клиент физически не может
 * подчистить за собой даже в `catch`. `purge_expired_photo_assets`
 * (`20260810100000_photo_runtime.sql`) тоже не поможет: она уходит от строк
 * `photo_assets`, а у сироты такой строки нет и не будет.
 * Владельцу нужен отдельный процесс для реальной уборки — кандидат: в
 * Волне 3 расширить `purge_expired_photo_assets` (или завести соседнюю
 * джобу) орфан-сканом `storage.objects` по бакетам `packaging-artwork` /
 * `packaging-photos`: объект старше ~24ч без единой ссылающейся строки
 * `photo_assets.storage_path` — можно удалять `service_role`.
 * Здесь сделано то, что можно сделать без серверного гранта: путь
 * детерминирован от содержимого (`objectPath`, sha256), а не от случайного
 * `crypto.randomUUID()`/индекса — повторная попытка после сбоя (тот же
 * пользователь пересобирает те же файлы) переливает поверх уже залитого
 * объекта вместо того, чтобы плодить новую копию на каждый ретрай.
 *
 * `input.faces` пока не долетает до `photo_assets.face_name`: у клиента нет
 * UPDATE-гранта на photo_assets (тем же ограничением, что и выше), а сама
 * RPC такого аргумента не принимает — имя грани воркер проставляет позже
 * сам, в `finalize_photo_inspection` из тела своего ответа. Поле в
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
  const bucket = input.sourceKind === 'master_pdf' ? 'packaging-artwork' : 'packaging-photos'
  const ext = input.sourceKind === 'master_pdf' ? 'pdf' : 'jpg'
  const paths: string[] = []
  const buffers: ArrayBuffer[] = []
  for (let i = 0; i < input.files.length; i += 1) {
    const blob =
      input.sourceKind === 'photo'
        ? await prepareImageForUpload(input.files[i])
        : input.files[i]
    const buffer = await blob.arrayBuffer()
    const path = objectPath(uid, await sha256Hex(buffer), ext)
    const { error } = await supabase.storage.from(bucket).upload(path, blob)
    if (error && !isDuplicateUploadError(error)) throw error
    paths.push(path)
    buffers.push(buffer)
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
 * Слоты паспорта фактов текущей проверки (для модалки «Поправить факт»,
 * план §7 список 2). `revision` у `photo_facts` — это ревизия ЗАПОЛНЕНИЯ
 * факта внутри данного `inspection_id`, а не ревизия проверки (та уже
 * зафиксирована конкретным `id`, каждая ревизия проверки — своя строка
 * `photo_inspections`, см. `create_photo_revision` в
 * `20260810100000_photo_runtime.sql`) — фильтр по `inspection_id` уже даёт
 * факты именно этой ревизии, второй фильтр не нужен. Строки `source =
 * 'system'` (`__scan__` и подобные служебные, комментарий в миграции) не
 * редактируемые пользователем слоты — отбрасываются здесь, а не в
 * компоненте, чтобы и будущие потребители не рисовали их по ошибке.
 */
export async function fetchPhotoFacts(inspectionId: string): Promise<PhotoFactRow[]> {
  const { data, error } = await supabase
    .from('photo_facts')
    .select('*')
    .eq('inspection_id', inspectionId)
    .neq('source', 'system')
    .order('slot_id')
  if (error) throw error
  // Второй, клиентский, фильтр по префиксу `__` — на случай будущей служебной
  // строки с source, отличным от 'system' (защита от предположения, не от
  // наблюдаемого факта: на сегодня единственный известный служебный slot_id
  // — `__scan__` — и так приходит с source='system').
  return (data ?? []).filter((f) => !f.slot_id.startsWith('__'))
}

/**
 * Подписанные ссылки на кропы-доказательства (`evidence-crops`, приватный
 * бакет). RLS на `storage.objects` для этого бакета читает по тому же
 * own-read принципу, что и `photo_*` (владелец проверки), поэтому подпись
 * запрашивается под сессией пользователя, не сервисной ролью. Один запрос
 * на пачку путей — `createSignedUrls`, а не цикл `createSignedUrl`.
 */
export async function fetchEvidenceCropUrls(paths: string[]): Promise<Record<string, string>> {
  const unique = [...new Set(paths)]
  if (unique.length === 0) return {}
  const { data, error } = await supabase.storage.from('evidence-crops').createSignedUrls(unique, 3600)
  if (error) throw error
  const map: Record<string, string> = {}
  for (const item of data ?? []) {
    if (item.path && item.signedUrl) map[item.path] = item.signedUrl
  }
  return map
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
 * повторного резерва квоты — план §6, механизм 5). Тот же риск сирот в
 * Storage и то же смягчение детерминированным путём, что и у
 * `uploadAndRequestInspection` — см. развёрнутый комментарий там, здесь не
 * дублируется.
 *
 * `faces` (грань каждого нового кадра) в `photo_assets.face_name` не
 * попадает — тем же ограничением, что и у `uploadAndRequestInspection`
 * (нет UPDATE-гранта у клиента, RPC такого параметра не принимает);
 * участвует только в ключе идемпотентности, чтобы повторная досъёмка того
 * же набора граней не расходовала лишний прогон при повторном сабмите формы.
 */
export async function requestRetake(
  inspectionId: string,
  files: File[],
  faces: string[],
): Promise<string> {
  const { data: auth } = await supabase.auth.getUser()
  if (!auth.user) throw new Error('not_authenticated')
  const uid = auth.user.id
  const paths: string[] = []
  const buffers: ArrayBuffer[] = []
  for (let i = 0; i < files.length; i += 1) {
    const blob = await prepareImageForUpload(files[i])
    const buffer = await blob.arrayBuffer()
    const path = objectPath(uid, await sha256Hex(buffer), 'jpg')
    const { error } = await supabase.storage.from('packaging-photos').upload(path, blob)
    if (error && !isDuplicateUploadError(error)) throw error
    paths.push(path)
    buffers.push(buffer)
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

/**
 * Габариты упаковки SKU (Задача 15, шаг 6, развилка 4 плана): пользователь
 * вводит один раз на товар+уровень, own-all RLS (photo_product_dimensions —
 * 20260810130000_requirement_photo.sql). Без них `min_size_mm` на фотопути
 * не проверяется — движку не от чего считать миллиметры.
 */
export async function fetchProductDimensions(
  productId: string,
  level: PackagingLevel,
): Promise<PhotoProductDimensionsRow | null> {
  const { data: auth } = await supabase.auth.getUser()
  if (!auth.user) return null
  const { data, error } = await supabase
    .from('photo_product_dimensions')
    .select('*')
    .eq('user_id', auth.user.id)
    .eq('product_id', productId)
    .eq('packaging_level', level)
    .maybeSingle()
  if (error) throw error
  return data
}

export async function upsertProductDimensions(input: {
  productId: string
  level: PackagingLevel
  widthMm: number
  heightMm: number
  depthMm?: number
}): Promise<void> {
  const { data: auth } = await supabase.auth.getUser()
  if (!auth.user) throw new Error('not_authenticated')
  const { error } = await supabase.from('photo_product_dimensions').upsert(
    {
      user_id: auth.user.id,
      product_id: input.productId,
      packaging_level: input.level,
      width_mm: input.widthMm,
      height_mm: input.heightMm,
      depth_mm: input.depthMm ?? null,
    },
    { onConflict: 'user_id,product_id,packaging_level' },
  )
  if (error) throw error
}

export type PhotoFindingReviewRow = Database['public']['Tables']['photo_finding_reviews']['Row']
export type PhotoFindingQueueRow = Database['public']['Views']['photo_finding_queue']['Row']

/**
 * Строка очереди юриста (`public.photo_finding_queue`, Задача 14): находка,
 * эскалированная подписчиком (`record_finding_action('escalated')`), без
 * опубликованного заключения. Вью сама скрывает не-юристов предикатом
 * `is_verified_lawyer()` (`20260810120000_photo_review_queue.sql`) — здесь
 * авторизация не дублируется.
 */
export interface PhotoFindingQueueItem {
  findingId: string
  inspectionId: string
  checkpointId: string
  ruleRef: string
  severity: string
  status: string
  message: string
  productKey: string
  packagingLevel: PackagingLevel
  escalatedAt: string
}

/** Строки вью типизированы optional-полями (генератор Supabase для view), но
 * реально ни одно не бывает null — все столбцы вью берутся из not-null полей
 * `photo_findings`/`photo_inspections`/`photo_finding_actions`. Фолбэки ниже —
 * только чтобы успокоить компилятор, не признак ожидаемых пустых значений. */
function toQueueItem(r: PhotoFindingQueueRow): PhotoFindingQueueItem {
  return {
    findingId: r.finding_id ?? '',
    inspectionId: r.inspection_id ?? '',
    checkpointId: r.checkpoint_id ?? '',
    ruleRef: r.rule_ref ?? '',
    severity: r.severity ?? '',
    status: r.status ?? '',
    message: r.message ?? '',
    productKey: r.product_key ?? '',
    packagingLevel: (r.packaging_level as PackagingLevel) ?? 'consumer',
    escalatedAt: r.escalated_at ?? '',
  }
}

export async function fetchPhotoReviewQueue(): Promise<PhotoFindingQueueItem[]> {
  const { data, error } = await supabase
    .from('photo_finding_queue')
    .select('*')
    .order('escalated_at', { ascending: false })
  if (error) throw error
  return (data ?? []).map(toQueueItem)
}

/**
 * Заключение юриста по находке (`photo_finding_reviews`, insert-only —
 * append-only инвариант, политика "verified lawyer insert" держит
 * `status` всегда `default 'pending'`, колоночный грант не даёт клиенту
 * писать `status`/`official_reply` напрямую).
 */
export async function submitPhotoFindingReview(input: {
  findingId: string
  lawyerId: string
  verdict: ReviewVerdict
  commentText: string
}): Promise<void> {
  const { error } = await supabase.from('photo_finding_reviews').insert({
    finding_id: input.findingId,
    lawyer_id: input.lawyerId,
    verdict: input.verdict,
    comment_text: input.commentText,
  })
  if (error) throw error
}

/** Подпись вердикта (RPC `sign_photo_inspection`, только verified-юрист). */
export async function signInspection(inspectionId: string): Promise<void> {
  const { error } = await supabase.rpc('sign_photo_inspection', {
    p_inspection_id: inspectionId,
  })
  if (error) throw error
}

/**
 * Имя подписавшего юриста по `photo_inspections.signed_by` (auth.users.id).
 * Публичное чтение verified-профилей уже открыто ("public read verified",
 * `20260729013000_lawyer_reviews.sql`) — отдельного гранта не требуется.
 */
export async function fetchLawyerName(userId: string): Promise<string | null> {
  const { data, error } = await supabase
    .from('lawyer_profiles')
    .select('display_name')
    .eq('user_id', userId)
    .maybeSingle()
  if (error) throw error
  return data?.display_name ?? null
}

/** Опубликованное заключение юриста по конкретной находке — для отчёта. */
export interface PhotoFindingReviewItem {
  id: string
  findingId: string
  verdict: ReviewVerdict
  commentText: string
  lawyerName: string
  credentials?: string
  createdAt: string
}

/**
 * Опубликованные заключения пачкой по находкам страницы отчёта.
 * `lawyer_profiles(display_name, credentials)` — та же встроенная связь
 * (`lawyer_id -> lawyer_profiles.user_id`), что и у `requirement_reviews`
 * (см. `REVIEW_SELECT` в `real.ts`); публичное чтение verified-профилей уже
 * открыто политикой "public read verified" (`20260729013000_lawyer_reviews.sql`).
 */
export async function fetchFindingReviews(
  findingIds: string[],
): Promise<PhotoFindingReviewItem[]> {
  if (findingIds.length === 0) return []
  const { data, error } = await supabase
    .from('photo_finding_reviews')
    .select(
      'id, finding_id, verdict, comment_text, created_at, lawyer_profiles(display_name, credentials)',
    )
    .in('finding_id', findingIds)
    .eq('status', 'published')
    .order('created_at', { ascending: false })
  if (error) throw error
  return (data ?? []).map((r) => ({
    id: r.id,
    findingId: r.finding_id,
    verdict: r.verdict,
    commentText: r.comment_text,
    lawyerName: r.lawyer_profiles?.display_name ?? 'Юрист',
    credentials: r.lawyer_profiles?.credentials ?? undefined,
    createdAt: r.created_at,
  }))
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
