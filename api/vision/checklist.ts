// Чек-лист товара: что движок вообще умеет проверить до загрузки фото.
// Публичный тизер (авторизация не нужна) — отсюда кэш на CDN 5 минут.
// Профиль движка резолвится из каталога витрины (photo_profile_for_product),
// состав чек-листа знает только воркер — он и остаётся источником истины.
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { adminClient, withVisionGuards, workerUrl } from '../_lib/vision.js'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const LEVELS = new Set(['consumer', 'transport'])
const UPSTREAM_TIMEOUT_MS = 15_000

export default withVisionGuards(async function handler(
  req: VercelRequest,
  res: VercelResponse,
): Promise<void> {
  if (req.method !== 'GET') {
    res.status(405).json({ reason: 'method' })
    return
  }
  const productId = String(req.query.product ?? '')
  const level = String(req.query.level ?? 'consumer')
  if (!productId) {
    res.status(422).json({ reason: 'no_product' })
    return
  }
  // p_product_id — uuid: мусор из адресной строки не должен доезжать до
  // Postgres и возвращаться пятисоткой про invalid input syntax
  if (!UUID_RE.test(productId)) {
    res.status(422).json({ reason: 'bad_product' })
    return
  }
  if (!LEVELS.has(level)) {
    res.status(422).json({ reason: 'bad_level' })
    return
  }

  const worker = workerUrl()

  const db = adminClient()
  const { data: profile, error } = await db.rpc('photo_profile_for_product', {
    p_product_id: productId,
  })
  if (error) console.error('vision/checklist: профиль не резолвится', error)
  if (!profile) {
    // товар вне трёх категорий движка — честный отказ, а не пустой чек-лист
    res.status(404).json({ reason: 'no_checklist' })
    return
  }

  const upstream = await fetch(
    `${worker}/api/checklist?product=${encodeURIComponent(profile)}&level=${encodeURIComponent(level)}`,
    { signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) },
  ).catch(() => null)
  if (!upstream?.ok) {
    res.status(502).json({ reason: 'worker_unavailable' })
    return
  }
  const body = await upstream.json().catch(() => null)
  if (!body) {
    res.status(502).json({ reason: 'worker_unavailable' })
    return
  }
  res.setHeader('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=60')
  res.status(200).json({ profile, ...(body as Record<string, unknown>) })
})
