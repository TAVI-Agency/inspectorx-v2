import { useTelemetry } from '@/data/hooks'
import { ru } from '@/i18n/ru'
import { formatRelativeTime, pluralize } from '@/lib/format'
import { cn } from '@/lib/utils'

/** Живая строка мониторинга — в шапке на всех экранах */
export function TelemetryLine({ className }: { className?: string }) {
  const { data } = useTelemetry()
  if (!data) return <div className={cn('h-4', className)} aria-hidden />
  const [actOne, actFew, actMany] = ru.header.actsUnit
  const [chOne, chFew, chMany] = ru.header.changesUnit
  return (
    <div
      className={cn(
        'flex min-w-0 items-center gap-1.5 font-mono text-[11px] text-muted-foreground',
        className,
      )}
    >
      <span className="relative flex size-1.5 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-positive opacity-60 motion-reduce:animate-none" />
        <span className="relative inline-flex size-1.5 rounded-full bg-positive" />
      </span>
      <span className="truncate">
        {ru.header.telemetry(
          pluralize(data.actsCount, actOne, actFew, actMany),
          formatRelativeTime(data.updatedAt),
          pluralize(data.weeklyChanges, chOne, chFew, chMany),
        )}
      </span>
    </div>
  )
}
