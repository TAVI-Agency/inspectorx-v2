import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CircleCheck, CircleAlert, LoaderCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/app/auth'
import { parseAuthHashError } from '@/lib/auth-url'
import { ru } from '@/i18n/ru'
import { CCard } from './ui'

/** Сколько ждём, пока supabase-js заберёт токены из ссылки, прежде чем сдаться */
const CONFIRM_TIMEOUT_MS = 8000

/**
 * Посадочная страница ссылки «подтвердите email» из письма.
 * Токены из hash обрабатывает supabase-js — здесь только показываем статус.
 */
export function CConfirmEmailPage() {
  const { session, resendConfirmation } = useAuth()
  const navigate = useNavigate()
  const [failed, setFailed] = useState(() => parseAuthHashError(window.location.hash) !== null)
  const [email, setEmail] = useState('')
  const [resent, setResent] = useState(false)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (session || failed) return
    const timer = window.setTimeout(() => setFailed(true), CONFIRM_TIMEOUT_MS)
    return () => window.clearTimeout(timer)
  }, [session, failed])

  useEffect(() => {
    if (!session) return
    const timer = window.setTimeout(() => navigate('/cabinet', { replace: true }), 1800)
    return () => window.clearTimeout(timer)
  }, [session, navigate])

  async function resend(e: React.FormEvent) {
    e.preventDefault()
    setPending(true)
    await resendConfirmation(email.trim())
    setPending(false)
    setResent(true)
  }

  return (
    <div className="flex justify-center px-4 py-16 sm:py-24">
      <CCard className="c-rise w-full max-w-sm p-7 text-center">
        {session ? (
          <>
            <CircleCheck aria-hidden className="mx-auto size-8 text-positive" />
            <h1 className="font-display mt-4 text-xl font-medium tracking-tight">
              {ru.auth.confirmedTitle}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {ru.auth.confirmedText}
            </p>
            <Button className="mt-6 w-full" onClick={() => navigate('/cabinet')}>
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
