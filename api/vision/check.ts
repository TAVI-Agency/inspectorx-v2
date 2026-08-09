// Синхронный мост между витриной и воркером: JWT → проверка владения →
// подписанные ссылки → воркер → финализация ОДНОЙ транзакцией
// (RPC finalize_photo_inspection). Немедленного 202 нет намеренно: фронт всё
// равно живёт поллингом photo_inspection_events, а один синхронный вызов
// избавляет от второго диспетчера и от гонки «кто финализирует».
// maxDuration 300 задаётся в vercel.json.
import type { VercelRequest, VercelResponse } from '@vercel/node'
import {
  adminClient, assertOwnPrefix, bucketFor, EVIDENCE_BUCKET, getUserFromRequest,
  REFUNDABLE_REASONS, withVisionGuards, workerSecret, workerUrl,
} from '../_lib/vision.js'

// Ниже потолка функции (300 с в vercel.json): у нас должно остаться время
// записать финал, иначе прогон повиснет в running до реперной джобы.
// 90 с не хватало живому прогону: табачный PDF на CPU Railway упёрся в
// worker_timeout 09.08.2026 при холодном старте.
const WORKER_TIMEOUT_MS = 270_000
const SIGNED_URL_TTL_SEC = 600

interface SignedUrlRow {
  signedUrl?: string | null
}

export default withVisionGuards(async function handler(
  req: VercelRequest,
  res: VercelResponse,
): Promise<void> {
  if (req.method !== 'POST') {
    res.status(405).json({ reason: 'method' })
    return
  }
  const user = await getUserFromRequest(req)
  if (!user) {
    res.status(401).json({ reason: 'auth' })
    return
  }
  const inspectionId: string = (req.body as { inspectionId?: string } | undefined)?.inspectionId ?? ''
  if (!inspectionId) {
    res.status(422).json({ reason: 'no_inspection_id' })
    return
  }

  // Реквизиты воркера читаются ДО любой записи: пока их нет (до Волны 3)
  // ответ обязан быть 503, а строка не должна остаться в running с
  // потраченной попыткой.
  const worker = workerUrl()
  const secret = workerSecret()

  const db = adminClient()
  const { data: ins } = await db.from('photo_inspections')
    .select('*').eq('id', inspectionId).eq('user_id', user.id).maybeSingle()
  if (!ins) {
    res.status(404).json({ reason: 'not_found' })
    return
  }
  if (ins.status !== 'queued') {
    // идемпотентность прогона: запускает только queued, всё прочее — конфликт
    res.status(409).json({ reason: `status_${ins.status}` })
    return
  }

  const { data: assets } = await db.from('photo_assets')
    .select('idx, storage_path, kind, face_name').eq('inspection_id', inspectionId).order('idx')
  if (!assets?.length || !assertOwnPrefix(assets.map((a) => a.storage_path), user.id)) {
    res.status(422).json({ reason: 'bad_paths' })
    return
  }

  const bucket = bucketFor(ins.source_kind as 'photo' | 'master_pdf')
  const { data: signed, error: signError } = await db.storage.from(bucket)
    .createSignedUrls(assets.map((a) => a.storage_path), SIGNED_URL_TTL_SEC)
  const assetUrls = (signed ?? []).map((s: SignedUrlRow) => s.signedUrl ?? '')
  if (signError || assetUrls.length !== assets.length || assetUrls.some((u) => !u)) {
    console.error('vision/check: не подписаны ссылки', signError)
    res.status(500).json({ reason: 'sign_failed' })
    return
  }

  // Захват строки условным апдейтом: проверка выше (status !== 'queued') от
  // гонки не спасает — два параллельных запроса (двойной клик) прошли бы её
  // оба и дважды заплатили бы за прогон. Забрать queued может только один.
  const { data: claimed, error: claimError } = await db.from('photo_inspections').update({
    status: 'running',
    heartbeat_at: new Date().toISOString(),
    // потолок попыток зашит в check-констрейнт (attempts <= 2); дойти до него
    // штатным путём нельзя — повторный запуск отбивается 409 выше
    attempts: Math.min(ins.attempts + 1, 2),
  }).eq('id', inspectionId).eq('status', 'queued').select('id')
  if (claimError || !claimed?.length) {
    console.error('vision/check: строка уже занята другим запросом', claimError)
    res.status(409).json({ reason: 'already_running' })
    return
  }

  // Досъёмка/ревизия: прежние факты приезжают в воркер ТЕЛОМ запроса из
  // photo_facts, чтобы не переизвлекать старые кадры. Родитель — строка, у
  // которой superseded_by указывает на нас (так их связывает request_photo_retake).
  let priorFacts: unknown[] = []
  if (ins.revision > 1) {
    const { data: parent } = await db.from('photo_inspections')
      .select('id, revision').eq('superseded_by', inspectionId).maybeSingle()
    if (parent) {
      const { data: facts } = await db.from('photo_facts')
        .select('slot_id, payload, source, confidence, asset_idx, bbox')
        .eq('inspection_id', parent.id).eq('revision', parent.revision)
      priorFacts = facts ?? []
    }
  }

  // Габариты SKU (Задача 15, шаг 6, развилка 4 плана): own-all таблица,
  // читаем service_role — без них воркер не знает физический масштаб и
  // `min_size_mm` на фотопути честно не проверяется. Строки нет для
  // большинства пользователей сегодня — reference_dimensions_mm просто null.
  let referenceDimensionsMm: { width_mm: number; height_mm: number } | null = null
  if (ins.product_id) {
    const { data: dims } = await db.from('photo_product_dimensions')
      .select('width_mm, height_mm')
      .eq('user_id', user.id).eq('product_id', ins.product_id)
      .eq('packaging_level', ins.packaging_level).maybeSingle()
    if (dims) referenceDimensionsMm = { width_mm: dims.width_mm, height_mm: dims.height_mm }
  }

  // p_reason у RPC — необязательный аргумент со значением по умолчанию null,
  // поэтому «причины нет» передаётся не null-ом, а отсутствием ключа
  // (JSON.stringify выкидывает undefined).
  //
  // degradedMode передаётся, только когда он ЕСТЬ (typeof !== 'undefined'):
  // ключ p_degraded_mode в теле RPC — это то, что отличает вызов ПЯТИПАРАМЕТРОВОЙ
  // перегрузки finalize_photo_inspection (20260817100000_degraded_half_quota.sql,
  // половина единицы квоты при "local_only") от исходной четырёхпараметровой
  // (Волна 1) — PostgREST резолвит перегрузку по числу именованных аргументов,
  // и лишний ключ здесь звал бы не ту функцию.
  const finalize = (
    outcome: 'done' | 'failed',
    reason: string | null,
    payload?: unknown,
    degradedMode?: string | null,
  ) =>
    db.rpc('finalize_photo_inspection', {
      p_inspection_id: inspectionId,
      p_outcome: outcome,
      p_reason: reason ?? undefined,
      p_payload: (payload ?? null) as never,
      ...(degradedMode !== undefined ? { p_degraded_mode: degradedMode } : {}),
    } as never)

  const failWith = async (reason: string): Promise<void> => {
    const { error } = await finalize('failed', reason)
    if (error) console.error('vision/check: финал failed не записан', error)
    res.status(200).json({ status: 'failed', reason })
  }

  let workerResponse: Response
  try {
    workerResponse = await fetch(`${worker}/internal/inspect`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Worker-Secret': secret,
      },
      body: JSON.stringify({
        inspection_id: inspectionId,
        product: ins.product_key,
        level: ins.packaging_level,
        markets: ins.markets,
        evaluated_at: ins.created_at,
        ruleset_sha256: ins.ruleset_sha256,
        kind: ins.source_kind,
        asset_urls: assetUrls,
        faces: ins.source_kind === 'photo' ? assets.map((a) => a.face_name ?? 'unknown') : null,
        prior_facts: priorFacts.length ? priorFacts : null,
        reuse_facts: ins.revision > 1,
        reference_dimensions_mm: referenceDimensionsMm,
      }),
      signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
    })
  } catch (err) {
    const reason = err instanceof Error && err.name === 'TimeoutError'
      ? 'worker_timeout' : 'worker_unreachable'
    await failWith(reason)
    return
  }

  if (workerResponse.status === 409) {
    // набор правил разъехался: воркер передеплоился между заявкой и прогоном
    await failWith('ruleset_drift')
    return
  }
  if (!workerResponse.ok) {
    const body = await workerResponse.json().catch(() => null) as { reason?: unknown } | null
    const reported = typeof body?.reason === 'string' ? body.reason : null
    // 401/403 (секрет разъехался при ротации) и 5xx (воркер лёг) — отказ НАШЕЙ
    // инфраструктуры, единицу квоты за него брать нельзя: причина обязана быть
    // из возвратного списка. Названная воркером причина побеждает нашу догадку
    // только если она сама возвратная (503 + ocr_unavailable точнее, чем
    // worker_unreachable).
    // Осмысленный отказ по данным (no_text_layer, asset_fetch_failed…) квоту
    // НЕ возвращает — так и задумано, закрытый список живёт в
    // finalize_photo_inspection.
    const ourFault = workerResponse.status >= 500
      || workerResponse.status === 401 || workerResponse.status === 403
    const reason = reported && (!ourFault || REFUNDABLE_REASONS.has(reported))
      ? reported
      : 'worker_unreachable'
    if (ourFault) console.error('vision/check: воркер отказал по своей вине', workerResponse.status, reported)
    await failWith(reason)
    return
  }

  const result = await workerResponse.json().catch(() => null) as
    { findings?: Array<Record<string, unknown>>; degraded_mode?: string | null } | null
  if (!result) {
    // 200 с нечитаемым телом — отказ нашей инфраструктуры, а не данных
    // пользователя: код из возвратного списка, квота вернётся.
    console.error('vision/check: воркер вернул нечитаемое тело')
    await failWith('worker_unreachable')
    return
  }

  // Кропы-доказательства: base64 от воркера → бакет evidence-crops под
  // service_role (пользователь читает свой префикс, но не пишет туда).
  const findings = result.findings ?? []
  for (let i = 0; i < findings.length; i += 1) {
    const b64 = findings[i].evidence_crop_b64 as string | undefined
    if (!b64) continue
    const path = `${user.id}/${inspectionId}/${i}.jpg`
    const { error: upErr } = await db.storage.from(EVIDENCE_BUCKET)
      .upload(path, Buffer.from(b64, 'base64'), { contentType: 'image/jpeg' })
    if (upErr) {
      // находка ценна и без картинки — теряем только иллюстрацию
      console.error('vision/check: кроп не залит', upErr)
    } else {
      findings[i].evidence_crop_path = path
    }
    delete findings[i].evidence_crop_b64
  }

  const { error: finErr } = await finalize('done', null, { ...result, findings }, result.degraded_mode ?? null)
  if (finErr) {
    // Наружу — только код: текст ошибки PostgREST несёт имена таблиц/колонок и
    // текст констрейнтов, а эндпоинт публичный с первого дня. Полная ошибка
    // остаётся в логе функции (тот же приём во всех api/vision/*).
    console.error('vision/check: финал done не записан', finErr)
    res.status(500).json({ reason: 'internal' })
    return
  }
  res.status(200).json({ status: 'done', inspectionId })
})
