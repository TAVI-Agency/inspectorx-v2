import { useEffect } from 'react'
import { Link, NavLink, Outlet, ScrollRestoration } from 'react-router-dom'
import {
  BadgeCheck,
  Compass,
  LayoutDashboard,
  LogIn,
  LogOut,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ThemeToggle } from '@/app/layout/ThemeToggle'
import { DevMenu } from '@/app/layout/DevMenu'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { useTelemetry } from '@/data/hooks'
import { formatRelativeTime, plural } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'

/**
 * Оболочка дизайна C: постоянный левый рейл-кокпит на десктопе,
 * верхняя панель + нижние табы на мобильном. Токены изолированы в .theme-c.
 */
export function CLayout() {
  // Порталы (диалоги, поповеры) рендерятся в body — вне поддерева .theme-c.
  // Пока открыт дизайн C, тема живёт на body, чтобы порталы не теряли токены.
  useEffect(() => {
    document.body.classList.add('theme-c')
    return () => document.body.classList.remove('theme-c')
  }, [])

  return (
    <div className="theme-c min-h-svh bg-background font-sans text-foreground antialiased">
      <CRail />
      <CMobileTop />
      <div className="flex min-h-svh flex-col pb-16 lg:pb-0 lg:pl-[248px]">
        <main className="flex-1">
          <Outlet />
        </main>
        <CFooter />
      </div>
      <CMobileTabs />
      <ScrollRestoration />
    </div>
  )
}

/** Монограмма: узел маршрута — кольцо с точкой-станцией */
function CMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'relative grid size-9 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground',
        className,
      )}
    >
      <svg viewBox="0 0 24 24" className="size-5" fill="none" aria-hidden>
        <path
          d="M4 17c4-.5 5.5-8 9-9.5 2-.86 5 .5 6 3"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <circle cx="4.5" cy="17" r="2" fill="currentColor" />
        <circle cx="19" cy="10.2" r="2" fill="currentColor" />
      </svg>
    </span>
  )
}

function useNavItems(): { to: string; end?: boolean; label: string; icon: LucideIcon }[] {
  const { session } = useAuth()
  const { mockSubscriber } = useAppMode()
  const showCabinet = Boolean(session) || mockSubscriber
  return [
    { to: '/catalog', end: true, label: ru.common.registry, icon: Compass },
    ...(showCabinet
      ? [{ to: '/cabinet', label: ru.common.cabinet, icon: LayoutDashboard }]
      : []),
    { to: '/pricing', label: ru.common.pricing, icon: BadgeCheck },
  ]
}

function CRail() {
  const items = useNavItems()
  const { session, signOut } = useAuth()

  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-[248px] flex-col border-r border-border bg-card lg:flex">
      <Link
        to="/catalog"
        className="flex items-center gap-3 px-5 pt-6 pb-5 focus-visible:outline-none"
      >
        <CMark />
        <span className="min-w-0">
          <span className="font-display block text-[15px] leading-tight font-medium tracking-tight">
            InspectorX
          </span>
          <span className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
            Реестр требований
          </span>
        </span>
      </Link>

      <nav className="mt-2 flex flex-col gap-1 px-3">
        {items.map(({ to, end, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                isActive
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground',
              )
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={cn(
                    'absolute top-1/2 left-0 h-5 w-[3px] -translate-y-1/2 rounded-full bg-primary transition-opacity',
                    isActive ? 'opacity-100' : 'opacity-0',
                  )}
                />
                <Icon className="size-4.5 shrink-0" />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto space-y-4 px-5 pb-5">
        <CTelemetry />
        <div className="flex items-center justify-between border-t border-border pt-4">
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <DevMenu />
          </div>
          {session ? (
            <Button variant="ghost" size="sm" onClick={() => void signOut()}>
              <LogOut />
              {ru.common.signOut}
            </Button>
          ) : (
            <Button size="sm" nativeButton={false} render={<Link to="/login" />}>
              <LogIn />
              {ru.common.signIn}
            </Button>
          )}
        </div>
        <p className="text-[11px] text-muted-foreground/70">
          <Link to="/" className="hover:text-muted-foreground">inspectorx.uz</Link>
        </p>
      </div>
    </aside>
  )
}

/** Телеметрия реестра: живой приборный блок в нижней части рейла */
function CTelemetry() {
  const { data } = useTelemetry()
  if (!data) return null
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="flex items-center gap-2">
        <span className="c-live size-1.5 shrink-0 rounded-full bg-positive" />
        <p className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
          Мониторинг
        </p>
      </div>
      <p className="mt-2 font-mono text-xs leading-relaxed text-foreground/80">
        {data.actsCount} {plural(data.actsCount, ...ru.header.actsUnit)}
        <span className="text-muted-foreground"> · {ru.header.updated(formatRelativeTime(data.updatedAt))}</span>
      </p>
      <p className="font-mono text-xs text-muted-foreground">
        {ru.header.weekly(`${data.weeklyChanges} ${plural(data.weeklyChanges, ...ru.header.changesUnit)}`)}
      </p>
    </div>
  )
}

function CMobileTop() {
  const { session, signOut } = useAuth()
  return (
    <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-border bg-card/85 px-4 backdrop-blur-lg lg:hidden">
      <Link to="/catalog" className="flex min-w-0 items-center gap-2.5">
        <CMark className="size-8 rounded-[10px]" />
        <span className="font-display truncate text-sm font-medium tracking-tight">
          InspectorX
        </span>
      </Link>
      <div className="ml-auto flex items-center gap-1">
        <ThemeToggle />
        <DevMenu />
        {session ? (
          <Button variant="ghost" size="sm" onClick={() => void signOut()}>
            {ru.common.signOut}
          </Button>
        ) : (
          <Button size="sm" nativeButton={false} render={<Link to="/login" />}>
            {ru.common.signIn}
          </Button>
        )}
      </div>
    </header>
  )
}

function CMobileTabs() {
  const items = useNavItems()
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 backdrop-blur-lg lg:hidden">
      <div className="mx-auto flex max-w-md items-stretch justify-around px-2 pt-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))]">
        {items.map(({ to, end, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'flex min-w-16 flex-col items-center gap-0.5 rounded-lg px-3 py-1.5 text-[11px] font-medium transition-colors',
                isActive ? 'text-primary' : 'text-muted-foreground',
              )
            }
          >
            <Icon className="size-5" />
            {label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}

function CFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-col gap-1.5 px-4 py-6 text-[12px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <p>{ru.footer.disclaimer}</p>
        <p className="shrink-0">
          <a href="mailto:hello@inspectorx.uz" className="hover:text-foreground">
            {ru.footer.email}
          </a>
          {' · '}
          {ru.footer.rights}
        </p>
      </div>
    </footer>
  )
}
