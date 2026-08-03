// Vercel Serverless Function (Node runtime): персональный .ics-фид дедлайнов.
// GET /api/calendar/<token>.ics -> text/calendar.
//
// Поток: token -> calendar_tokens (сервис-роль, мимо RLS) -> user_id ->
// profiles.is_subscribed -> user_deadline_events -> buildIcs.
//
// Ключ SUPABASE_SERVICE_ROLE_KEY читается только из process.env на сервере:
// этот файл лежит вне src/, Vite его не собирает и в клиентский бандл
// не попадает (проверено сборкой — см. task-36-report.md).
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { createClient } from '@supabase/supabase-js'
import { buildIcs, type DeadlineEvent, type DeadlineEventKind } from '../_lib/ics.js'
// Только типы (стираются при компиляции) — переиспользуем сгенерированную
// схему из src/lib, не тащим туда рантайм-код и не связываем api/ с Vite.
import type { Database } from '../../src/lib/database.types.js'

const DEADLINE_EVENT_KINDS: readonly DeadlineEventKind[] = [
  'effective_from',
  'transition_until',
  'valid_to',
]

function isDeadlineEventKind(value: string): value is DeadlineEventKind {
  return (DEADLINE_EVENT_KINDS as readonly string[]).includes(value)
}

function sendText(res: VercelResponse, status: number, text: string): void {
  res.status(status).setHeader('Content-Type', 'text/plain; charset=utf-8').send(text)
}

export default async function handler(req: VercelRequest, res: VercelResponse): Promise<void> {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET')
    sendText(res, 405, 'Метод не поддерживается')
    return
  }

  const rawToken = req.query.token
  const tokenParam = Array.isArray(rawToken) ? rawToken[0] : rawToken
  // URL вида /api/calendar/<token>.ics — весь сегмент под [token] приходит
  // вместе с расширением, отрезаем его перед поиском в БД.
  const token = tokenParam?.replace(/\.ics$/i, '')

  if (!token) {
    sendText(res, 404, 'Токен не найден')
    return
  }

  // SUPABASE_URL — отдельная серверная переменная (см. task-36-report.md);
  // VITE_SUPABASE_URL как запасной вариант, если в Vercel настроена только
  // клиентская — значение публичное (URL проекта), секрета в нём нет.
  const supabaseUrl = process.env.SUPABASE_URL ?? process.env.VITE_SUPABASE_URL
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY

  if (!supabaseUrl || !serviceKey) {
    console.error('calendar feed: missing SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY env vars')
    sendText(res, 500, 'Ошибка конфигурации сервера')
    return
  }

  const supabase = createClient<Database>(supabaseUrl, serviceKey, {
    auth: { persistSession: false },
  })

  const { data: tokenRow, error: tokenError } = await supabase
    .from('calendar_tokens')
    .select('user_id')
    .eq('token', token)
    .maybeSingle()

  if (tokenError) {
    console.error('calendar feed: calendar_tokens lookup failed', tokenError)
    sendText(res, 500, 'Ошибка сервера')
    return
  }

  if (!tokenRow) {
    sendText(res, 404, 'Токен не найден')
    return
  }

  const { data: profile, error: profileError } = await supabase
    .from('profiles')
    .select('is_subscribed')
    .eq('id', tokenRow.user_id)
    .maybeSingle()

  if (profileError) {
    console.error('calendar feed: profiles lookup failed', profileError)
    sendText(res, 500, 'Ошибка сервера')
    return
  }

  if (!profile?.is_subscribed) {
    sendText(res, 403, 'Доступно по подписке')
    return
  }

  const { data: rows, error: eventsError } = await supabase
    .from('user_deadline_events')
    .select('requirement_id, event_kind, event_date, title')
    .eq('user_id', tokenRow.user_id)

  if (eventsError) {
    console.error('calendar feed: user_deadline_events lookup failed', eventsError)
    sendText(res, 500, 'Ошибка сервера')
    return
  }

  const events: DeadlineEvent[] = (rows ?? []).flatMap((row) => {
    if (!row.requirement_id || !row.event_kind || !row.event_date || !row.title) return []
    if (!isDeadlineEventKind(row.event_kind)) return []
    return [
      {
        requirementId: row.requirement_id,
        eventKind: row.event_kind,
        eventDate: row.event_date,
        title: row.title,
      },
    ]
  })

  const ics = buildIcs(events)

  res
    .status(200)
    .setHeader('Content-Type', 'text/calendar; charset=utf-8')
    .setHeader('Content-Disposition', 'inline; filename="inspectorx-deadlines.ics"')
    .setHeader('Cache-Control', 'private, max-age=300')
    .send(ics)
}
