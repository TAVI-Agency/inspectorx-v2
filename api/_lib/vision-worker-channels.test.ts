// Каналы воркер → витрина: прогресс прогона и отпечаток набора правил.
// Оба закрыты общим секретом X-Worker-Secret, в базу пишет только сервер.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeFakeDb, makeFakeResponse, makeRequest } from './vision-test-doubles.js'

const state = vi.hoisted(() => ({ db: null as unknown as ReturnType<typeof makeFakeDb> }))

vi.mock('@supabase/supabase-js', () => ({ createClient: () => state.db }))

const { default: progress } = await import('../vision/progress.js')
const { default: ruleset } = await import('../vision/ruleset.js')

const SECRET = 'worker-secret'
const SHA = 'a'.repeat(64)

beforeEach(() => {
  state.db = makeFakeDb()
  vi.stubEnv('SUPABASE_URL', 'https://db.example')
  vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
  vi.stubEnv('VISION_WORKER_SECRET', SECRET)
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('POST /api/vision/progress', () => {
  const authed = { 'x-worker-secret': SECRET }

  it('чужой метод — 405', async () => {
    const captured = makeFakeResponse()
    await progress(makeRequest({ method: 'GET', headers: authed }), captured.res)
    expect(captured.statusCode).toBe(405)
  })

  it('без секрета — 401 и ни одной записи в базу', async () => {
    const captured = makeFakeResponse()
    await progress(
      makeRequest({ body: { inspection_id: 'i-1', stage: 'read' } }),
      captured.res,
    )
    expect(captured.statusCode).toBe(401)
    expect(state.db.calls).toHaveLength(0)
  })

  it('чужой секрет — 401', async () => {
    const captured = makeFakeResponse()
    await progress(
      makeRequest({ headers: { 'x-worker-secret': 'wrong' }, body: { inspection_id: 'i-1', stage: 'read' } }),
      captured.res,
    )
    expect(captured.statusCode).toBe(401)
  })

  it('неизвестная стадия — 422, база не трогается', async () => {
    const captured = makeFakeResponse()
    await progress(
      makeRequest({ headers: authed, body: { inspection_id: 'i-1', stage: 'самодеятельность' } }),
      captured.res,
    )
    expect(captured.statusCode).toBe(422)
    expect(captured.body).toEqual({ reason: 'bad_body' })
    expect(state.db.calls).toHaveLength(0)
  })

  it('пустое тело — 422', async () => {
    const captured = makeFakeResponse()
    await progress(makeRequest({ headers: authed }), captured.res)
    expect(captured.statusCode).toBe(422)
  })

  it('событие ложится в photo_inspection_events, пульс обновляется', async () => {
    const captured = makeFakeResponse()
    await progress(
      makeRequest({
        headers: authed,
        body: { inspection_id: 'i-1', stage: 'judge', detail: { shard: 2 } },
      }),
      captured.res,
    )
    expect(captured.statusCode).toBe(200)
    const [insert] = state.db.callsFor('photo_inspection_events.insert')
    expect(insert.payload).toEqual({
      inspection_id: 'i-1', stage: 'judge', detail: { shard: 2 },
    })
    const [beat] = state.db.callsFor('photo_inspections.update')
    expect(beat.filters).toContainEqual({ method: 'eq', column: 'id', value: 'i-1' })
    expect(beat.payload).toHaveProperty('heartbeat_at')
  })

  it('detail необязателен — по умолчанию пустой объект', async () => {
    const captured = makeFakeResponse()
    await progress(
      makeRequest({ headers: authed, body: { inspection_id: 'i-1', stage: 'done' } }),
      captured.res,
    )
    expect(captured.statusCode).toBe(200)
    const [insert] = state.db.callsFor('photo_inspection_events.insert')
    expect(insert.payload).toMatchObject({ detail: {} })
  })

  it('ошибка вставки — 500, пульс не ставится', async () => {
    state.db = makeFakeDb({
      'photo_inspection_events.insert': { error: { message: 'нет такой проверки' } },
    })
    const captured = makeFakeResponse()
    await progress(
      makeRequest({ headers: authed, body: { inspection_id: 'i-1', stage: 'read' } }),
      captured.res,
    )
    expect(captured.statusCode).toBe(500)
    expect(state.db.callsFor('photo_inspections.update')).toHaveLength(0)
  })
})

describe('POST /api/vision/ruleset', () => {
  const authed = { 'x-worker-secret': SECRET }

  it('чужой метод — 405, без секрета — 401', async () => {
    const a = makeFakeResponse()
    await ruleset(makeRequest({ method: 'GET', headers: authed }), a.res)
    expect(a.statusCode).toBe(405)
    const b = makeFakeResponse()
    await ruleset(makeRequest({ body: { sha256: SHA, version: '1' } }), b.res)
    expect(b.statusCode).toBe(401)
  })

  it('отпечаток не длины 64 — 422', async () => {
    const captured = makeFakeResponse()
    await ruleset(
      makeRequest({ headers: authed, body: { sha256: 'коротко', version: '1.0' } }),
      captured.res,
    )
    expect(captured.statusCode).toBe(422)
    expect(captured.body).toEqual({ reason: 'bad_fingerprint' })
    expect(state.db.calls).toHaveLength(0)
  })

  it('без версии — 422', async () => {
    const captured = makeFakeResponse()
    await ruleset(makeRequest({ headers: authed, body: { sha256: SHA } }), captured.res)
    expect(captured.statusCode).toBe(422)
  })

  it('новая версия поднимается, старая теряет is_current', async () => {
    const captured = makeFakeResponse()
    await ruleset(
      makeRequest({
        headers: authed,
        body: {
          sha256: SHA, version: '2026.08.1', built_at: '2026-08-07T00:00:00Z',
          packs: { uz: 12 }, checks_count: 87,
        },
      }),
      captured.res,
    )
    expect(captured.statusCode).toBe(200)
    const [clear] = state.db.callsFor('ruleset_versions.update')
    expect(clear.payload).toEqual({ is_current: false })
    expect(clear.filters).toContainEqual({ method: 'eq', column: 'is_current', value: true })
    expect(clear.filters).toContainEqual({ method: 'neq', column: 'sha256', value: SHA })
    const [up] = state.db.callsFor('ruleset_versions.upsert')
    expect(up.payload).toEqual({
      sha256: SHA, version: '2026.08.1', built_at: '2026-08-07T00:00:00Z',
      packs: { uz: 12 }, checks_count: 87, is_current: true,
    })
  })

  it('повторная регистрация того же отпечатка идемпотентна', async () => {
    const captured = makeFakeResponse()
    await ruleset(
      makeRequest({ headers: authed, body: { sha256: SHA, version: '2026.08.1' } }),
      captured.res,
    )
    expect(captured.statusCode).toBe(200)
    // neq по своему же sha не даёт снять флаг с самой себя
    const [clear] = state.db.callsFor('ruleset_versions.update')
    expect(clear.filters).toContainEqual({ method: 'neq', column: 'sha256', value: SHA })
  })

  it('ошибка апсерта — 500', async () => {
    state.db = makeFakeDb({ 'ruleset_versions.upsert': { error: { message: 'конфликт' } } })
    const captured = makeFakeResponse()
    await ruleset(
      makeRequest({ headers: authed, body: { sha256: SHA, version: '1' } }),
      captured.res,
    )
    expect(captured.statusCode).toBe(500)
  })
})
