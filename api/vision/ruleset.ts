// Регистрация отпечатка набора правил: воркер передеплоился — сообщает
// sha256 собранного ruleset. Проверка стартует только при живой текущей
// версии (request_photo_inspection падает 'no_ruleset'), а несовпадение
// отпечатка на стороне воркера даёт 409 ruleset_drift.
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { adminClient, requireWorkerSecret, withVisionGuards } from '../_lib/vision.js'

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
  const {
    sha256, version, built_at: builtAt, packs, checks_count: checksCount,
  } = (req.body ?? {}) as {
    sha256?: unknown
    version?: unknown
    built_at?: unknown
    packs?: unknown
    checks_count?: unknown
  }
  if (typeof sha256 !== 'string' || sha256.length !== 64 || typeof version !== 'string' || !version) {
    res.status(422).json({ reason: 'bad_fingerprint' })
    return
  }

  const db = adminClient()
  // Снимаем is_current с предыдущей: на колонке частичный уникальный индекс,
  // двух текущих версий одновременно быть не может. neq по своему же
  // отпечатку делает повторную регистрацию той же версии идемпотентной.
  const { error: clearError } = await db.from('ruleset_versions')
    .update({ is_current: false })
    .eq('is_current', true)
    .neq('sha256', sha256)
  if (clearError) {
    console.error('vision/ruleset: не снят is_current', clearError)
    res.status(500).json({ reason: clearError.message })
    return
  }

  const { error } = await db.from('ruleset_versions').upsert({
    sha256,
    version,
    built_at: typeof builtAt === 'string' ? builtAt : new Date().toISOString(),
    packs: (packs ?? {}) as never,
    checks_count: typeof checksCount === 'number' ? checksCount : 0,
    is_current: true,
  })
  if (error) {
    console.error('vision/ruleset: версия не записана', error)
    res.status(500).json({ reason: error.message })
    return
  }
  res.status(200).json({ ok: true })
})
