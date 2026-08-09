// Vercel Serverless Function (Node runtime): вебхук Telegram-бота.
// Владелец жмёт «✅ Одобрить»/«❌ Отклонить» под уведомлением о заявке
// (кнопки шлёт notify_new_request(), supabase/migrations/
// 20260817120000_access_by_request.sql) — Telegram присылает сюда
// callback_query, мы читаем/меняем заявку и, при апруве, приглашаем
// человека письмом.
//
// SUPABASE_SERVICE_ROLE_KEY и TELEGRAM_BOT_TOKEN читаются только из
// process.env на сервере: файл лежит вне src/, Vite его не собирает и в
// клиентский бандл не попадает (тот же приём, что и в api/calendar/[token].ts).
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import { answerCallbackQuery, editMessageText } from '../_lib/telegram.js'
import type { Database } from '../../src/lib/database.types.js'

type AdminClient = SupabaseClient<Database>

/** Куда ведёт ссылка из письма-приглашения — там пользователь задаёт пароль (CConfirmEmailPage). */
const INVITE_REDIRECT_TO = 'https://inspectorx.uz/auth/confirm'

const CALLBACK_RE = /^sr:(approve|reject):([0-9a-f-]{36})$/

interface TelegramCallbackQuery {
  id: string
  data?: string
  message?: {
    message_id: number
    text?: string
    chat: { id: number | string }
  }
}

interface TelegramUpdate {
  callback_query?: TelegramCallbackQuery
}

function sendJson(res: VercelResponse, status: number, body: unknown): void {
  res.status(status).json(body)
}

/** SUPABASE_URL — серверная переменная, VITE_SUPABASE_URL — запасной вариант
 * (значение публичное, секрета в нём нет), как в api/calendar и api/vision. */
function adminClient(): AdminClient | null {
  const url = process.env.SUPABASE_URL ?? process.env.VITE_SUPABASE_URL
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY
  if (!url || !key) return null
  return createClient<Database>(url, key, { auth: { persistSession: false } })
}

/** Тот же приём, что и mapAuthError в CAuthPage.tsx: у admin-API нет отдельного
 * машинного кода на «email уже занят», отличаем по тексту ошибки. */
function isAlreadyRegistered(message: string): boolean {
  const m = message.toLowerCase()
  return m.includes('already registered') || m.includes('already been registered') || m.includes('already exists')
}

/**
 * Approve: пригласить письмом (или, если юзер уже есть, найти его id),
 * включить profiles.is_subscribed, закрыть заявку.
 * Возвращает текст для editMessageText.
 */
async function approve(db: AdminClient, requestId: string, email: string): Promise<string> {
  const invite = await db.auth.admin.inviteUserByEmail(email, { redirectTo: INVITE_REDIRECT_TO })
  let userId = invite.data.user?.id

  if (invite.error) {
    if (!isAlreadyRegistered(invite.error.message)) {
      console.error('telegram webhook: inviteUserByEmail failed', invite.error)
      throw new Error('invite_failed')
    }
    // Юзер уже зарегистрирован — не роняем апрув, ищем его id, чтобы
    // всё равно включить подписку (см. миграцию, find_user_id_by_email).
    const { data: foundId, error: lookupError } = await db.rpc('find_user_id_by_email', {
      p_email: email,
    })
    if (lookupError || !foundId) {
      console.error('telegram webhook: find_user_id_by_email failed', lookupError)
      throw new Error('user_lookup_failed')
    }
    userId = foundId
  }

  if (!userId) {
    console.error('telegram webhook: приглашение прошло без user_id')
    throw new Error('invite_no_user')
  }

  const { error: profileError } = await db
    .from('profiles')
    .update({ is_subscribed: true })
    .eq('id', userId)
  if (profileError) {
    console.error('telegram webhook: profiles update failed', profileError)
    throw new Error('profile_update_failed')
  }

  const { data: claimed, error: claimError } = await db
    .from('subscription_requests')
    .update({ status: 'activated', handled_at: new Date().toISOString() })
    .eq('id', requestId)
    .in('status', ['new', 'contacted'])
    .select('id')
    .maybeSingle()
  if (claimError) {
    console.error('telegram webhook: subscription_requests update failed', claimError)
    throw new Error('request_update_failed')
  }
  if (!claimed) return 'ALREADY_HANDLED'

  return '✅ Одобрено'
}

async function reject(db: AdminClient, requestId: string): Promise<string> {
  const { data: claimed, error } = await db
    .from('subscription_requests')
    .update({ status: 'rejected', handled_at: new Date().toISOString() })
    .eq('id', requestId)
    .in('status', ['new', 'contacted'])
    .select('id')
    .maybeSingle()
  if (error) {
    console.error('telegram webhook: subscription_requests reject failed', error)
    throw new Error('request_update_failed')
  }
  if (!claimed) return 'ALREADY_HANDLED'
  return '❌ Отклонено'
}

export default async function handler(req: VercelRequest, res: VercelResponse): Promise<void> {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST')
    sendJson(res, 405, { ok: false })
    return
  }

  const webhookSecret = process.env.TELEGRAM_WEBHOOK_SECRET
  const incomingSecret = req.headers['x-telegram-bot-api-secret-token']
  if (!webhookSecret || incomingSecret !== webhookSecret) {
    sendJson(res, 401, { ok: false })
    return
  }

  // Telegram ретраит апдейт, если не получит 200 — дальше всегда отвечаем
  // 200, а реальный результат уходит юзеру через answerCallbackQuery.
  const update = req.body as TelegramUpdate | undefined
  const cq = update?.callback_query
  if (!cq?.data || !cq.message) {
    sendJson(res, 200, { ok: true })
    return
  }

  const adminChatId = process.env.TELEGRAM_ADMIN_CHAT_ID
  if (!adminChatId || String(cq.message.chat.id) !== adminChatId) {
    // Чужой чат — тихо игнорируем и не отвечаем на кнопку (её там нет и не будет).
    sendJson(res, 200, { ok: true })
    return
  }

  const match = CALLBACK_RE.exec(cq.data)
  if (!match) {
    await answerCallbackQuery(cq.id, 'Неизвестная команда')
    sendJson(res, 200, { ok: true })
    return
  }
  const [, action, requestId] = match

  const db = adminClient()
  if (!db) {
    console.error('telegram webhook: missing SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY env vars')
    await answerCallbackQuery(cq.id, 'Ошибка конфигурации сервера', true)
    sendJson(res, 200, { ok: true })
    return
  }

  const { data: request, error: fetchError } = await db
    .from('subscription_requests')
    .select('id, email, status')
    .eq('id', requestId)
    .maybeSingle()
  if (fetchError) {
    console.error('telegram webhook: subscription_requests lookup failed', fetchError)
    await answerCallbackQuery(cq.id, 'Ошибка сервера', true)
    sendJson(res, 200, { ok: true })
    return
  }
  if (!request) {
    await answerCallbackQuery(cq.id, 'Заявка не найдена', true)
    sendJson(res, 200, { ok: true })
    return
  }
  if (request.status === 'activated' || request.status === 'rejected') {
    await answerCallbackQuery(cq.id, 'Уже обработано')
    sendJson(res, 200, { ok: true })
    return
  }

  if (action === 'approve' && !request.email) {
    await answerCallbackQuery(cq.id, 'В заявке нет email — не могу отправить приглашение', true)
    sendJson(res, 200, { ok: true })
    return
  }

  let statusLine: string
  try {
    statusLine =
      action === 'approve' ? await approve(db, requestId, request.email!) : await reject(db, requestId)
  } catch (err) {
    console.error('telegram webhook: обработка кнопки упала', err)
    await answerCallbackQuery(cq.id, 'Не получилось — смотрите логи сервера', true)
    sendJson(res, 200, { ok: true })
    return
  }

  if (statusLine === 'ALREADY_HANDLED') {
    await answerCallbackQuery(cq.id, 'Уже обработано')
    sendJson(res, 200, { ok: true })
    return
  }

  const originalText = cq.message.text ?? ''
  await Promise.all([
    answerCallbackQuery(cq.id, statusLine),
    editMessageText(cq.message.chat.id, cq.message.message_id, `${originalText}\n\n${statusLine}`),
  ])
  sendJson(res, 200, { ok: true })
}
