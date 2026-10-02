import { describe, expect, it, vi, beforeEach } from 'vitest'

import { analyticsScripts, initObservability } from './observability'

// Мок для @sentry/react на уровне модуля
vi.mock('@sentry/react', () => ({
  init: vi.fn(),
}))

describe('analyticsScripts', () => {
  it('без переменных — пусто', () => {
    expect(analyticsScripts({})).toEqual([])
  })

  it('Plausible по домену', () => {
    const [s] = analyticsScripts({ VITE_PLAUSIBLE_DOMAIN: 'inspectorx.uz' })
    expect(s.src).toContain('plausible.io')
    expect(s.attrs?.['data-domain']).toBe('inspectorx.uz')
  })

  it('Метрика по id', () => {
    const [s] = analyticsScripts({ VITE_YM_ID: '12345' })
    expect(s.inline).toContain("ym(12345, 'init'")
  })

  it('нечисловой VITE_YM_ID — Метрику пропускаем', () => {
    expect(analyticsScripts({ VITE_YM_ID: 'not-a-number' })).toEqual([])
  })

  it('Plausible и Метрика вместе — оба в списке', () => {
    const scripts = analyticsScripts({
      VITE_PLAUSIBLE_DOMAIN: 'inspectorx.uz',
      VITE_YM_ID: '999',
    })
    expect(scripts).toHaveLength(2)
  })

  it('id с пробелами после trim — проходит валидацию', () => {
    const scripts = analyticsScripts({ VITE_YM_ID: '  12345  ' })
    expect(scripts).toHaveLength(1)
    expect(scripts[0]?.inline).toContain("ym(12345, 'init'")
  })

  it('id = "0" — Метрику пропускаем (> 0)', () => {
    expect(analyticsScripts({ VITE_YM_ID: '0' })).toEqual([])
  })

  it('id с пробелом посередине — Метрику пропускаем', () => {
    expect(analyticsScripts({ VITE_YM_ID: '123 45' })).toEqual([])
  })
})

describe('initObservability', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('без переменных — не падает (полный no-op, нет DOM в node-окружении теста)', () => {
    expect(() => initObservability({})).not.toThrow()
  })

  it('без аргумента — тоже не падает', () => {
    expect(() => initObservability()).not.toThrow()
  })

  it('при DSN — динамически импортирует Sentry и вызывает init с правильными параметрами', async () => {
    initObservability({
      VITE_SENTRY_DSN: 'https://x@o.ingest.sentry.io/1',
      MODE: 'production',
    })

    // Даём микрозадаче выполниться (динамический импорт асинхронный)
    await new Promise((r) => setTimeout(r, 0))

    const { init } = await import('@sentry/react')
    expect(init).toHaveBeenCalledOnce()
    expect(init).toHaveBeenCalledWith({
      dsn: 'https://x@o.ingest.sentry.io/1',
      environment: 'production',
      tracesSampleRate: 0.1,
    })
  })

  it('без DSN — Sentry init не вызывается', async () => {
    const { init } = await import('@sentry/react')
    vi.clearAllMocks()

    initObservability({ MODE: 'production' })

    // Даём микрозадаче выполниться (но не должно быть никакой микрозадачи для Sentry)
    await new Promise((r) => setTimeout(r, 0))

    expect(init).not.toHaveBeenCalled()
  })
})
