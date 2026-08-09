import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CircleCheck, CircleAlert, LoaderCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/app/auth'
import { parseAuthHashError, parseAuthHashType } from '@/lib/auth-url'
import { ru } from '@/i18n/ru'
import { CCard } from './ui'

/** Сколько ждём, пока supabase-js заберёт токены из ссылки, прежде чем сдаться */
const CONFIRM_TIMEOUT_MS = 8000

/**
 * Посадочная страница ссылок из писем Supabase — на неё ведут ДВА разных
 * письма: подтверждение почты (type=signup, сессия уже полноценная — просто
 * показываем статус и уводим в приложение) и приглашение после апрува
 * заявки в Telegram (type=invite, api/telegram/webhook.ts →
 * auth.admin.inviteUserByEmail с redirectTo сюда же) — у инвайта пароля ещё
 * нет, поэтому здесь его просят задать (механика та же, что в
 * CResetPasswordPage: supabase.auth.updateUser({ password }) на recovery-сессии
 * из hash). Токены из hash забирает сам supabase-js (detectSessionInUrl).
 */
export function CConfirmEmailPage() {
  const { session, resendConfirmation, updatePassword } = useAuth()
  const navigate = useNavigate()
  const [failed, setFailed] = useState(() => parseAuthHashError(window.location.hash) !== null)
  const [isInvite] = useState(() => parseAuthHashType(window.location.hash) === 'invite')
  const [email, setEmail] = useState('')
  const [resent, setResent] = useState(false)
  const [pending, setPending] = useState(false)

  const [password, setPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordPending, setPasswordPending] = useState(false)
  const [passwordDone, setPasswordDone] = useState(false)

  useEffect(() => {
    if (session || failed) return
    const timer = window.setTimeout(() => setFailed(true), CONFIRM_TIMEOUT_MS)
    return () => window.clearTimeout(timer)
  }, [session, failed])

  // Обычное подтверждение почты — сразу в приложение. Приглашение сначала
  // ждёт пароль (см. submitPassword ниже), редиректит уже passwordDone.
  useEffect(() => {
    if (!session || isInvite) return
    const timer = window.setTimeout(() => navigate('/products', { replace: true }), 1800)
    return () => window.clearTimeout(timer)
  }, [session, isInvite, navigate])

  useEffect(() => {
    if (!passwordDone) return
    const timer = window.setTimeout(() => navigate('/products', { replace: true }), 1800)
    return () => window.clearTimeout(timer)
  }, [passwordDone, navigate])

  async function resend(e: React.FormEvent) {
    e.preventDefault()
    setPending(true)
    await resendConfirmation(email.trim())
    setPending(false)
    setResent(true)
  }

  async function submitPassword(e: React.FormEvent) {
    e.preventDefault()
    setPasswordError(null)
    setPasswordPending(true)
    const result = await updatePassword(password)
    setPasswordPending(false)
    if (result.error) {
      setPasswordError(
        result.error.toLowerCase().includes('different from the old')
          ? ru.auth.errors.samePassword
          : ru.auth.errors.weakPassword,
      )
    } else {
      setPasswordDone(true)
    }
  }

  return (
    <div className="flex justify-center px-4 py-16 sm:py-24">
      <CCard className="c-rise w-full max-w-sm p-7 text-center">
        {session && isInvite && !passwordDone ? (
          <form onSubmit={submitPassword} className="text-left">
            <h1 className="font-display text-xl font-medium tracking-tight">
              {ru.auth.inviteTitle}
            </h1>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
              {ru.auth.inviteText}
            </p>
            <div className="mt-6 space-y-1.5">
              <Label htmlFor="cconfirm-invite-password">{ru.auth.newPassword}</Label>
              <Input
                id="cconfirm-invite-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                minLength={6}
                required
              />
            </div>
            {passwordError && <p className="mt-3 text-sm text-destructive">{passwordError}</p>}
            <Button type="submit" className="mt-6 w-full" disabled={passwordPending}>
              {passwordPending ? ru.common.loading : ru.auth.inviteCta}
            </Button>
          </form>
        ) : session && isInvite && passwordDone ? (
          <>
            <CircleCheck aria-hidden className="mx-auto size-8 text-positive" />
            <h1 className="font-display mt-4 text-xl font-medium tracking-tight">
              {ru.auth.inviteDoneTitle}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {ru.auth.inviteDoneText}
            </p>
          </>
        ) : session ? (
          <>
            <CircleCheck aria-hidden className="mx-auto size-8 text-positive" />
            <h1 className="font-display mt-4 text-xl font-medium tracking-tight">
              {ru.auth.confirmedTitle}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {ru.auth.confirmedText}
            </p>
            <Button className="mt-6 w-full" onClick={() => navigate('/products')}>
              {ru.auth.confirmedCta}
            </Button>
          </>
        ) : failed ? (
          <>
            <CircleAlert aria-hidden className="mx-auto size-8 text-sanction" />
            <h1 className="font-display mt-4 text-xl font-medium tracking-tight">
              {ru.auth.confirmErrorTitle}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {ru.auth.confirmErrorText}
            </p>
            {resent ? (
              <p className="mt-5 text-sm text-positive">{ru.auth.resendDone}</p>
            ) : (
              <form onSubmit={resend} className="mt-5 space-y-3 text-left">
                <div className="space-y-1.5">
                  <Label htmlFor="cconfirm-email">{ru.auth.email}</Label>
                  <Input
                    id="cconfirm-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@company.uz"
                    autoComplete="email"
                    required
                  />
                </div>
                <Button type="submit" className="w-full" disabled={pending}>
                  {pending ? ru.common.loading : ru.auth.resend}
                </Button>
              </form>
            )}
          </>
        ) : (
          <>
            <LoaderCircle aria-hidden className="mx-auto size-8 animate-spin text-muted-foreground" />
            <h1 className="font-display mt-4 text-xl font-medium tracking-tight">
              {ru.auth.confirmingTitle}
            </h1>
          </>
        )}
      </CCard>
    </div>
  )
}
