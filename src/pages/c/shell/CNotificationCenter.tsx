import { Bell } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { useNotificationCenter, useTelemetry } from '@/data/hooks'
import type { AppNotification } from '@/data/types'
import { formatDate, formatRelativeTime, plural } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'

/** Колокольчик: единый центр уведомлений в шапке */
export function CNotificationCenter() {
  const { session } = useAuth()
  const { mockSubscriber } = useAppMode()
  const { items, unreadCount, markRead, markAllRead } = useNotificationCenter()
  const { data: telemetry } = useTelemetry()

  return (
    <Popover>
      <PopoverTrigger
        aria-label={ru.notifications.aria(unreadCount)}
        className="relative inline-flex size-9 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <Bell className="size-4" />
        {unreadCount > 0 && (
          <span className="c-unread absolute -top-1.5 -right-1.5 grid min-w-[18px] place-items-center rounded-full bg-primary px-1 py-0.5 font-mono text-[10px] leading-none font-semibold text-primary-foreground">
            {unreadCount}
          </span>
        )}
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} className="w-[340px] gap-0 p-0">
        <div className="flex items-center justify-between border-b border-border px-3.5 py-2.5">
          <p className="text-sm font-semibold tracking-tight">{ru.notifications.title}</p>
          {unreadCount > 0 && (
            <button
              type="button"
              onClick={markAllRead}
              className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              {ru.notifications.markAllRead}
            </button>
          )}
        </div>
        <div className="max-h-96 overflow-y-auto">
          {items.length === 0 ? (
            <p className="px-3.5 py-5 text-xs leading-relaxed text-muted-foreground">
              {session || mockSubscriber ? ru.notifications.empty : ru.notifications.emptyGuest}
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {items.map((n) => (
                <CNotificationRow key={n.id} n={n} onRead={() => markRead(n)} />
              ))}
            </ul>
          )}
        </div>
        {/* Телеметрия мониторинга — прежний виджет рейла живёт теперь здесь */}
        <div className="flex items-center justify-between gap-3 border-t border-border px-3.5 py-2.5">
          {telemetry && (
            <p className="flex min-w-0 items-center gap-2 font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
              <span className="c-live size-1.5 shrink-0 rounded-full bg-positive" />
              <span className="truncate">
                {telemetry.actsCount} {plural(telemetry.actsCount, ...ru.header.actsUnit)}
                {' · '}
                {ru.header.updated(formatRelativeTime(telemetry.updatedAt))}
              </span>
            </p>
          )}
          <Link
            to="/changes"
            className="shrink-0 text-xs font-medium text-primary underline-offset-2 hover:underline"
          >
            {ru.notifications.allChanges} →
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function CNotificationRow({ n, onRead }: { n: AppNotification; onRead: () => void }) {
  const inner = (
    <span className="flex items-start gap-2">
      <span
        className={cn(
          'mt-1.5 size-1.5 shrink-0 rounded-full',
          n.isRead ? 'bg-transparent' : n.inFavor ? 'c-unread bg-positive' : 'c-unread bg-primary',
        )}
      />
      <span className="min-w-0">
        <span className={cn('block text-[13px] leading-snug', !n.isRead && 'font-medium')}>
          {n.title}
        </span>
        {(n.subtitle || n.inFavor) && (
          <span className="mt-0.5 block truncate text-xs text-muted-foreground">
            {n.inFavor && (
              <span className="font-medium text-positive">{ru.notifications.inFavor} · </span>
            )}
            {n.subtitle}
          </span>
        )}
        <span className="mt-0.5 block font-mono text-[10px] text-muted-foreground">
          {formatDate(n.createdAt)}
        </span>
      </span>
    </span>
  )
  return (
    <li>
      {n.link ? (
        <Link
          to={n.link}
          onClick={onRead}
          className="block px-3.5 py-2.5 transition-colors hover:bg-secondary/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {inner}
        </Link>
      ) : (
        <button
          type="button"
          onClick={onRead}
          className="block w-full px-3.5 py-2.5 text-left transition-colors hover:bg-secondary/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {inner}
        </button>
      )}
    </li>
  )
}
