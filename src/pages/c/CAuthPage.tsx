import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { MailCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/app/auth'
import { ru } from '@/i18n/ru'
import { CCard } from './ui'

function mapAuthError(message: string): string {
  const m = message.toLowerCase()
  if (m.includes('invalid login credentials')) return ru.auth.errors.invalid
  if (m.includes('already registered') || m.includes('already exists'))
    return ru.auth.errors.exists
  if (m.includes('not confirmed')) return ru.auth.errors.notConfirmed
  if (m.includes('password')) return ru.auth.errors.weakPassword
  return ru.auth.errors.generic
}

/** Кнопка «отправить письмо ещё раз» с минутным кулдауном от лимитов SMTP */
export function ResendButton({ email }: { email: string }) {
  const { resendConfirmation } = useAuth()
  const [state, setState] = useState<'idle' | 'pending' | 'sent' | 'cooldown'>('idle')

  async function resend() {
    setState('pending')
    const { error } = await resendConfirmation(email)
    if (error && error.toLowerCase().includes('rate limit')) {
      setState('cooldown')
    } else {
      setState('sent')
    }
    window.setTimeout(() => setState('idle'), 60_000)
  }

  if (state === 'sent')
    return <p className="text-sm text-positive">{ru.auth.resendDone}</p>
  if (state === 'cooldown')
    return <p className="text-sm text-muted-foreground">{ru.auth.resendCooldown}</p>
  return (
    <button
      type="button"
      onClick={resend}
      disabled={state === 'pending'}
      className="text-sm text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-60"
    >
      {state === 'pending' ? ru.common.loading : ru.auth.resend}
    </button>
  )
}

/** Карточка «проверьте почту» после регистрации */
function ConfirmSentCard({ email }: { email: string }) {
  return (
    <CCard className="c-rise w-full max-w-sm p-7 text-center">
      <MailCheck aria-hidden className="mx-auto size-8 text-positive" />
      <h1 className="font-display mt-4 text-xl font-medium tracking-tight">
        {ru.auth.confirmSentTitle}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
        {ru.auth.confirmSentText(email)}
      </p>
      <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
        {ru.auth.confirmSentSpamHint}
      </p>
      <div className="mt-5">
        <ResendButton email={email} />
      </div>
    </CCard>
  )
}

/** Вход/регистрация дизайна C: тихая центрированная карточка */
export function CAuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { session, signIn, signUp, loading } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [confirmSentTo, setConfirmSentTo] = useState<string | null>(null)

  const isRegister = mode === 'register'

  useEffect(() => {
    if (!loading && session) navigate('/products', { replace: true })
  }, [loading, session, navigate])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    if (isRegister) {
      const result = await signUp(email.trim(), password, fullName.trim())
      setPending(false)
      if (result.error) setError(mapAuthError(result.error))
      else if (result.needsConfirmation) setConfirmSentTo(email.trim())
      else navigate('/products', { replace: true })
    } else {
      const result = await signIn(email.trim(), password)
      setPending(false)
      if (result.error) setError(mapAuthError(result.error))
      else navigate('/products', { replace: true })
    }
  }

  const notConfirmedError = error === ru.auth.errors.notConfirmed

  return (
    <div className="flex justify-center px-4 py-16 sm:py-24">
      {confirmSentTo ? (
        <ConfirmSentCard email={confirmSentTo} />
      ) : (
        <CCard className="c-rise w-full max-w-sm p-7">
          <form onSubmit={submit}>
            <h1 className="font-display text-xl font-medium tracking-tight">
              {isRegister ? ru.auth.registerTitle : ru.auth.loginTitle}
            </h1>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
              {isRegister
                ? 'Создайте аккаунт, чтобы собрать портфель товаров.'
                : 'Войдите, чтобы следить за изменениями по товарам.'}
            </p>

            <div className="mt-6 space-y-4">
              {isRegister && (
                <div className="space-y-1.5">
                  <Label htmlFor="cauth-name">{ru.auth.fullName}</Label>
                  <Input
                    id="cauth-name"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder={ru.auth.fullNamePlaceholder}
                    autoComplete="name"
                    required
                  />
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="cauth-email">{ru.auth.email}</Label>
                <Input
                  id="cauth-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.uz"
                  autoComplete="email"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <div className="flex items-baseline justify-between">
                  <Label htmlFor="cauth-password">{ru.auth.password}</Label>
                  {!isRegister && (
                    <Link
                      to="/forgot-password"
                      className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                    >
                      {ru.auth.forgotPassword}
                    </Link>
                  )}
                </div>
                <Input
                  id="cauth-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={isRegister ? 'new-password' : 'current-password'}
                  minLength={6}
                  required
                />
              </div>
            </div>

            {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
            {notConfirmedError && email.trim() && (
              <div className="mt-2">
                <ResendButton email={email.trim()} />
              </div>
            )}

            <Button type="submit" className="mt-6 w-full" disabled={pending}>
              {pending ? ru.common.loading : isRegister ? ru.auth.registerCta : ru.auth.loginCta}
            </Button>

            <p className="mt-4 text-center text-sm text-muted-foreground">
              {isRegister ? (
                <Link to="/login" className="underline-offset-2 hover:text-foreground hover:underline">
                  {ru.auth.switchToLogin}
                </Link>
              ) : (
                <Link to="/register" className="underline-offset-2 hover:text-foreground hover:underline">
                  {ru.auth.switchToRegister}
                </Link>
              )}
            </p>
          </form>
        </CCard>
      )}
    </div>
  )
}
