/**
 * Страно-независимый формат показа: коды классификаторов и суммы санкций.
 * Единственное место, где живёт связка «система кода / единица штрафа → как
 * это читает пользователь» — компоненты и src/data не хардкодят лейблы вроде
 * «ТН ВЭД»/«БРВ» напрямую (Задача 33, чистка УЗ-специфики Блока 4).
 */
import type { CountryCode } from '@/data/countries'

/**
 * Лейблы систем национальных кодов (`catalog.country_codes.system` /
 * `passport.codes[].system`, ADR-0004). Список расширяется по мере
 * подключения новых юрисдикций/справочников — не привязан к одной стране:
 * ТН ВЭД действует во всех странах ЕАЭС, ИКПУ — фискальный код Узбекистана,
 * ОКЭД — код вида деятельности (используется и в УЗ, и в КЗ).
 */
export const CODE_SYSTEM_LABELS: Record<string, string> = {
  tnved: 'ТН ВЭД',
  ikpu: 'ИКПУ',
  oked: 'ОКЭД',
}

/** Лейбл системы кода с фолбэком на сам код системы, если справочник ещё не знает её. */
export function codeSystemLabel(system: string): string {
  return CODE_SYSTEM_LABELS[system] ?? system.toUpperCase()
}

/** Порядок чипов кодов в паспорте — по объявлению CODE_SYSTEM_LABELS, неизвестные системы — в конец. */
export function sortCodesForDisplay<T extends { system: string }>(codes: readonly T[]): T[] {
  const order = Object.keys(CODE_SYSTEM_LABELS)
  return [...codes].sort((a, b) => {
    const ia = order.indexOf(a.system)
    const ib = order.indexOf(b.system)
    if (ia !== ib) return (ia === -1 ? order.length : ia) - (ib === -1 ? order.length : ib)
    return a.system.localeCompare(b.system)
  })
}

/** Штраф/санкция: сумма + единица измерения. Единица — строка ИЗ ДАННЫХ
 *  (БРВ/МРП/AED/…, конвейер пишет её как есть) — формула её выбора не
 *  хардкодится нигде в коде, только шаблон фразы завязан на страну. */
export interface Fine {
  amount: number
  unit: string
}

const AMOUNT_FMT = new Intl.NumberFormat('ru-RU')

/**
 * «до 50 БРВ» (УЗ/КЗ и по умолчанию — единица постфиксом) · «AED 50 000»
 * (ОАЭ — единица (валюта) префиксом, разговорный порядок для дирхама).
 * Никакого switch по стране ради выбора единицы измерения — она уже в `f.unit`,
 * `country` влияет только на порядок слов в шаблоне.
 */
export function formatFine(f: Fine, country: CountryCode): string {
  const amount = AMOUNT_FMT.format(f.amount)
  return country === 'AE' ? `${f.unit} ${amount}` : `до ${amount} ${f.unit}`
}
