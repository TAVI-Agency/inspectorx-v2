import { Link, NavLink } from 'react-router-dom'
import {
  CircleUserRound,
  Compass,
  MessageCircle,
  Package,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react'
import { useAuth } from '@/app/auth'
import { useNotificationCenter } from '@/data/hooks'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CMark } from '../CLayout'
import { CProfileMenu, initialsOf } from './CProfileMenu'
import { useRouteCrumb } from './nav'
import { CNotificationCenter } from './CNotificationCenter'

/** Мобильная шапка: логотип, контекст страницы, колокольчик */
export function CMobileTop() {
  const crumb = useRouteCrumb()
  return (
    <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-border bg-card/85 px-4 backdrop-blur-lg lg:hidden">
      <Link to="/catalog" className="shrink-0 focus-visible:outline-none">
        <CMark className="size-8 rounded-[10px]" />
      </Link>
      <p className="min-w-0 truncate font-mono text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase">
        {crumb}
      </p>
      <span className="ml-auto shrink-0">
        <CNotificationCenter />
      </span>
    </header>
  )
}

const TABS: { to: string; end?: boolean; label: string; icon: LucideIcon; dot?: boolean }[] = [
  { to: '/catalog', end: true, label: ru.nav.registry, icon: Compass },
  { to: '/products', label: ru.nav.products, icon: Package, dot: true },
  { to: '/changes', label: ru.nav.changes, icon: TrendingUp, dot: true },
  { to: '/questions', label: ru.nav.questions, icon: MessageCircle },
]

/** Нижние табы: частое + вход в меню профиля (там же «Проверки» и юрист) */
export function CMobileTabs() {
  const { session, profile } = useAuth()
  const { changesUnread } = useNotificationCenter()

  const tabClass =
    'flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-lg px-1 py-1.5 text-[10px] font-medium transition-colors'

  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 backdrop-blur-lg lg:hidden">
      <div className="mx-auto flex max-w-md items-stretch justify-around px-1 pt-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))]">
        {TABS.map(({ to, end, label, icon: Icon, dot }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(tabClass, 'relative', isActive ? 'text-primary' : 'text-muted-foreground')
            }
          >
            {dot && changesUnread > 0 && (
              <span className="c-unread absolute -top-0.5 right-1/2 size-1.5 translate-x-3 rounded-full bg-primary" />
            )}
            <Icon className="size-5" />
            <span className="max-w-full truncate">{label}</span>
          </NavLink>
        ))}
        <CProfileMenu
          side="top"
          align="end"
          includeNavSections
          trigger={
            <button
              type="button"
              aria-label={ru.profileMenu.openAria}
              className={cn(tabClass, 'text-muted-foreground')}
            >
              <span className="flex h-5 items-center">
                {session ? (
                  <span className="grid size-6 place-items-center rounded-full bg-primary/15 text-[10px] font-semibold text-primary">
                    {initialsOf(profile?.fullName)}
                  </span>
                ) : (
                  <CircleUserRound className="size-5" />
                )}
              </span>
              <span className="max-w-full truncate">{ru.nav.profile}</span>
            </button>
          }
        />
      </div>
    </nav>
  )
}
