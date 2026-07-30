import { Link, NavLink } from 'react-router-dom'
import { ChevronsUpDown, CircleUserRound, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CMark } from '../CLayout'
import { CProfileMenu, initialsOf } from './CProfileMenu'
import { useNavSections, type NavItem } from './nav'

/**
 * Рейл-кокпит: секции навигации, внизу — карточка профиля.
 * Сворачивается до иконок; редкое (тема, выход, тариф) живёт в меню профиля.
 */
export function CRail({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const sections = useNavSections()

  return (
    <aside
      className={cn(
        'fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-border bg-card transition-[width] duration-200 lg:flex',
        collapsed ? 'w-16' : 'w-[248px]',
      )}
    >
      {collapsed ? (
        <div className="flex flex-col items-center gap-2 pt-5">
          <Link to="/catalog" className="focus-visible:outline-none">
            <CMark />
          </Link>
          <CRailToggle collapsed={collapsed} onToggle={onToggle} />
        </div>
      ) : (
        <div className="flex items-center gap-2 px-4 pt-6 pb-1">
          <Link to="/catalog" className="flex min-w-0 items-center gap-3 focus-visible:outline-none">
            <CMark />
            <span className="min-w-0 overflow-hidden">
              <span className="font-display block text-[15px] leading-tight font-medium tracking-tight">
                InspectorX
              </span>
              <span className="block font-mono text-[10px] tracking-[0.14em] whitespace-nowrap text-muted-foreground uppercase">
                Реестр требований
              </span>
            </span>
          </Link>
          <span className="-mr-1 ml-auto">
            <CRailToggle collapsed={collapsed} onToggle={onToggle} />
          </span>
        </div>
      )}

      <nav className="mt-1 flex-1 overflow-y-auto pb-4">
        {sections.map((section, i) => (
          <div key={section.label ?? `section-${i}`}>
            {section.label &&
              (collapsed ? (
                <div className="mx-3 my-3 border-t border-border" />
              ) : (
                <p className="px-3 pt-5 pb-1 font-mono text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase">
                  {section.label}
                </p>
              ))}
            <div className={cn('flex flex-col gap-1', collapsed ? 'px-2' : 'px-3')}>
              {section.items.map((item) => (
                <CRailLink key={item.to} item={item} collapsed={collapsed} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-2">
        <CRailProfile collapsed={collapsed} />
      </div>
    </aside>
  )
}

function CRailToggle({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const Icon = collapsed ? PanelLeftOpen : PanelLeftClose
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={collapsed ? ru.nav.expand : ru.nav.collapse}
      title={collapsed ? ru.nav.expand : ru.nav.collapse}
      className="inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <Icon className="size-4" />
    </button>
  )
}

function CRailLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const { to, end, label, icon: Icon, badge, soon } = item
  const hasBadge = Boolean(badge && badge > 0)

  return (
    <NavLink
      to={to}
      end={end}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        cn(
          'group relative flex items-center gap-3 rounded-lg py-2.5 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
          collapsed ? 'justify-center px-0' : 'px-3',
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
          {collapsed ? (
            hasBadge && (
              <span className="c-unread absolute top-1.5 right-1.5 size-1.5 rounded-full bg-primary" />
            )
          ) : (
            <>
              {label}
              {hasBadge ? (
                <span className="ml-auto rounded-full bg-primary px-1.5 py-0.5 font-mono text-[10px] leading-none font-semibold text-primary-foreground">
                  {badge}
                </span>
              ) : soon ? (
                <span className="ml-auto font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
                  {ru.nav.soon}
                </span>
              ) : null}
            </>
          )}
        </>
      )}
    </NavLink>
  )
}

/** Карточка профиля внизу рейла — единственный вход в редкие действия */
function CRailProfile({ collapsed }: { collapsed: boolean }) {
  const { session, profile, realSubscriber } = useAuth()
  const { mockSubscriber } = useAppMode()

  const planLine = realSubscriber
    ? ru.profileMenu.planPaid
    : mockSubscriber
      ? ru.profileMenu.planDemo
      : ru.profileMenu.planFree

  const avatar = session ? (
    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
      {initialsOf(profile?.fullName)}
    </span>
  ) : (
    <CircleUserRound className="size-8 shrink-0 text-muted-foreground" />
  )

  return (
    <CProfileMenu
      side="top"
      align="start"
      trigger={
        <button
          type="button"
          aria-label={ru.profileMenu.openAria}
          className={cn(
            'flex w-full items-center gap-2.5 rounded-lg py-2 text-left transition-colors hover:bg-secondary/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
            collapsed ? 'justify-center px-0' : 'px-2.5',
          )}
        >
          {avatar}
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium">
                  {session ? (profile?.fullName ?? session.user.email) : ru.profileMenu.guestName}
                </span>
                <span className="block truncate text-[11px] text-muted-foreground">{planLine}</span>
              </span>
              <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
            </>
          )}
        </button>
      }
    />
  )
}
