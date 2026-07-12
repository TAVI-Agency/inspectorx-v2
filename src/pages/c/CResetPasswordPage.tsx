import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CircleAlert, CircleCheck, LoaderCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/app/auth'
import { parseAuthHashError } from '@/lib/auth-url'
import { ru } from '@/i18n/ru'
import { CCard } from './ui'

/** Сколько ждём recovery-сессию из ссылки, прежде чем счесть её недействительной */
const RECOVERY_TIMEOUT_MS = 8000

/**
 * Посадочная страница ссылки «смена пароля» из письма.
 * Ссылка выдаёт recovery-сессию (supabase-js заберёт её из hash) — дальше форма нового пароля.
 */
export function CResetPasswordPage() {
  const { session, updatePassword } = useAuth()
  const navigate = useNavigate()
  const [invalid, setInvalid] = useState(() => parseAuthHashError(window.location.hash) !== null)
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (session || invalid) return
    const timer = window.setTimeout(() => setInvalid(true), RECOVERY_TIMEOUT_MS)
    return () => window.clearTimeout(timer)
  }, [session, invalid])

  useEffect(() => {
    if (!done) return
    const timer = window.setTimeout(() => navigate('/cabinet', { replace: true }), 1800)
    return () => window.clearTimeout(timer)
  }, [done, navigate])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    const result = await updatePassword(password)
    setPending(false)
    if (result.error) {
      setError(
        result.error.toLowerCase().includes('different from the old')
          ? ru.auth.errors.samePassword
          : ru.auth.errors.weakPassword,
      )
    } else {
      setDone(true)
    }
  }

  return (
    <div className="flex justify-center px-4 py-16 sm:py-24">
      <CCard className="c-rise w-full max-w-sm p-7">
        {done ? (
          <div className="text-center">
            <CircleCheck aria-hidden className="mx-auto size-8 text-positive" />
            <h1 className="font-display mt-4 text-xl font-medium tracking-tight">
              {ru.auth.resetDoneTitle}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {ru.auth.resetDoneText}
            </p>
          </div>
        ) : session ? (
          <form onSubmit={submit}>
            <h1 className="font-display text-xl font-medium tracking-tight">
              {ru.auth.resetTitle}
            </h1>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
              {ru.auth.resetText}
            </p>
            <div className="mt-6 space-y-1.5">
              <Label htmlFor="creset-password">{ru.auth.newPassword}</Label>
              <Input
                id="creset-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                minLength={6}
                required
              />
            </div>
            {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
            <Button type="submit" className="mt-6 w-full" disabled={pending}>
              {pending ? ru.common.loading : ru.auth.resetCta}
            </Button>
          </form>
        ) : invalid ? (
          <div className="text-center">
            <CircleAlert aria-hidden className="mx-auto size-8 text-sanction" />
            <h1 className="font-display mt-4 text-xl font-medium tracking-tight">
              {ru.auth.resetLinkInvalidTitle}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {ru.auth.resetLinkInvalidText}
            </p>
            <p className="mt-5 text-sm">
              <Link
                to="/forgot-password"
                className="text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                {ru.auth.forgotTitle}
              </Link>
            </p>
          </div>
        ) : (
          <div className="text-center">
            <LoaderCircle aria-hidden className="mx-auto size-8 animate-spin text-muted-foreground" />
            <h1 className="font-display mt-4 text-xl font-medium tracking-tight">
              {ru.common.loading}
            </h1>
          </div>
        )}
      </CCard>
    </div>
  )
}
