import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeFakeDb, makeFakeResponse, makeRequest } from './vision-test-doubles.js'

const state = vi.hoisted(() => ({ db: null as unknown as ReturnType<typeof makeFakeDb> }))

vi.mock('@supabase/supabase-js', () => ({
  createClient: () => state.db,
}))

import {
  adminClient, assertOwnPrefix, bucketFor, getUserFromRequest, REFUNDABLE_REASONS,
  requireWorkerSecret, VisionConfigError, withVisionGuards, workerSecret, workerUrl,
} from './vision.js'

describe('assertOwnPrefix', () => {
  const uid = '3f2b8c1d-0000-4000-8000-000000000001'
  it('свой префикс проходит', () => {
    expect(assertOwnPrefix([`${uid}/abc/0.jpg`], uid)).toBe(true)
  })
  it('чужой префикс и обход через ../ отклоняются', () => {
    expect(assertOwnPrefix(['other/abc/0.jpg'], uid)).toBe(false)
    expect(assertOwnPrefix([`${uid}/../other/0.jpg`], uid)).toBe(false)
    expect(assertOwnPrefix([], uid)).toBe(false)
  })
})

describe('bucketFor', () => {
  it('kind → бакет', () => {
    expect(bucketFor('master_pdf')).toBe('packaging-artwork')
    expect(bucketFor('photo')).toBe('packaging-photos')
  })
})

it('список возвратных причин закрыт и совпадает с миграцией', () => {
  expect([...REFUNDABLE_REASONS].sort()).toEqual([
    'dispatch_lost', 'ocr_unavailable', 'ruleset_drift',
    'vlm_unavailable', 'worker_timeout', 'worker_unreachable',
  ])
})

describe('конфигурация окружения', () => {
  beforeEach(() => {
    state.db = makeFakeDb()
    vi.stubEnv('SUPABASE_URL', '')
    vi.stubEnv('VITE_SUPABASE_URL', '')
    vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', '')
    vi.stubEnv('VISION_WORKER_URL', '')
    vi.stubEnv('VISION_WORKER_SECRET', '')
  })
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('adminClient без ключей — VisionConfigError server_misconfigured', () => {
    expect(() => adminClient()).toThrow(VisionConfigError)
    try {
      adminClient()
    } catch (err) {
      expect((err as VisionConfigError).reason).toBe('server_misconfigured')
    }
  })

  it('workerUrl/workerSecret до Волны 3 — worker_not_configured', () => {
    expect(() => workerUrl()).toThrow(VisionConfigError)
    expect(() => workerSecret()).toThrow(VisionConfigError)
  })

  it('workerUrl срезает хвостовой слэш', () => {
    vi.stubEnv('VISION_WORKER_URL', 'https://worker.example/')
    expect(workerUrl()).toBe('https://worker.example')
  })
})

describe('withVisionGuards', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('нехватка воркера — 503 с машинным кодом', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const captured = makeFakeResponse()
    await withVisionGuards(async () => {
      throw new VisionConfigError('worker_not_configured', 'missing VISION_WORKER_URL')
    })(makeRequest({}), captured.res)
    expect(captured.statusCode).toBe(503)
    expect(captured.body).toEqual({ reason: 'worker_not_configured' })
  })

  it('нехватка ключей базы — 500 server_misconfigured', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const captured = makeFakeResponse()
    await withVisionGuards(async () => {
      throw new VisionConfigError('server_misconfigured', 'missing SUPABASE_URL')
    })(makeRequest({}), captured.res)
    expect(captured.statusCode).toBe(500)
    expect(captured.body).toEqual({ reason: 'server_misconfigured' })
  })

  it('любая другая ошибка наружу не протекает', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const captured = makeFakeResponse()
    await withVisionGuards(async () => {
      throw new Error('секретный стектрейс')
    })(makeRequest({}), captured.res)
    expect(captured.statusCode).toBe(500)
    expect(captured.body).toEqual({ reason: 'internal' })
    expect(JSON.stringify(captured.body)).not.toContain('секретный')
    expect(spy).toHaveBeenCalled()
  })
})

describe('requireWorkerSecret', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('без секрета в окружении не пропускает никого', () => {
    vi.stubEnv('VISION_WORKER_SECRET', '')
    expect(requireWorkerSecret(makeRequest({ headers: { 'x-worker-secret': '' } }))).toBe(false)
    expect(requireWorkerSecret(makeRequest({ headers: {} }))).toBe(false)
  })

  it('сверяет заголовок с секретом', () => {
    vi.stubEnv('VISION_WORKER_SECRET', 's3cret')
    expect(requireWorkerSecret(makeRequest({ headers: { 'x-worker-secret': 's3cret' } }))).toBe(true)
    expect(requireWorkerSecret(makeRequest({ headers: { 'x-worker-secret': 'nope' } }))).toBe(false)
    expect(requireWorkerSecret(makeRequest({ headers: {} }))).toBe(false)
  })
})

describe('getUserFromRequest', () => {
  beforeEach(() => {
    vi.stubEnv('SUPABASE_URL', 'https://db.example')
    vi.stubEnv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
  })
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('без заголовка Authorization — null, база не дёргается', async () => {
    state.db = makeFakeDb()
    expect(await getUserFromRequest(makeRequest({ headers: {} }))).toBeNull()
    expect(state.db.calls).toHaveLength(0)
  })

  it('схема не Bearer — null', async () => {
    state.db = makeFakeDb()
    expect(await getUserFromRequest(makeRequest({ headers: { authorization: 'Basic xyz' } })))
      .toBeNull()
    expect(state.db.calls).toHaveLength(0)
  })

  it('битый токен — null', async () => {
    state.db = makeFakeDb({ 'auth.getUser': { data: null, error: { message: 'bad jwt' } } })
    expect(await getUserFromRequest(makeRequest({ headers: { authorization: 'Bearer bad' } })))
      .toBeNull()
  })

  it('живой токен — id пользователя', async () => {
    state.db = makeFakeDb({ 'auth.getUser': { data: { id: 'u-1' }, error: null } })
    expect(await getUserFromRequest(makeRequest({ headers: { authorization: 'Bearer ok' } })))
      .toEqual({ id: 'u-1' })
    expect(state.db.calls[0].args).toBe('ok')
  })
})
