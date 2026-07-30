import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Scale } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useMyLawyerProfile } from '@/data/hooks'
import { useAuth } from '@/app/auth'
import { ru } from '@/i18n/ru'
import { CCard } from './ui'

/** Раздел юриста: содержимое видит только верифицированный эксперт */
export function CLawyerGuard({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth()
  const { data: profile, isLoading } = useMyLawyerProfile()
  if (loading || (session && isLoading)) return null
  if (profile?.status === 'verified') return <>{children}</>
  return (
    <div className="mx-auto max-w-6xl px-4 py-24 sm:px-8">
      <CCard className="mx-auto max-w-md p-8 text-center">
        <span className="mx-auto grid size-12 place-items-center rounded-full border border-primary/40 bg-accent text-accent-foreground">
          <Scale className="size-5" />
        </span>
        <h1 className="mt-4 text-xl font-semibold tracking-tight">
          {ru.cabinet.lawyer.becomeTitle}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {ru.cabinet.lawyer.becomeText}
        </p>
        {session ? (
          <Button className="mt-5" nativeButton={false} render={<Link to="/settings" />}>
            {ru.cabinet.lawyer.becomeCta}
          </Button>
        ) : (
          <Button className="mt-5" nativeButton={false} render={<Link to="/login" />}>
            {ru.common.signIn}
          </Button>
        )}
      </CCard>
    </div>
  )
}
