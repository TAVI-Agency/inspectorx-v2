// Чистая функция сборки .ics (RFC 5545) для персонального фида дедлайнов.
// Живёт в api/_lib, а не в src/lib — этот код исполняется только на
// Vercel-функции (Node), в клиентский Vite-бандл не попадает и не должен.

/** Виды событий ЖЦ требования — соответствуют колонке event_kind view user_deadline_events. */
export type DeadlineEventKind = 'effective_from' | 'transition_until' | 'valid_to'

export interface DeadlineEvent {
  requirementId: string
  eventKind: DeadlineEventKind
  /** Дата события в формате 'YYYY-MM-DD' (без времени — событие на весь день). */
  eventDate: string
  /** Русское название требования (requirement_contents.title, lang='ru'). */
  title: string
}

export interface BuildIcsOptions {
  /** X-WR-CALNAME — имя календаря в клиенте подписчика. */
  calendarName?: string
  /** Базовый URL сайта для ссылки в DESCRIPTION. */
  siteUrl?: string
  /** Фиксированная метка времени для DTSTAMP — только для детерминизма в тестах. */
  now?: Date
}

const SUMMARY_SUFFIX: Record<DeadlineEventKind, string> = {
  effective_from: 'вступает в силу',
  transition_until: 'конец переходного периода',
  valid_to: 'утрата силы',
}

/** Экранирование текстовых полей ICS (RFC 5545 §3.3.11): `\`, `;`, `,`, переносы строк. */
function escapeText(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r\n|\r|\n/g, '\\n')
}

/** 'YYYY-MM-DD' -> 'YYYYMMDD' для DTSTART;VALUE=DATE. */
function formatDate(isoDate: string): string {
  return isoDate.replace(/-/g, '').slice(0, 8)
}

/** UTC-штамп 'YYYYMMDDTHHMMSSZ' для DTSTAMP. */
function formatTimestamp(date: Date): string {
  return date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z')
}

/**
 * Фолдинг длинных строк по RFC 5545 §3.1: физическая строка ICS не должна
 * превышать 75 октетов, перенос — CRLF + один пробел в начале продолжения.
 * Заголовок и SUMMARY/DESCRIPTION у нас короткие, но фолдинг оставлен для
 * корректности на случай длинных названий требований.
 */
function foldLine(line: string): string {
  const limit = 74 // + 1 октет на ведущий пробел продолжения = 75
  if (line.length <= limit) return line
  let result = line.slice(0, limit)
  let rest = line.slice(limit)
  while (rest.length > 0) {
    const chunk = rest.slice(0, limit - 1)
    result += '\r\n ' + chunk
    rest = rest.slice(chunk.length)
  }
  return result
}

/**
 * Собирает VCALENDAR с VEVENT на каждое событие плюс VALARM за 7 дней.
 * events — уже отфильтрованный по юзеру и подписке набор строк view
 * user_deadline_events (см. api/calendar/[token].ts).
 */
export function buildIcs(events: DeadlineEvent[], opts: BuildIcsOptions = {}): string {
  const siteUrl = opts.siteUrl ?? 'https://inspectorx.uz'
  const calendarName = opts.calendarName ?? 'InspectorX — дедлайны'
  const dtstamp = formatTimestamp(opts.now ?? new Date())

  const lines: string[] = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//InspectorX//Calendar Feed//RU',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    `X-WR-CALNAME:${escapeText(calendarName)}`,
  ]

  for (const event of events) {
    const summary = `${event.title} — ${SUMMARY_SUFFIX[event.eventKind]}`
    // UID уникален уже на уровне view (distinct по requirement_id+event_kind
    // на юзера), составной ключ здесь — просто явная привязка формата.
    const uid = `${event.requirementId}-${event.eventKind}@inspectorx.uz`
    lines.push(
      'BEGIN:VEVENT',
      `UID:${uid}`,
      `DTSTAMP:${dtstamp}`,
      `DTSTART;VALUE=DATE:${formatDate(event.eventDate)}`,
      `SUMMARY:${escapeText(summary)}`,
      // Ссылки на карточку товара в view нет (там только requirement_id, без
      // product_id) — ведём на общую ленту изменений сайта. См. task-36-report.md.
      `DESCRIPTION:${escapeText(`Подробности: ${siteUrl}/changes`)}`,
      'BEGIN:VALARM',
      'ACTION:DISPLAY',
      `DESCRIPTION:${escapeText(summary)}`,
      'TRIGGER:-P7D',
      'END:VALARM',
      'END:VEVENT',
    )
  }

  lines.push('END:VCALENDAR')

  return lines.map(foldLine).join('\r\n') + '\r\n'
}
