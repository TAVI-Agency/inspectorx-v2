import type { StageInfo } from '@/data/types'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'

/** Фильтры-чипы этапов ЖЦ со счётчиками и точками непрочитанного (§3.3) */
export function StageChips({
  stages,
  active,
  onChange,
  total,
}: {
  stages: StageInfo[]
  active: string | null
  onChange: (stageId: string | null) => void
  total: number
}) {
  return (
    <div
      className="scrollbar-none -mx-4 flex gap-2 overflow-x-auto px-4 max-sm:[mask-image:linear-gradient(to_right,black_90%,transparent)] sm:mx-0 sm:flex-wrap sm:px-0"
      role="tablist"
      aria-label={ru.product.listTitle}
    >
      <Chip
        label={ru.product.stagesAll}
        count={total}
        selected={active === null}
        onClick={() => onChange(null)}
      />
      {stages.map((s) => (
        <Chip
          key={s.id}
          label={s.name}
          count={s.count}
          unread={s.unreadCount > 0}
          selected={active === s.id}
          onClick={() => onChange(active === s.id ? null : s.id)}
        />
      ))}
    </div>
  )
}

function Chip({
  label,
  count,
  unread,
  selected,
  onClick,
}: {
  label: string
  count: number
  unread?: boolean
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      onClick={onClick}
      className={cn(
        'relative inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-[13px] whitespace-nowrap transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
        selected
          ? 'border-foreground bg-foreground text-background'
          : 'bg-paper text-foreground hover:border-foreground/30',
      )}
    >
      {unread && (
        <span
          className="absolute -top-0.5 -right-0.5 size-2 rounded-full bg-primary"
          aria-label="есть непрочитанные изменения"
        />
      )}
      <span className="whitespace-nowrap">{label}</span>
      <span
        className={cn(
          'font-mono text-[11px]',
          selected ? 'text-background/70' : 'text-muted-foreground',
        )}
      >
        {count}
      </span>
    </button>
  )
}
