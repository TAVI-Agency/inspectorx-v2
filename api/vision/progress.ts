// Канал прогресса: воркер сообщает стадию прогона, витрина кладёт событие и
// обновляет пульс. Фронт живёт поллингом photo_inspection_events, а реперная
// джоба (reap_stale_inspections) по heartbeat_at понимает, что прогон жив.
//
// Пишет в photo_* только этот сервер под service_role — воркер в базу не ходит.
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { adminClient, requireWorkerSecret, withVisionGuards } from '../_lib/vision.js'

// Дословно check-констрейнт photo_inspection_events.stage
// (20260810100000_photo_runtime.sql): неизвестная стадия упала бы 500-й
// с текстом Postgres — отбиваем её здесь понятным 422.
const STAGES = new Set(['received', 'prepare', 'read', 'judge', 'render', 'done', 'failed'])

export default withVisionGuards(async function handler(
  req: VercelRequest,
  res: VercelResponse,
): Promise<void> {
  if (req.method !== 'POST') {
    res.status(405).json({ reason: 'method' })
    return
  }
  if (!requireWorkerSecret(req)) {
    res.status(401).json({ reason: 'secret' })
    return
  }
  const { inspection_id: inspectionId, stage, detail } = (req.body ?? {}) as {
    inspection_id?: string
    stage?: string
    detail?: unknown
  }
  if (!inspectionId || !stage || !STAGES.has(stage)) {
    res.status(422).json({ reason: 'bad_body' })
    return
  }

  const db = adminClient()
  const { error } = await db.from('photo_inspection_events').insert({
    inspection_id: inspectionId,
    stage,
    detail: (detail ?? {}) as never,
  })
  if (error) {
    // наружу — только код: текст PostgREST выдал бы имена таблиц/колонок
    console.error('vision/progress: событие не записано', error)
    res.status(500).json({ reason: 'internal' })
    return
  }
  // Пульс — на каждой стадии: репер добивает прогон, молчащий 3 минуты.
  await db.from('photo_inspections')
    .update({ heartbeat_at: new Date().toISOString() })
    .eq('id', inspectionId)
  res.status(200).json({ ok: true })
})
