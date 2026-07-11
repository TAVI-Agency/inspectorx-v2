import { Link, NavLink, useLocation } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/app/auth'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { TelemetryLine } from './TelemetryLine'
import { ThemeToggle } from './ThemeToggle'

function navLinkClass({ isActive }: { isActive: boolean }) {
  return cn(
    'rounded-md px-2 py-1 text-sm transition-colors hover:text-foreground',
    isActive ? 'text-foreground' : 'text-muted-foreground',
  )
}

export function SiteHeader() {
  const { session, signOut } = useAuth()
  // На лендинге телеметрия крупно в hero — мобильную полоску шапки не дублируем
  const isLanding = useLocation().pathname === '/'
  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-12 max-w-6xl items-center gap-4 px-4 sm:px-6">
        <Link to="/" className="shrink-0 text-[15px] font-semibold tracking-tight">
          Inspector<span className="text-primary">X</span>
        </Link>
        <TelemetryLine className="hidden min-w-0 flex-1 justify-center md:flex" />
        <nav className="ml-auto flex shrink-0 items-center gap-1 md:ml-0">
          <NavLink to="/pricing" className={navLinkClass}>
            {ru.common.pricing}
          </NavLink>
          <NavLink to="/app" className={navLinkClass}>
            {ru.common.cabinet}
          </NavLink>
          {session ? (
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground"
              onClick={() => void signOut()}
            >
              {ru.common.signOut}
            </Button>
          ) : (
            <NavLink to="/login" className={navLinkClass}>
              {ru.common.signIn}
            </NavLink>
          )}
          <ThemeToggle />
        </nav>
      </div>
      {!isLanding && (
        <div className="border-t border-border/60 px-4 py-1 md:hidden">
          <TelemetryLine />
        </div>
      )}
    </header>
  )
}
