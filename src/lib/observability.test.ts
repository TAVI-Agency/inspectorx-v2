import { describe, expect, it } from 'vitest'

import { analyticsScripts, initObservability } from './observability'

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
})

describe('initObservability', () => {
  it('без переменных — не падает (полный no-op, нет DOM в node-окружении теста)', () => {
    expect(() => initObservability({})).not.toThrow()
  })

  it('без аргумента — тоже не падает', () => {
    expect(() => initObservability()).not.toThrow()
  })
})
