import { describe, expect, it } from 'vitest'

import { reportCounters } from '@/data'
import {
  decidedByLabel,
  faceLabel,
  isRefundableReason,
  readerCoverageSummary,
  severityLabel,
  stageLabel,
  splitFindings,
} from './report-utils'

describe('splitFindings', () => {
  const f = (status: string, confidence_class = 'machine_read', decided_by = 'pdf_text') =>
    ({ status, confidence_class, decided_by }) as never
  it('четыре списка §7: нарушения / досъёмка-человек / граница метода / без эталона', () => {
    const lists = splitFindings([f('fail'), f('pass'), f('unreadable')],
      [{ class: 'метод' }, { class: 'нет эталона' }] as never)
    expect(lists.violations).toHaveLength(1)
    expect(lists.needsHuman).toHaveLength(1)
    expect(lists.notCheckable).toHaveLength(1)
    expect(lists.noGold).toHaveLength(1)
  })

  it('список 2 — объединение unreadable и needs_human, а не только нечитаемых', () => {
    // прочитано машиной, но без уверенности — тоже «нужен человек»
    const lists = splitFindings(
      [f('unreadable'), f('pass', 'needs_human'), f('pass'), f('fail', 'needs_human')],
      [] as never,
    )
    expect(lists.needsHuman).toHaveLength(3)
  })

  it('плитка «Требует человека» и список 2 дают одно число', () => {
    const findings = [f('unreadable'), f('pass', 'needs_human'), f('pass'), f('fail')]
    const lists = splitFindings(findings, [] as never)
    const counters = reportCounters({
      inspection: { decided: 4, checked: 4 },
      findings,
      notCheckable: [],
      assets: [],
    } as never)
    expect(counters.needsHuman).toBe(lists.needsHuman.length)
  })
})

it('decided_by показывается словами, не кодом', () => {
  expect(decidedByLabel('pdf_text')).toBe('прочитано в макете')
  expect(decidedByLabel('zbar')).toBe('декодирован штрих-код')
  expect(decidedByLabel('ocr')).toBe('распознано OCR')
  expect(decidedByLabel('human')).toBe('подтверждено человеком')
})

it('стадии ожидания именованные', () => {
  expect(stageLabel('prepare', 'master_pdf')).toBe('разбираем макет')
  expect(stageLabel('read', 'photo')).toBe('читаем этикетку')
  expect(stageLabel('judge', 'photo')).toBe('сверяем с требованиями')
})

it('незнакомая стадия — сырой код, не пустая строка', () => {
  expect(stageLabel('unknown_stage', 'photo')).toBe('unknown_stage')
})

it('severityLabel — словами, незнакомый код — как есть', () => {
  expect(severityLabel('critical')).toBe('критично')
  expect(severityLabel('major')).toBe('существенно')
  expect(severityLabel('minor')).toBe('незначительно')
  expect(severityLabel('info')).toBe('к сведению')
  expect(severityLabel('mystery')).toBe('mystery')
})

it('faceLabel понимает оба словаря кодов граней', () => {
  expect(faceLabel('front_panel')).toBe('лицевая')
  expect(faceLabel('back')).toBe('оборотная')
  expect(faceLabel('unknown_face')).toBe('unknown_face')
})

it('isRefundableReason — закрытый список из RPC finalize_photo_inspection', () => {
  expect(isRefundableReason('worker_timeout')).toBe(true)
  expect(isRefundableReason('no_text_layer')).toBe(false)
})

describe('readerCoverageSummary', () => {
  it('master_pdf: массив покрытых страниц даёт их число', () => {
    expect(readerCoverageSummary('master_pdf', ['p1', 'p2', 'p3'], 1)).toEqual({
      kind: 'master_pdf',
      pages: 3,
    })
  })
  it('photo: объект {have, of} читается напрямую', () => {
    expect(readerCoverageSummary('photo', { have: 3, of: 4 }, 4)).toEqual({
      kind: 'photo',
      have: 3,
      of: 4,
    })
  })
  it('непонятная форма без кадров — null, не выдуманное число', () => {
    expect(readerCoverageSummary('photo', { weird: true }, 0)).toBeNull()
  })
})
