import { describe, expect, it } from 'vitest'

import {
  buildIdempotencyKey,
  groupRetakeBySurface,
  isPreliminary,
  reportCounters,
  type InspectionBundle,
  type PhotoFindingRow,
  type PhotoInspectionRow,
} from './vision'

describe('buildIdempotencyKey', () => {
  const a = new TextEncoder().encode('file-a').buffer as ArrayBuffer
  const b = new TextEncoder().encode('file-b').buffer as ArrayBuffer
  it('детерминирован и не зависит от порядка файлов', async () => {
    const k1 = await buildIdempotencyKey([a, b], 'consumer', ['UZ'])
    const k2 = await buildIdempotencyKey([b, a], 'consumer', ['UZ'])
    expect(k1).toBe(k2)
    expect(k1).toMatch(/^[0-9a-f]{64}$/)
  })
  it('меняется от уровня и рынков', async () => {
    const k1 = await buildIdempotencyKey([a], 'consumer', ['UZ'])
    const k2 = await buildIdempotencyKey([a], 'transport', ['UZ'])
    const k3 = await buildIdempotencyKey([a], 'consumer', ['UZ', 'EAEU'])
    expect(new Set([k1, k2, k3]).size).toBe(3)
  })
})

describe('groupRetakeBySurface', () => {
  it('группирует по surface и сортирует по числу пунктов', () => {
    const f = (surface: string) => ({ surface, status: 'unreadable' }) as never
    const groups = groupRetakeBySurface([f('back_panel'), f('side_panel'), f('back_panel')])
    expect(groups[0]).toMatchObject({ surface: 'back_panel' })
    expect(groups[0].findings).toHaveLength(2)
    expect(groups[1]).toMatchObject({ surface: 'side_panel' })
    expect(groups[1].findings).toHaveLength(1)
  })

  it('пустой список находок — пустой результат', () => {
    expect(groupRetakeBySurface([])).toEqual([])
  })
})

// Фикстуры строк — только поля, от которых зависит логика; остальные
// required-колонки БД для чистых функций не нужны (`as never`, как и в
// groupRetakeBySurface выше).
function finding(fields: Partial<PhotoFindingRow>): PhotoFindingRow {
  return { status: 'pass', confidence_class: 'machine_read', severity: 'info', ...fields } as never
}

function inspection(fields: Partial<PhotoInspectionRow>): PhotoInspectionRow {
  return { decided: 10, checked: 12, overall: 'pass', signed_by: null, ...fields } as never
}

function bundle(
  insFields: Partial<PhotoInspectionRow>,
  findings: PhotoFindingRow[] = [],
): InspectionBundle {
  return { inspection: inspection(insFields), findings, notCheckable: [], assets: [] }
}

describe('reportCounters', () => {
  it('нарушения и «нужен человек» считаются из findings, decided/checked — из строки проверки', () => {
    const b = bundle({ decided: 14, checked: 14 }, [
      finding({ status: 'fail' }),
      finding({ status: 'fail', confidence_class: 'needs_human' }),
      finding({ status: 'pass' }),
      finding({ status: 'unreadable', confidence_class: 'needs_human' }),
    ])
    expect(reportCounters(b)).toEqual({
      violations: 2,
      decided: 14,
      checked: 14,
      needsHuman: 2,
    })
  })

  it('decided/checked null в строке — читаются как 0', () => {
    const b = bundle({ decided: null, checked: null })
    expect(reportCounters(b)).toEqual({ violations: 0, decided: 0, checked: 0, needsHuman: 0 })
  })
})

describe('isPreliminary', () => {
  it('overall = fail без подписи — предварительный', () => {
    expect(isPreliminary(bundle({ overall: 'fail', signed_by: null }))).toBe(true)
  })

  it('критичная находка без подписи — предварительный, даже если overall не fail', () => {
    const b = bundle({ overall: 'pass', signed_by: null }, [finding({ severity: 'critical' })])
    expect(isPreliminary(b)).toBe(true)
  })

  it('подписанный вердикт — окончателен, даже с fail', () => {
    expect(isPreliminary(bundle({ overall: 'fail', signed_by: 'lawyer-1' }))).toBe(false)
  })

  it('pass без критичных находок и без подписи — окончателен', () => {
    const b = bundle({ overall: 'pass', signed_by: null }, [finding({ severity: 'minor' })])
    expect(isPreliminary(b)).toBe(false)
  })
})
