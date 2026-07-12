import { Link, NavLink, useLocation } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { TelemetryLine } from './TelemetryLine'
import { ThemeToggle } from './ThemeToggle'

function navLinkClass({ isActive }: { isActive: boolean }) {
  return cn(
    'shrink-0 rounded-md px-2 py-1 text-sm whitespace-nowrap transition-colors hover:text-foreground',
    isActive ? 'text-foreground' : 'text-muted-foreground',
  )
}

export function SiteHeader() {
  const { session, signOut } = useAuth()
  const { mockSubscriber } = useAppMode()
  // На лендинге телеметрия живёт в hero у поиска — в шапке не дублируем
  const isLanding = useLocation().pathname === '/'
  // «Кабинет» показываем тем, у кого он не упрётся в логин-стену
  const showCabinet = Boolean(session) || mockSubscriber

  return (
    <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-12 max-w-6xl items-center gap-4 px-4 sm:px-6">
        <Link to="/" className="shrink-0 text-[15px] font-semibold tracking-tight">
          Inspector<span className="text-primary">X</span>
        </Link>
        {!isLanding && (
          <TelemetryLine className="hidden min-w-0 flex-1 justify-center md:flex" />
        )}
        <nav className="scrollbar-none ml-auto flex min-w-0 items-center gap-1 overflow-x-auto md:ml-0">
          <NavLink to="/catalog" className={navLinkClass}>
            {ru.common.registry}
          </NavLink>
          <NavLink to="/pricing" className={navLinkClass}>
            {ru.common.pricing}
          </NavLink>
          {showCabinet && (
            <NavLink to="/app" className={navLinkClass}>
              {ru.common.cabinet}
            </NavLink>
          )}
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
        <div className="scrollbar-none overflow-x-auto border-t border-border/60 px-4 py-1 md:hidden">
          <TelemetryLine />
        </div>
      )}
    </header>
  )
}
