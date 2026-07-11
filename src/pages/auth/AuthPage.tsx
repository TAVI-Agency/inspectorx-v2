import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/app/auth'
import { ru } from '@/i18n/ru'

function mapAuthError(message: string): string {
  const m = message.toLowerCase()
  if (m.includes('invalid login credentials')) return ru.auth.errors.invalid
  if (m.includes('already registered') || m.includes('already exists'))
    return ru.auth.errors.exists
  if (m.includes('not confirmed')) return ru.auth.errors.notConfirmed
  if (m.includes('password')) return ru.auth.errors.weakPassword
  return ru.auth.errors.generic
}

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { session, signIn, signUp, loading } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const isRegister = mode === 'register'

  useEffect(() => {
    if (!loading && session) navigate('/app', { replace: true })
  }, [loading, session, navigate])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    const result = isRegister
      ? await signUp(email.trim(), password, fullName.trim())
      : await signIn(email.trim(), password)
    setPending(false)
    if (result.error) {
      setError(mapAuthError(result.error))
    } else {
      navigate('/app', { replace: true })
    }
  }

  return (
    <div className="mx-auto flex max-w-6xl justify-center px-4 py-16 sm:px-6 sm:py-24">
      <form onSubmit={submit} className="w-full max-w-sm rounded-lg border bg-paper p-6">
        <p className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
          {ru.common.appName}
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">
          {isRegister ? ru.auth.registerTitle : ru.auth.loginTitle}
        </h1>

        <div className="mt-6 space-y-4">
          {isRegister && (
            <div className="space-y-1.5">
              <Label htmlFor="auth-name">{ru.auth.fullName}</Label>
              <Input
                id="auth-name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder={ru.auth.fullNamePlaceholder}
                autoComplete="name"
                required
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="auth-email">{ru.auth.email}</Label>
            <Input
              id="auth-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.uz"
              autoComplete="email"
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="auth-password">{ru.auth.password}</Label>
            <Input
              id="auth-password"
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

        <Button type="submit" className="mt-5 w-full" disabled={pending}>
          {pending
            ? ru.common.loading
            : isRegister
              ? ru.auth.registerCta
              : ru.auth.loginCta}
        </Button>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          {isRegister ? (
            <Link to="/login" className="hover:text-foreground hover:underline">
              {ru.auth.switchToLogin}
            </Link>
          ) : (
            <Link to="/register" className="hover:text-foreground hover:underline">
              {ru.auth.switchToRegister}
            </Link>
          )}
        </p>
      </form>
    </div>
  )
}
