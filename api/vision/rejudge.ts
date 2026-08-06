// Пересуд правленого факта: человек исправил то, что машина прочла неверно.
// Ноль сетевых вызовов к моделям и ноль строк в photo_model_calls — заново
// применяются только правила. Старый вердикт не переписывается никогда:
// результат уезжает новой ревизией (create_photo_revision, append-only).
import type { VercelRequest, VercelResponse } from '@vercel/node'
import {
  adminClient, getUserFromRequest, withVisionGuards, workerSecret, workerUrl,
} from '../_lib/vision.js'

const UPSTREAM_TIMEOUT_MS = 15_000

interface Override {
  slotId: string
  payload: unknown
  note?: string
}

interface FactRow {
  slot_id: string
  payload: unknown
  source: string
  confidence: number | null
  asset_idx: number | null
  bbox: unknown
}

/**
 * Паспорт фактов для новой ревизии: прежние факты плюс правки человека.
 *
 * Собирается здесь, а не берётся из ответа воркера: в контракте
 * RejudgeResponse поля facts нет, а create_photo_revision заполняет
 * photo_facts из p_payload->'facts'. Без этой сборки новая ревизия
 * получила бы ноль фактов, и следующая досъёмка/пересуд увидели бы пустой
 * паспорт — «всё нечитаемо».
 */
export function mergeFacts(prior: FactRow[], overrides: Override[]): FactRow[] {
  const merged = new Map<string, FactRow>()
  for (const fact of prior) merged.set(fact.slot_id, fact)
  for (const o of overrides) {
    const before = merged.get(o.slotId)
    merged.set(o.slotId, {
      slot_id: o.slotId,
      payload: o.payload,
      // человек — высший приоритет источника; машинная уверенность по этому
      // слоту больше не имеет значения
      source: 'human',
      confidence: 1,
      // привязка к кадру остаётся от прежнего факта: правится прочитанное
      // значение, а не место, где оно найдено
      asset_idx: before?.asset_idx ?? null,
      bbox: before?.bbox ?? null,
    })
  }
  return [...merged.values()]
}

function isOverride(value: unknown): value is Override {
  if (typeof value !== 'object' || value === null) return false
  const o = value as Partial<Override>
  return typeof o.slotId === 'string' && o.slotId.length > 0 && o.payload !== undefined
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
  const { inspectionId, overrides } = (req.body ?? {}) as {
    inspectionId?: string
    overrides?: unknown
  }
  if (!inspectionId || !Array.isArray(overrides) || overrides.length === 0) {
    res.status(422).json({ reason: 'bad_body' })
    return
  }
  if (!overrides.every(isOverride)) {
    res.status(422).json({ reason: 'bad_override' })
    return
  }

  const worker = workerUrl()
  const secret = workerSecret()

  const db = adminClient()
  const { data: ins } = await db.from('photo_inspections').select('*')
    .eq('id', inspectionId).eq('user_id', user.id).eq('status', 'done').maybeSingle()
  if (!ins) {
    res.status(404).json({ reason: 'not_found' })
    return
  }

  // 1. Записать правки: источник «человек» — высший приоритет, след остаётся
  //    даже если пересуд дальше не доедет.
  const overrideRows = overrides.map((o) => ({
    inspection_id: inspectionId,
    slot_id: o.slotId,
    payload: o.payload as never,
    author_user_id: user.id,
    note: o.note ?? '',
  }))
  const { error: ovErr } = await db.from('photo_fact_overrides').insert(overrideRows)
  if (ovErr) {
    console.error('vision/rejudge: правки не записаны', ovErr)
    res.status(500).json({ reason: ovErr.message })
    return
  }

  // 2. Факты последней ревизии — из БАЗЫ, а не из кэша контейнера воркера.
  const { data: facts } = await db.from('photo_facts')
    .select('slot_id, payload, source, confidence, asset_idx, bbox')
    .eq('inspection_id', inspectionId).eq('revision', ins.revision)

  // 3. Пересуд.
  const upstream = await fetch(`${worker}/internal/rejudge`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Worker-Secret': secret,
    },
    body: JSON.stringify({
      checklist_key: {
        product: ins.product_key, level: ins.packaging_level, markets: ins.markets,
      },
      facts: facts ?? [],
      overrides: overrides.map((o) => ({
        slot_id: o.slotId, payload: o.payload, note: o.note ?? '',
      })),
    }),
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  }).catch(() => null)
  if (!upstream?.ok) {
    res.status(502).json({ reason: 'worker_unavailable' })
    return
  }
  const verdict = await upstream.json().catch(() => null)
  if (!verdict) {
    res.status(502).json({ reason: 'worker_unavailable' })
    return
  }

  // 4. Новая ревизия одной транзакцией. Вердикт приходит от воркера, паспорт
  //    фактов собираем сами — воркер его не возвращает.
  const mergedFacts = mergeFacts((facts ?? []) as FactRow[], overrides)
  const { data: newId, error } = await db.rpc('create_photo_revision', {
    p_parent_id: inspectionId,
    p_payload: { ...(verdict as Record<string, unknown>), facts: mergedFacts } as never,
  })
  if (error) {
    console.error('vision/rejudge: ревизия не создана', error)
    // потолок ревизий (3) — это конфликт состояния, а не сбой сервера
    const status = error.message.includes('revision_limit') ? 409 : 500
    res.status(status).json({
      reason: status === 409 ? 'revision_limit' : error.message,
    })
    return
  }
  res.status(200).json({ inspectionId: newId })
})
