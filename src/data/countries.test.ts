import { describe, expect, it } from 'vitest'

import { COUNTRIES, parseCountryParam } from './countries'

// Первый юнит-тест фронта (этап 1 плана фотоконтроля: скрипт `npm run test`
// обязан гонять настоящий тест, а не проходить на пустом наборе).
describe('parseCountryParam', () => {
  it('валидный код страны возвращается как есть', () => {
    expect(parseCountryParam('KZ')).toBe('KZ')
    expect(parseCountryParam('AE')).toBe('AE')
  })

  it('пустое значение фолбэчит на UZ', () => {
    expect(parseCountryParam(null)).toBe('UZ')
    expect(parseCountryParam('')).toBe('UZ')
  })

  it('невалидный код фолбэчит на UZ, без исключений', () => {
    expect(parseCountryParam('RU')).toBe('UZ')
    expect(parseCountryParam('uz')).toBe('UZ') // регистр важен: в URL — верхний
    expect(parseCountryParam('<script>')).toBe('UZ')
  })

  it('каждый код из COUNTRIES проходит разбор без фолбэка', () => {
    for (const code of COUNTRIES) {
      expect(parseCountryParam(code)).toBe(code)
    }
  })
})
