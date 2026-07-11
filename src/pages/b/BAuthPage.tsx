import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/app/auth'
import { ru } from '@/i18n/ru'
import { BCard } from './ui'

function mapAuthError(message: string): string {
  const m = message.toLowerCase()
  if (m.includes('invalid login credentials')) return ru.auth.errors.invalid
  if (m.includes('already registered') || m.includes('already exists'))
    return ru.auth.errors.exists
  if (m.includes('not confirmed')) return ru.auth.errors.notConfirmed
  if (m.includes('password')) return ru.auth.errors.weakPassword
  return ru.auth.errors.generic
}

export function BAuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { session, signIn, signUp, loading } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const isRegister = mode === 'register'

  useEffect(() => {
    if (!loading && session) navigate('/b/cabinet', { replace: true })
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
    else navigate('/b/cabinet', { replace: true })
  }

  return (
    <div className="mx-auto flex max-w-7xl justify-center px-4 py-16 sm:px-6 sm:py-24">
      <BCard className="w-full max-w-sm p-7">
        <form onSubmit={submit}>
          <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <span className="text-sm font-bold">iX</span>
          </span>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight">
            {isRegister ? ru.auth.registerTitle : ru.auth.loginTitle}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {isRegister
              ? 'Создайте аккаунт, чтобы собрать портфель товаров.'
              : 'Войдите, чтобы следить за изменениями по товарам.'}
          </p>

          <div className="mt-6 space-y-4">
            {isRegister && (
              <div className="space-y-1.5">
                <Label htmlFor="bauth-name">{ru.auth.fullName}</Label>
                <Input
                  id="bauth-name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder={ru.auth.fullNamePlaceholder}
                  autoComplete="name"
                  required
                />
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="bauth-email">{ru.auth.email}</Label>
              <Input
                id="bauth-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.uz"
                autoComplete="email"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="bauth-password">{ru.auth.password}</Label>
              <Input
                id="bauth-password"
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
              <Link to="/b/login" className="hover:text-foreground hover:underline">
                {ru.auth.switchToLogin}
              </Link>
            ) : (
              <Link to="/b/register" className="hover:text-foreground hover:underline">
                {ru.auth.switchToRegister}
              </Link>
            )}
          </p>
        </form>
      </BCard>
    </div>
  )
}
