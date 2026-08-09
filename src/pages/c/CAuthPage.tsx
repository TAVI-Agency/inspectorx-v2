import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { MailCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/app/auth'
import { useSubscriptionRequest } from '@/data/hooks'
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

/** Вход: доступ только по одобренной заявке — самостоятельной регистрации нет. */
function LoginForm() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    const result = await signIn(email.trim(), password)
    setPending(false)
    if (result.error) setError(mapAuthError(result.error))
    else navigate('/products', { replace: true })
  }

  const notConfirmedError = error === ru.auth.errors.notConfirmed

  return (
    <CCard className="c-rise w-full max-w-sm p-7">
      <form onSubmit={submit}>
        <h1 className="font-display text-xl font-medium tracking-tight">{ru.auth.loginTitle}</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
          {ru.auth.loginSubtitle}
        </p>

        <div className="mt-6 space-y-4">
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
              <Link
                to="/forgot-password"
                className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                {ru.auth.forgotPassword}
              </Link>
            </div>
            <Input
              id="cauth-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
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
          {pending ? ru.common.loading : ru.auth.loginCta}
        </Button>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          {ru.auth.inviteOnly.notice} {ru.auth.inviteOnly.noAccess}{' '}
          <Link to="/register" className="underline-offset-2 hover:text-foreground hover:underline">
            {ru.auth.inviteOnly.cta}
          </Link>
        </p>
      </form>
    </CCard>
  )
}

/** Экран после отправки заявки на доступ */
function ApplicationSentCard() {
  return (
    <CCard className="c-rise w-full max-w-sm p-7 text-center">
      <MailCheck aria-hidden className="mx-auto size-8 text-positive" />
      <h1 className="font-display mt-4 text-xl font-medium tracking-tight">
        {ru.auth.applicationSentTitle}
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
        {ru.auth.applicationSentText}
      </p>
      <Button variant="outline" className="mt-5" nativeButton={false} render={<Link to="/catalog" />}>
        {ru.pricing.thanksCta}
      </Button>
    </CCard>
  )
}

/**
 * /register — раньше самостоятельная регистрация, теперь заявка на доступ:
 * владелец апрувит в Telegram (api/telegram/webhook.ts), после апрува
 * приходит письмо-приглашение (CConfirmEmailPage, type=invite). Пароля здесь
 * больше нет — его задают по ссылке из письма.
 */
function ApplicationForm() {
  const request = useSubscriptionRequest()
  const [fullName, setFullName] = useState('')
  const [company, setCompany] = useState('')
  const [contact, setContact] = useState('')
  const [email, setEmail] = useState('')
  const [errors, setErrors] = useState<{ name?: string; contact?: string; email?: string }>({})

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const next: typeof errors = {}
    if (!fullName.trim()) next.name = ru.pricing.validation.nameRequired
    if (!contact.trim()) next.contact = ru.pricing.validation.contactRequired
    if (!email.trim()) next.email = ru.pricing.validation.emailRequired
    setErrors(next)
    if (Object.keys(next).length > 0) return
    request.mutate({
      fullName: fullName.trim(),
      contact: contact.trim(),
      email: email.trim(),
      company: company.trim() || undefined,
    })
  }

  if (request.isSuccess) return <ApplicationSentCard />

  return (
    <CCard className="c-rise w-full max-w-sm p-7">
      <form onSubmit={submit} noValidate>
        <h1 className="font-display text-xl font-medium tracking-tight">{ru.auth.registerTitle}</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
          {ru.auth.applicationSubtitle}
        </p>

        <div className="mt-6 space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="creq-name">{ru.auth.fullName}</Label>
            <Input
              id="creq-name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder={ru.auth.fullNamePlaceholder}
              autoComplete="name"
              aria-invalid={Boolean(errors.name)}
            />
            {errors.name && <p className="text-xs text-destructive">{errors.name}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="creq-company">{ru.pricing.companyLabel}</Label>
            <Input
              id="creq-company"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder={ru.pricing.companyPlaceholder}
              autoComplete="organization"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="creq-contact">{ru.pricing.contactLabel}</Label>
            <Input
              id="creq-contact"
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              placeholder={ru.pricing.contactPlaceholder}
              autoComplete="tel"
              aria-invalid={Boolean(errors.contact)}
            />
            {errors.contact && <p className="text-xs text-destructive">{errors.contact}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="creq-email">{ru.pricing.emailLabel}</Label>
            <Input
              id="creq-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={ru.pricing.emailPlaceholder}
              autoComplete="email"
              aria-invalid={Boolean(errors.email)}
            />
            {errors.email && <p className="text-xs text-destructive">{errors.email}</p>}
          </div>
        </div>

        {request.isError && <p className="mt-3 text-sm text-destructive">{ru.auth.errors.generic}</p>}

        <Button type="submit" className="mt-6 w-full" disabled={request.isPending}>
          {request.isPending ? ru.common.sending : ru.pricing.submit}
        </Button>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          <Link to="/login" className="underline-offset-2 hover:text-foreground hover:underline">
            {ru.auth.switchToLogin}
          </Link>
        </p>
      </form>
    </CCard>
  )
}

/** Вход/заявка на доступ дизайна C: тихая центрированная карточка */
export function CAuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { session, loading } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (!loading && session) navigate('/products', { replace: true })
  }, [loading, session, navigate])

  return (
    <div className="flex justify-center px-4 py-16 sm:py-24">
      {mode === 'register' ? <ApplicationForm /> : <LoginForm />}
    </div>
  )
}
