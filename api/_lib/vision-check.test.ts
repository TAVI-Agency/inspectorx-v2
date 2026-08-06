// Оркестратор прогона: JWT → владение → подписанные ссылки → воркер →
// финализация одной транзакцией. Сети здесь нет: fetch подменён, база —
// дублёр. Проверяется проводка и выбор машинных кодов отказа.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeFakeDb, makeFakeResponse, makeRequest, type FakeRoutes } from './vision-test-doubles.js'

const state = vi.hoisted(() => ({ db: null as unknown as ReturnType<typeof makeFakeDb> }))

vi.mock('@supabase/supabase-js', () => ({ createClient: () => state.db }))

const { default: check } = await import('../vision/check.js')
const { REFUNDABLE_REASONS } = await import('./vision.js')

const UID = 'u-1'
const INSPECTION_ID = 'ins-1'
const SHA = 'a'.repeat(64)

const INSPECTION = {
  id: INSPECTION_ID,
  user_id: UID,
  product_id: 'prod-1',
  product_key: 'tobacco',
  packaging_level: 'consumer',
  markets: ['UZ'],
  source_kind: 'photo',
  status: 'queued',
  revision: 1,
  attempts: 0,
  created_at: '2026-08-07T00:00:00.000Z',
  ruleset_sha256: SHA,
}

const ASSETS = [
  { idx: 0, storage_path: `${UID}/${INSPECTION_ID}/0.jpg`, kind: 'photo', face_name: 'front' },
  { idx: 1, storage_path: `${UID}/${INSPECTION_ID}/1.jpg`, kind: 'photo', face_name: 'back' },
]

const SIGNED = [
  { signedUrl: 'https://storage.example/0', path: ASSETS[0].storage_path, error: null },
  { signedUrl: 'https://storage.example/1', path: ASSETS[1].storage_path, error: null },
]

const WORKER_RESULT = {
  overall: 'fail',
  decided: 12,
  checked: 14,
  findings: [
    { checkpoint_id: 'c1', rule_ref: 'ПКМ-43 п.1', group_key: 'g', kind: 'k', severity: 'critical', status: 'fail', evidence_crop_b64: Buffer.from('кроп').toString('base64') },
    { checkpoint_id: 'c2', rule_ref: 'ПКМ-43 п.2', group_key: 'g', kind: 'k', severity: 'minor', status: 'pass' },
  ],
  facts: [{ slot_id: 'brand', payload: { text: 'X' }, source: 'ocr' }],
  cost_usd: 0.42,
}

function baseRoutes(overrides: FakeRoutes = {}): FakeRoutes {
  return {
    'auth.getUser': { data: { id: UID }, error: null },
    'photo_inspections.select': { data: INSPECTION, error: null },
    'photo_assets.select': { data: ASSETS, error: null },
    'storage.packaging-photos.createSignedUrls': { data: SIGNED, error: null },
    'photo_inspections.update': { data: [{ id: INSPECTION_ID }], error: null },
    'storage.evidence-crops.upload': { error: null },
    'rpc.finalize_photo_inspection': { error: null },
    ...overrides,
  }
}

function authedRequest(body: unknown = { inspectionId: INSPECTION_ID }) {
  return makeRequest({ headers: { authorization: 'Bearer jwt' }, body })
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  state.db = makeFakeDb(baseRoutes())
  vi.stubEnv('SUPABASE_URL', 'https://db.example')
  vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
  vi.stubEnv('VISION_WORKER_URL', 'https://worker.example/')
  vi.stubEnv('VISION_WORKER_SECRET', 'worker-secret')
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('входные проверки', () => {
  it('чужой метод — 405', async () => {
    const captured = makeFakeResponse()
    await check(makeRequest({ method: 'GET' }), captured.res)
    expect(captured.statusCode).toBe(405)
  })

  it('без токена — 401', async () => {
    const captured = makeFakeResponse()
    await check(makeRequest({ body: { inspectionId: INSPECTION_ID } }), captured.res)
    expect(captured.statusCode).toBe(401)
  })

  it('без inspectionId — 422', async () => {
    const captured = makeFakeResponse()
    await check(authedRequest({}), captured.res)
    expect(captured.statusCode).toBe(422)
    expect(captured.body).toEqual({ reason: 'no_inspection_id' })
  })

  it('чужая проверка — 404, поиск идёт по паре id + user_id', async () => {
    state.db = makeFakeDb(baseRoutes({ 'photo_inspections.select': { data: null, error: null } }))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.statusCode).toBe(404)
    const [lookup] = state.db.callsFor('photo_inspections.select')
    expect(lookup.filters).toContainEqual({ method: 'eq', column: 'user_id', value: UID })
  })

  it('повторный запуск завершённой проверки — 409', async () => {
    state.db = makeFakeDb(baseRoutes({
      'photo_inspections.select': { data: { ...INSPECTION, status: 'done' }, error: null },
    }))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.statusCode).toBe(409)
    expect(captured.body).toEqual({ reason: 'status_done' })
  })

  it('чужой префикс в путях — 422, ссылки не подписываются', async () => {
    state.db = makeFakeDb(baseRoutes({
      'photo_assets.select': {
        data: [{ idx: 0, storage_path: 'someone-else/x/0.jpg', kind: 'photo', face_name: 'front' }],
        error: null,
      },
    }))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.statusCode).toBe(422)
    expect(captured.body).toEqual({ reason: 'bad_paths' })
    expect(state.db.callsFor('storage.packaging-photos.createSignedUrls')).toHaveLength(0)
  })

  it('нет ни одного кадра — 422', async () => {
    state.db = makeFakeDb(baseRoutes({ 'photo_assets.select': { data: [], error: null } }))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.statusCode).toBe(422)
  })

  it('подпись ссылок не удалась — 500, статус в running не уходит', async () => {
    state.db = makeFakeDb(baseRoutes({
      'storage.packaging-photos.createSignedUrls': { data: null, error: { message: 'нет объекта' } },
    }))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.statusCode).toBe(500)
    expect(captured.body).toEqual({ reason: 'sign_failed' })
    expect(state.db.callsFor('photo_inspections.update')).toHaveLength(0)
  })
})

describe('воркер не подключён (до Волны 3)', () => {
  it('нет VISION_WORKER_URL — 503, проверка не помечается running', async () => {
    vi.stubEnv('VISION_WORKER_URL', '')
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.statusCode).toBe(503)
    expect(captured.body).toEqual({ reason: 'worker_not_configured' })
    expect(state.db.callsFor('photo_inspections.update')).toHaveLength(0)
    expect(state.db.callsFor('rpc.finalize_photo_inspection')).toHaveLength(0)
  })

  it('нет VISION_WORKER_SECRET — 503', async () => {
    vi.stubEnv('VISION_WORKER_SECRET', '')
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.statusCode).toBe(503)
    expect(captured.body).toEqual({ reason: 'worker_not_configured' })
  })
})

describe('отказы воркера', () => {
  it('таймаут — финал failed/worker_timeout, квота возвратная', async () => {
    const err = new Error('timed out')
    err.name = 'TimeoutError'
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(err))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.statusCode).toBe(200)
    expect(captured.body).toEqual({ status: 'failed', reason: 'worker_timeout' })
    const [fin] = state.db.callsFor('rpc.finalize_photo_inspection')
    expect(fin.args).toMatchObject({
      p_inspection_id: INSPECTION_ID, p_outcome: 'failed', p_reason: 'worker_timeout',
    })
    expect(REFUNDABLE_REASONS.has('worker_timeout')).toBe(true)
  })

  it('сеть не дошла — worker_unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.body).toEqual({ status: 'failed', reason: 'worker_unreachable' })
  })

  it('409 от воркера — ruleset_drift', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(409, { reason: 'ruleset_drift' })))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.body).toEqual({ status: 'failed', reason: 'ruleset_drift' })
    const [fin] = state.db.callsFor('rpc.finalize_photo_inspection')
    expect(fin.args).toMatchObject({ p_reason: 'ruleset_drift' })
  })

  it('422 no_text_layer — отказ по данным, в возвратный список не входит', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(422, { reason: 'no_text_layer' })))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.body).toEqual({ status: 'failed', reason: 'no_text_layer' })
    expect(REFUNDABLE_REASONS.has('no_text_layer')).toBe(false)
  })

  it('424 asset_fetch_failed прокидывается как есть', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(424, { reason: 'asset_fetch_failed' })))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.body).toEqual({ status: 'failed', reason: 'asset_fetch_failed' })
  })

  it('401 от воркера (секрет разъехался) — машинный код без тела', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('unauthorized', { status: 401 })))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.body).toEqual({ status: 'failed', reason: 'worker_error' })
  })
})

describe('успешный прогон', () => {
  it('запрос к воркеру собран по контракту InspectRequest', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, WORKER_RESULT))
    vi.stubGlobal('fetch', fetchMock)
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('https://worker.example/internal/inspect')
    expect((init.headers as Record<string, string>)['X-Worker-Secret']).toBe('worker-secret')
    expect(JSON.parse(init.body as string)).toEqual({
      inspection_id: INSPECTION_ID,
      product: 'tobacco',
      level: 'consumer',
      markets: ['UZ'],
      evaluated_at: INSPECTION.created_at,
      ruleset_sha256: SHA,
      kind: 'photo',
      asset_urls: ['https://storage.example/0', 'https://storage.example/1'],
      faces: ['front', 'back'],
      prior_facts: null,
      reuse_facts: false,
    })
  })

  it('проверка помечается running с пульсом и попыткой', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, WORKER_RESULT)))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    const [run] = state.db.callsFor('photo_inspections.update')
    expect(run.payload).toMatchObject({ status: 'running', attempts: 1 })
    expect(run.payload).toHaveProperty('heartbeat_at')
    // строка забирается условно — только пока она ещё queued
    expect(run.filters).toContainEqual({ method: 'eq', column: 'status', value: 'queued' })
  })

  it('строку уже забрал параллельный запрос — 409, второго прогона нет', async () => {
    state.db = makeFakeDb(baseRoutes({ 'photo_inspections.update': { data: [], error: null } }))
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.statusCode).toBe(409)
    expect(captured.body).toEqual({ reason: 'already_running' })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(state.db.callsFor('rpc.finalize_photo_inspection')).toHaveLength(0)
  })

  it('кроп уезжает в evidence-crops, base64 в базу не попадает', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, WORKER_RESULT)))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)

    const uploads = state.db.callsFor('storage.evidence-crops.upload')
    expect(uploads).toHaveLength(1)
    expect((uploads[0].args as { path: string }).path).toBe(`${UID}/${INSPECTION_ID}/0.jpg`)

    const [fin] = state.db.callsFor('rpc.finalize_photo_inspection')
    const payload = (fin.args as { p_payload: { findings: Array<Record<string, unknown>> } }).p_payload
    expect(payload.findings[0].evidence_crop_path).toBe(`${UID}/${INSPECTION_ID}/0.jpg`)
    expect(payload.findings[0]).not.toHaveProperty('evidence_crop_b64')
    expect(JSON.stringify(payload)).not.toContain('evidence_crop_b64')
  })

  it('кроп не залился — находка остаётся, путь не проставляется', async () => {
    state.db = makeFakeDb(baseRoutes({
      'storage.evidence-crops.upload': { error: { message: 'квота бакета' } },
    }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, WORKER_RESULT)))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.statusCode).toBe(200)
    const [fin] = state.db.callsFor('rpc.finalize_photo_inspection')
    const payload = (fin.args as { p_payload: { findings: Array<Record<string, unknown>> } }).p_payload
    expect(payload.findings[0].evidence_crop_path).toBeUndefined()
    expect(payload.findings).toHaveLength(2)
  })

  it('финал done одной транзакцией, ответ 200', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, WORKER_RESULT)))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.statusCode).toBe(200)
    expect(captured.body).toEqual({ status: 'done', inspectionId: INSPECTION_ID })
    const finals = state.db.callsFor('rpc.finalize_photo_inspection')
    expect(finals).toHaveLength(1)
    // p_reason у RPC необязателен: «причины нет» = ключа нет
    expect(finals[0].args).toMatchObject({ p_outcome: 'done' })
    expect((finals[0].args as { p_reason?: string }).p_reason).toBeUndefined()
  })

  it('финализация упала — 500', async () => {
    state.db = makeFakeDb(baseRoutes({
      'rpc.finalize_photo_inspection': { error: { message: 'inspection_not_found' } },
    }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, WORKER_RESULT)))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.statusCode).toBe(500)
  })

  it('нечитаемое тело ответа воркера — инфраструктурный отказ, квота возвращается', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('не json', { status: 200 })))
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(captured.body).toEqual({ status: 'failed', reason: 'worker_unreachable' })
    expect(REFUNDABLE_REASONS.has('worker_unreachable')).toBe(true)
  })
})

describe('ревизия (досъёмка)', () => {
  const REVISION = { ...INSPECTION, id: 'ins-2', revision: 2 }
  const PARENT = { id: INSPECTION_ID, revision: 1 }
  const PRIOR_FACTS = [{ slot_id: 'brand', payload: { text: 'X' }, source: 'ocr', confidence: 0.9 }]

  it('прежние факты уезжают телом запроса, reuse_facts=true', async () => {
    state.db = makeFakeDb(baseRoutes({
      'photo_inspections.select': [
        { data: REVISION, error: null },
        { data: PARENT, error: null },
      ],
      'photo_facts.select': { data: PRIOR_FACTS, error: null },
    }))
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, WORKER_RESULT))
    vi.stubGlobal('fetch', fetchMock)
    const captured = makeFakeResponse()
    await check(makeRequest({ headers: { authorization: 'Bearer jwt' }, body: { inspectionId: 'ins-2' } }), captured.res)

    // родитель ищется по superseded_by, факты — по его id и его ревизии
    const parentLookup = state.db.callsFor('photo_inspections.select')[1]
    expect(parentLookup.filters).toContainEqual({ method: 'eq', column: 'superseded_by', value: 'ins-2' })
    const [facts] = state.db.callsFor('photo_facts.select')
    expect(facts.filters).toContainEqual({ method: 'eq', column: 'inspection_id', value: INSPECTION_ID })
    expect(facts.filters).toContainEqual({ method: 'eq', column: 'revision', value: 1 })

    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)
    expect(body.prior_facts).toEqual(PRIOR_FACTS)
    expect(body.reuse_facts).toBe(true)
  })

  it('родитель не найден — прогон идёт без прежних фактов', async () => {
    state.db = makeFakeDb(baseRoutes({
      'photo_inspections.select': [
        { data: REVISION, error: null },
        { data: null, error: null },
      ],
    }))
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, WORKER_RESULT))
    vi.stubGlobal('fetch', fetchMock)
    const captured = makeFakeResponse()
    await check(makeRequest({ headers: { authorization: 'Bearer jwt' }, body: { inspectionId: 'ins-2' } }), captured.res)
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)
    expect(body.prior_facts).toBeNull()
    expect(state.db.callsFor('photo_facts.select')).toHaveLength(0)
  })
})

describe('макет PDF', () => {
  it('подписывается в packaging-artwork, faces не передаются', async () => {
    state.db = makeFakeDb(baseRoutes({
      'photo_inspections.select': { data: { ...INSPECTION, source_kind: 'master_pdf' }, error: null },
      'photo_assets.select': {
        data: [{ idx: 0, storage_path: `${UID}/${INSPECTION_ID}/art.pdf`, kind: 'master_pdf', face_name: 'unknown' }],
        error: null,
      },
      'storage.packaging-artwork.createSignedUrls': {
        data: [{ signedUrl: 'https://storage.example/pdf', path: 'x', error: null }],
        error: null,
      },
    }))
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, WORKER_RESULT))
    vi.stubGlobal('fetch', fetchMock)
    const captured = makeFakeResponse()
    await check(authedRequest(), captured.res)
    expect(state.db.callsFor('storage.packaging-artwork.createSignedUrls')).toHaveLength(1)
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)
    expect(body.kind).toBe('master_pdf')
    expect(body.faces).toBeNull()
  })
})
