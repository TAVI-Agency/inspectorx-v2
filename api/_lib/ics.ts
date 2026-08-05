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
 * превышать 75 ОКТЕТОВ — не UTF-16 юнитов и не символов JS-строки. Кириллица
 * в UTF-8 — 2 байта на символ, «—» (em dash) — 3, так что 74-символьная
 * русская строка — это уже ~148 октетов, вдвое больше лимита. Считаем через
 * Buffer.byteLength, режем строго по границам символов (Array.from — код-
 * поинты, переживает суррогатные пары), никогда не разрезая многобайтовый
 * символ пополам. Первая физическая строка — лимит 75 октетов; строки-
 * продолжения — 74 октета на сам текст + 1 октет на ведущий пробел (тоже
 * часть строки при передаче), итого тоже 75.
 */
function foldLine(line: string): string {
  const octetLimit = 75
  if (Buffer.byteLength(line, 'utf8') <= octetLimit) return line

  const physicalLines: string[] = []
  let current = ''
  let currentBytes = 0
  let limit = octetLimit // первая строка — без ведущего пробела

  for (const ch of Array.from(line)) {
    const chBytes = Buffer.byteLength(ch, 'utf8')
    if (currentBytes + chBytes > limit) {
      physicalLines.push(current)
      current = ch
      currentBytes = chBytes
      limit = octetLimit - 1 // все следующие строки — продолжения (минус пробел)
    } else {
      current += ch
      currentBytes += chBytes
    }
  }
  physicalLines.push(current)

  return physicalLines.map((part, i) => (i === 0 ? part : ' ' + part)).join('\r\n')
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
