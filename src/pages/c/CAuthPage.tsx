import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
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

/** Вход/регистрация дизайна C: тихая центрированная карточка */
export function CAuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { session, signIn, signUp, loading } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const isRegister = mode === 'register'

  useEffect(() => {
    if (!loading && session) navigate('/c/cabinet', { replace: true })
  }, [loading, session, navigate])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    const result = isRegister
      ? await signUp(email.trim(), password, fullName.trim())
      : await signIn(email.trim(), password)
    setPending(false)
    if (result.error) setError(mapAuthError(result.error))
    else navigate('/c/cabinet', { replace: true })
  }

  return (
    <div className="flex justify-center px-4 py-16 sm:py-24">
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
              <Label htmlFor="cauth-password">{ru.auth.password}</Label>
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

          <Button type="submit" className="mt-6 w-full" disabled={pending}>
            {pending ? ru.common.loading : isRegister ? ru.auth.registerCta : ru.auth.loginCta}
          </Button>

          <p className="mt-4 text-center text-sm text-muted-foreground">
            {isRegister ? (
              <Link to="/c/login" className="underline-offset-2 hover:text-foreground hover:underline">
                {ru.auth.switchToLogin}
              </Link>
            ) : (
              <Link to="/c/register" className="underline-offset-2 hover:text-foreground hover:underline">
                {ru.auth.switchToRegister}
              </Link>
            )}
          </p>
        </form>
      </CCard>
    </div>
  )
}
