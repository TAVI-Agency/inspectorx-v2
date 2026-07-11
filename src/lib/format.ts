const DATE_FMT = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})

const DATE_TIME_FMT = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  return DATE_FMT.format(new Date(iso))
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return ''
  return DATE_TIME_FMT.format(new Date(iso))
}

/** Русские множественные формы: plural(3, 'акт', 'акта', 'актов') */
export function plural(n: number, one: string, few: string, many: string): string {
  const abs = Math.abs(n) % 100
  const d = abs % 10
  if (abs > 10 && abs < 20) return many
  if (d > 1 && d < 5) return few
  if (d === 1) return one
  return many
}

export function pluralize(n: number, one: string, few: string, many: string): string {
  return `${n} ${plural(n, one, few, many)}`
}

/** ТН ВЭД с классификаторными пробелами: 2404110001 → 2404 11 000 1 */
export function formatHsCode(code: string): string {
  const digits = code.replace(/\D/g, '')
  if (digits.length !== 10) return code
  return `${digits.slice(0, 4)} ${digits.slice(4, 6)} ${digits.slice(6, 9)} ${digits.slice(9)}`
}

/** Дней до даты (от сегодня, без учёта времени). Отрицательное — дата прошла. */
export function daysUntil(iso: string): number {
  const target = new Date(iso)
  const today = new Date()
  target.setHours(0, 0, 0, 0)
  today.setHours(0, 0, 0, 0)
  return Math.round((target.getTime() - today.getTime()) / 86_400_000)
}

/** «сегодня 18:05» / «вчера 09:12» / «08.07, 14:00» — для строки телеметрии */
export function formatRelativeTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) return `сегодня ${time}`
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (d.toDateString() === yesterday.toDateString()) return `вчера ${time}`
  return `${d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}, ${time}`
}
