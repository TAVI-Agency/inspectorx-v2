import { Outlet, ScrollRestoration, Link, NavLink } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ThemeToggle } from '@/app/layout/ThemeToggle'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { cn } from '@/lib/utils'

/**
 * Оболочка дизайна Б. Всё поддерево обёрнуто в .theme-b — токены (цвет, радиус,
 * шрифт Geist) переопределяются локально, дизайны не протекают. Данные и
 * контексты (auth/theme) — общие с дизайном A.
 */
export function BLayout() {
  return (
    <div className="theme-b flex min-h-svh flex-col bg-background text-foreground">
      <BHeader />
      <main className="flex-1">
        <Outlet />
      </main>
      <BFooter />
      <ScrollRestoration />
    </div>
  )
}

function navClass({ isActive }: { isActive: boolean }) {
  return cn(
    'rounded-full px-3 py-1.5 text-sm font-medium transition-colors',
    isActive
      ? 'bg-secondary text-foreground'
      : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground',
  )
}

function BHeader() {
  const { session, signOut } = useAuth()
  const { mockSubscriber } = useAppMode()
  const showCabinet = Boolean(session) || mockSubscriber

  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-background/80 backdrop-blur-lg">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:px-6">
        <Link to="/b" className="flex shrink-0 items-center gap-2">
          <span className="grid size-8 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <span className="text-[15px] font-bold">iX</span>
          </span>
          <span className="text-[15px] font-semibold tracking-tight">InspectorX</span>
          <span className="rounded-full bg-accent px-2 py-0.5 text-[10px] font-semibold tracking-wide text-accent-foreground uppercase">
            Кокпит
          </span>
        </Link>

        <nav className="ml-4 hidden items-center gap-1 md:flex">
          <NavLink to="/b" end className={navClass}>
            Каталог
          </NavLink>
          <NavLink to="/b/pricing" className={navClass}>
            Тарифы
          </NavLink>
          {showCabinet && (
            <NavLink to="/b/cabinet" className={navClass}>
              Кабинет
            </NavLink>
          )}
          <NavLink to="/b/admin" className={navClass}>
            Админка
          </NavLink>
        </nav>

        <div className="ml-auto flex items-center gap-1.5">
          <ThemeToggle />
          {session ? (
            <Button variant="ghost" size="sm" onClick={() => void signOut()}>
              Выйти
            </Button>
          ) : (
            <Button size="sm" nativeButton={false} render={<Link to="/b/login" />}>
              Войти
            </Button>
          )}
        </div>
      </div>
    </header>
  )
}

function BFooter() {
  return (
    <footer className="mt-auto border-t border-border/70">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex items-center gap-2.5">
          <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground">
            <span className="text-xs font-bold">iX</span>
          </span>
          <span className="text-sm text-muted-foreground">
            InspectorX · чек-лист соответствия · дизайн Б
          </span>
        </div>
        <div className="flex items-center gap-5 text-sm text-muted-foreground">
          <a href="mailto:hello@inspectorx.uz" className="hover:text-foreground">
            hello@inspectorx.uz
          </a>
          <Link to="/" className="hover:text-foreground">
            ← Дизайн A
          </Link>
        </div>
      </div>
    </footer>
  )
}
