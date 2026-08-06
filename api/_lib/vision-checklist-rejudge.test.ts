// Чек-лист (публичный тизер с кэшем) и пересуд правленого факта.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeFakeDb, makeFakeResponse, makeRequest, type FakeRoutes } from './vision-test-doubles.js'

const state = vi.hoisted(() => ({ db: null as unknown as ReturnType<typeof makeFakeDb> }))

vi.mock('@supabase/supabase-js', () => ({ createClient: () => state.db }))

const { default: checklist } = await import('../vision/checklist.js')
const { default: rejudge } = await import('../vision/rejudge.js')

const UID = 'u-1'
const PRODUCT_ID = '3f2b8c1d-0000-4000-8000-000000000001'
const INSPECTION_ID = 'ins-1'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubEnv('SUPABASE_URL', 'https://db.example')
  vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
  vi.stubEnv('VISION_WORKER_URL', 'https://worker.example')
  vi.stubEnv('VISION_WORKER_SECRET', 'worker-secret')
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('GET /api/vision/checklist', () => {
  const CHECKLIST = {
    title: 'Табачная продукция, потребительская упаковка',
    groups: [{ key: 'marking', items: [] }],
    counters: { checkable: 20, partial: 3, notCheckable: 5, noGold: 1 },
  }

  beforeEach(() => {
    state.db = makeFakeDb({
      'rpc.photo_profile_for_product': { data: 'tobacco', error: null },
    })
  })

  it('чужой метод — 405', async () => {
    const captured = makeFakeResponse()
    await checklist(makeRequest({ method: 'POST', query: { product: PRODUCT_ID } }), captured.res)
    expect(captured.statusCode).toBe(405)
  })

  it('без товара — 422', async () => {
    const captured = makeFakeResponse()
    await checklist(makeRequest({ method: 'GET', query: {} }), captured.res)
    expect(captured.statusCode).toBe(422)
    expect(captured.body).toEqual({ reason: 'no_product' })
  })

  it('товар не uuid — 422, база не дёргается', async () => {
    const captured = makeFakeResponse()
    await checklist(makeRequest({ method: 'GET', query: { product: 'сигареты' } }), captured.res)
    expect(captured.statusCode).toBe(422)
    expect(captured.body).toEqual({ reason: 'bad_product' })
    expect(state.db.calls).toHaveLength(0)
  })

  it('неизвестный уровень упаковки — 422', async () => {
    const captured = makeFakeResponse()
    await checklist(
      makeRequest({ method: 'GET', query: { product: PRODUCT_ID, level: 'палета' } }),
      captured.res,
    )
    expect(captured.statusCode).toBe(422)
    expect(captured.body).toEqual({ reason: 'bad_level' })
  })

  it('товар вне профилей движка — 404 no_checklist, воркер не дёргается', async () => {
    state.db = makeFakeDb({ 'rpc.photo_profile_for_product': { data: null, error: null } })
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const captured = makeFakeResponse()
    await checklist(makeRequest({ method: 'GET', query: { product: PRODUCT_ID } }), captured.res)
    expect(captured.statusCode).toBe(404)
    expect(captured.body).toEqual({ reason: 'no_checklist' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('воркер не подключён — 503', async () => {
    vi.stubEnv('VISION_WORKER_URL', '')
    const captured = makeFakeResponse()
    await checklist(makeRequest({ method: 'GET', query: { product: PRODUCT_ID } }), captured.res)
    expect(captured.statusCode).toBe(503)
    expect(captured.body).toEqual({ reason: 'worker_not_configured' })
  })

  it('воркер лежит — 502', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')))
    const captured = makeFakeResponse()
    await checklist(makeRequest({ method: 'GET', query: { product: PRODUCT_ID } }), captured.res)
    expect(captured.statusCode).toBe(502)
    expect(captured.body).toEqual({ reason: 'worker_unavailable' })
  })

  it('воркер ответил ошибкой — 502', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(500, { reason: 'boom' })))
    const captured = makeFakeResponse()
    await checklist(makeRequest({ method: 'GET', query: { product: PRODUCT_ID } }), captured.res)
    expect(captured.statusCode).toBe(502)
  })

  it('профиль резолвится по товару, тело прокидывается с кэшем на 5 минут', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, CHECKLIST))
    vi.stubGlobal('fetch', fetchMock)
    const captured = makeFakeResponse()
    await checklist(
      makeRequest({ method: 'GET', query: { product: PRODUCT_ID, level: 'transport' } }),
      captured.res,
    )
    expect(captured.statusCode).toBe(200)
    expect(captured.body).toEqual({ profile: 'tobacco', ...CHECKLIST })
    expect(captured.headers['cache-control']).toBe('public, s-maxage=300, stale-while-revalidate=60')
    expect(fetchMock.mock.calls[0][0])
      .toBe('https://worker.example/api/checklist?product=tobacco&level=transport')
    const [rpc] = state.db.callsFor('rpc.photo_profile_for_product')
    expect(rpc.args).toEqual({ p_product_id: PRODUCT_ID })
  })

  it('уровень по умолчанию — потребительская упаковка', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, CHECKLIST))
    vi.stubGlobal('fetch', fetchMock)
    const captured = makeFakeResponse()
    await checklist(makeRequest({ method: 'GET', query: { product: PRODUCT_ID } }), captured.res)
    expect(fetchMock.mock.calls[0][0]).toContain('level=consumer')
  })
})

describe('POST /api/vision/rejudge', () => {
  const DONE = {
    id: INSPECTION_ID, user_id: UID, product_key: 'tobacco',
    packaging_level: 'consumer', markets: ['UZ'], status: 'done', revision: 1,
  }
  const FACTS = [
    { slot_id: 'brand', payload: { text: 'X' }, source: 'ocr', confidence: 0.7, asset_idx: 1, bbox: [1, 2, 3, 4] },
    { slot_id: 'nicotine', payload: { mg: 0.5 }, source: 'ocr', confidence: 0.9, asset_idx: 0, bbox: null },
  ]
  // RejudgeResponse — только вердикт: паспорт фактов воркер не возвращает
  const VERDICT = { overall: 'pass', decided: 14, checked: 14, findings: [], not_checkable: [] }
  const OVERRIDES = [{ slotId: 'brand', payload: { text: 'Y' }, note: 'на пачке читается Y' }]

  function routes(overrides: FakeRoutes = {}): FakeRoutes {
    return {
      'auth.getUser': { data: { id: UID }, error: null },
      'photo_inspections.select': { data: DONE, error: null },
      'photo_fact_overrides.insert': { error: null },
      'photo_facts.select': { data: FACTS, error: null },
      'rpc.create_photo_revision': { data: 'ins-2', error: null },
      ...overrides,
    }
  }

  function authed(body: unknown = { inspectionId: INSPECTION_ID, overrides: OVERRIDES }) {
    return makeRequest({ headers: { authorization: 'Bearer jwt' }, body })
  }

  beforeEach(() => {
    state.db = makeFakeDb(routes())
  })

  it('чужой метод — 405', async () => {
    const captured = makeFakeResponse()
    await rejudge(makeRequest({ method: 'GET' }), captured.res)
    expect(captured.statusCode).toBe(405)
  })

  it('без токена — 401', async () => {
    const captured = makeFakeResponse()
    await rejudge(makeRequest({ body: { inspectionId: INSPECTION_ID, overrides: OVERRIDES } }), captured.res)
    expect(captured.statusCode).toBe(401)
  })

  it('пустой список правок — 422', async () => {
    const captured = makeFakeResponse()
    await rejudge(authed({ inspectionId: INSPECTION_ID, overrides: [] }), captured.res)
    expect(captured.statusCode).toBe(422)
    expect(captured.body).toEqual({ reason: 'bad_body' })
  })

  it('правка без slotId — 422', async () => {
    const captured = makeFakeResponse()
    await rejudge(
      authed({ inspectionId: INSPECTION_ID, overrides: [{ payload: { text: 'Y' } }] }),
      captured.res,
    )
    expect(captured.statusCode).toBe(422)
    expect(captured.body).toEqual({ reason: 'bad_override' })
  })

  it('чужая или незавершённая проверка — 404', async () => {
    state.db = makeFakeDb(routes({ 'photo_inspections.select': { data: null, error: null } }))
    const captured = makeFakeResponse()
    await rejudge(authed(), captured.res)
    expect(captured.statusCode).toBe(404)
    const [lookup] = state.db.callsFor('photo_inspections.select')
    expect(lookup.filters).toContainEqual({ method: 'eq', column: 'user_id', value: UID })
    expect(lookup.filters).toContainEqual({ method: 'eq', column: 'status', value: 'done' })
  })

  it('правки ложатся в photo_fact_overrides с автором', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, VERDICT)))
    const captured = makeFakeResponse()
    await rejudge(authed(), captured.res)
    const [ins] = state.db.callsFor('photo_fact_overrides.insert')
    expect(ins.payload).toEqual([{
      inspection_id: INSPECTION_ID, slot_id: 'brand', payload: { text: 'Y' },
      author_user_id: UID, note: 'на пачке читается Y',
    }])
  })

  it('правки не записались — 500, пересуда нет', async () => {
    state.db = makeFakeDb(routes({ 'photo_fact_overrides.insert': { error: { message: 'нет проверки' } } }))
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const captured = makeFakeResponse()
    await rejudge(authed(), captured.res)
    expect(captured.statusCode).toBe(500)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('пересуд идёт по фактам последней ревизии из базы', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, VERDICT))
    vi.stubGlobal('fetch', fetchMock)
    const captured = makeFakeResponse()
    await rejudge(authed(), captured.res)

    const [facts] = state.db.callsFor('photo_facts.select')
    expect(facts.filters).toContainEqual({ method: 'eq', column: 'inspection_id', value: INSPECTION_ID })
    expect(facts.filters).toContainEqual({ method: 'eq', column: 'revision', value: 1 })

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('https://worker.example/internal/rejudge')
    expect((init.headers as Record<string, string>)['X-Worker-Secret']).toBe('worker-secret')
    expect(JSON.parse(init.body as string)).toEqual({
      checklist_key: { product: 'tobacco', level: 'consumer', markets: ['UZ'] },
      facts: FACTS,
      overrides: [{ slot_id: 'brand', payload: { text: 'Y' }, note: 'на пачке читается Y' }],
    })
  })

  it('воркер лежит — 502', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')))
    const captured = makeFakeResponse()
    await rejudge(authed(), captured.res)
    expect(captured.statusCode).toBe(502)
    expect(captured.body).toEqual({ reason: 'worker_unavailable' })
  })

  it('новая ревизия одной транзакцией; моделей не звали', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, VERDICT)))
    const captured = makeFakeResponse()
    await rejudge(authed(), captured.res)
    expect(captured.statusCode).toBe(200)
    expect(captured.body).toEqual({ inspectionId: 'ins-2' })
    const [rpc] = state.db.callsFor('rpc.create_photo_revision')
    expect(rpc.args).toMatchObject({ p_parent_id: INSPECTION_ID })
    expect((rpc.args as { p_payload: Record<string, unknown> }).p_payload)
      .toMatchObject({ overall: 'pass', decided: 14, checked: 14 })
    expect(state.db.calls.filter((c) => c.table === 'photo_model_calls')).toHaveLength(0)
  })

  it('новая ревизия уносит паспорт фактов с применёнными правками', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, VERDICT)))
    const captured = makeFakeResponse()
    await rejudge(authed(), captured.res)

    // create_photo_revision заполняет photo_facts из p_payload->'facts';
    // воркер facts не возвращает — их собирает функция
    const [rpc] = state.db.callsFor('rpc.create_photo_revision')
    const { facts } = (rpc.args as { p_payload: { facts: Array<Record<string, unknown>> } }).p_payload
    expect(facts).toEqual([
      // правленый слот: значение человека, источник 'human', привязка к кадру цела
      { slot_id: 'brand', payload: { text: 'Y' }, source: 'human', confidence: 1, asset_idx: 1, bbox: [1, 2, 3, 4] },
      // нетронутый слот доезжает как был
      { slot_id: 'nicotine', payload: { mg: 0.5 }, source: 'ocr', confidence: 0.9, asset_idx: 0, bbox: null },
    ])
  })

  it('правка нового слота добавляется, а не теряется', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, VERDICT)))
    const captured = makeFakeResponse()
    await rejudge(authed({
      inspectionId: INSPECTION_ID,
      overrides: [{ slotId: 'expiry', payload: { date: '2027-01-01' } }],
    }), captured.res)

    const [rpc] = state.db.callsFor('rpc.create_photo_revision')
    const { facts } = (rpc.args as { p_payload: { facts: Array<Record<string, unknown>> } }).p_payload
    expect(facts).toHaveLength(3)
    expect(facts[2]).toEqual({
      slot_id: 'expiry', payload: { date: '2027-01-01' }, source: 'human',
      confidence: 1, asset_idx: null, bbox: null,
    })
  })

  it('пустой паспорт родителя — в ревизию уезжают только правки', async () => {
    state.db = makeFakeDb(routes({ 'photo_facts.select': { data: [], error: null } }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, VERDICT)))
    const captured = makeFakeResponse()
    await rejudge(authed(), captured.res)
    const [rpc] = state.db.callsFor('rpc.create_photo_revision')
    const { facts } = (rpc.args as { p_payload: { facts: Array<Record<string, unknown>> } }).p_payload
    expect(facts).toEqual([
      { slot_id: 'brand', payload: { text: 'Y' }, source: 'human', confidence: 1, asset_idx: null, bbox: null },
    ])
  })

  it('потолок ревизий — 409, а не пятисотка', async () => {
    state.db = makeFakeDb(routes({
      'rpc.create_photo_revision': { data: null, error: { message: 'revision_limit' } },
    }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, VERDICT)))
    const captured = makeFakeResponse()
    await rejudge(authed(), captured.res)
    expect(captured.statusCode).toBe(409)
    expect(captured.body).toEqual({ reason: 'revision_limit' })
  })

  it('прочая ошибка ревизии — 500', async () => {
    state.db = makeFakeDb(routes({
      'rpc.create_photo_revision': { data: null, error: { message: 'что-то ещё' } },
    }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, VERDICT)))
    const captured = makeFakeResponse()
    await rejudge(authed(), captured.res)
    expect(captured.statusCode).toBe(500)
  })

  it('воркер не подключён — 503, правки не пишутся', async () => {
    vi.stubEnv('VISION_WORKER_URL', '')
    const captured = makeFakeResponse()
    await rejudge(authed(), captured.res)
    expect(captured.statusCode).toBe(503)
    expect(state.db.callsFor('photo_fact_overrides.insert')).toHaveLength(0)
  })
})
