// Тонкий клиент Telegram Bot API для api/telegram/webhook.ts.
// TELEGRAM_BOT_TOKEN — только в process.env на сервере (вне src/), в
// клиентский бандл не попадает.

const TELEGRAM_API = 'https://api.telegram.org'

function botToken(): string {
  const token = process.env.TELEGRAM_BOT_TOKEN
  if (!token) throw new Error('missing TELEGRAM_BOT_TOKEN')
  return token
}

/** Общий POST-вызов метода Bot API; сбой логируем, но не бросаем — ответ
 * админу дороже ретрая (тот же принцип, что и в notify_admin_telegram). */
async function callTelegram(method: string, payload: Record<string, unknown>): Promise<void> {
  const res = await fetch(`${TELEGRAM_API}/bot${botToken()}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    console.error(`telegram webhook: ${method} failed`, res.status, body)
  }
}

/** Всплывающая подсказка на нажатую кнопку — без неё Telegram крутит "часики" у клиента. */
export function answerCallbackQuery(
  callbackQueryId: string,
  text: string,
  showAlert = false,
): Promise<void> {
  return callTelegram('answerCallbackQuery', {
    callback_query_id: callbackQueryId,
    text,
    show_alert: showAlert,
  })
}

/** Дописывает строку-статус к исходному сообщению и снимает инлайн-кнопки
 * (второе нажатие после этого ничего не пришлёт — идемпотентность закрыта
 * и на уровне UI, не только в обработчике). */
export function editMessageText(
  chatId: number | string,
  messageId: number,
  text: string,
): Promise<void> {
  return callTelegram('editMessageText', {
    chat_id: chatId,
    message_id: messageId,
    text,
    reply_markup: { inline_keyboard: [] },
  })
}
