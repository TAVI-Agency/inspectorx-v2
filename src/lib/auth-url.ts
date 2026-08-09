/**
 * Ошибки из ссылок в письмах Supabase приходят в hash-фрагменте:
 * /auth/confirm#error=access_denied&error_code=otp_expired&error_description=...
 * Успешные токены из hash забирает сам supabase-js (detectSessionInUrl).
 */
export function parseAuthHashError(hash: string): string | null {
  const params = new URLSearchParams(hash.replace(/^#/, ''))
  return params.get('error_code') ?? params.get('error')
}

/**
 * Тип успешной ссылки из hash: .../#access_token=...&type=invite|signup|recovery...
 * Приглашение (владелец одобрил заявку в Telegram, см. api/telegram/webhook.ts)
 * и обычное подтверждение письма ведут на один роут (/auth/confirm) — по этому
 * значению CConfirmEmailPage решает, показывать форму пароля или нет.
 */
export function parseAuthHashType(hash: string): string | null {
  const params = new URLSearchParams(hash.replace(/^#/, ''))
  return params.get('type')
}
