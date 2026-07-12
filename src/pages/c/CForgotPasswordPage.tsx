import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MailCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/app/auth'
import { ru } from '@/i18n/ru'
import { CCard } from './ui'

/** Запрос ссылки на смену пароля. Ответ всегда «письмо отправлено» — без утечки, есть ли аккаунт. */
export function CForgotPasswordPage() {
  const { requestPasswordReset } = useAuth()
  const [email, setEmail] = useState('')
  const [pending, setPending] = useState(false)
  const [sentTo, setSentTo] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setPending(true)
    await requestPasswordReset(email.trim())
    setPending(false)
    setSentTo(email.trim())
  }

  return (
    <div className="flex justify-center px-4 py-16 sm:py-24">
      <CCard className="c-rise w-full max-w-sm p-7">
        {sentTo ? (
          <div className="text-center">
            <MailCheck aria-hidden className="mx-auto size-8 text-positive" />
            <h1 className="font-display mt-4 text-xl font-medium tracking-tight">
              {ru.auth.forgotSentTitle}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {ru.auth.forgotSentText(sentTo)}
            </p>
            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
              {ru.auth.confirmSentSpamHint}
            </p>
          </div>
        ) : (
          <form onSubmit={submit}>
            <h1 className="font-display text-xl font-medium tracking-tight">
              {ru.auth.forgotTitle}
            </h1>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
              {ru.auth.forgotText}
            </p>
            <div className="mt-6 space-y-1.5">
              <Label htmlFor="cforgot-email">{ru.auth.email}</Label>
              <Input
                id="cforgot-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.uz"
                autoComplete="email"
                required
              />
            </div>
            <Button type="submit" className="mt-6 w-full" disabled={pending}>
              {pending ? ru.common.loading : ru.auth.forgotCta}
            </Button>
          </form>
        )}
        <p className="mt-4 text-center text-sm text-muted-foreground">
          <Link to="/login" className="underline-offset-2 hover:text-foreground hover:underline">
            {ru.auth.backToLogin}
          </Link>
        </p>
      </CCard>
    </div>
  )
}
