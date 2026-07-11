import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Expand } from '@/components/Expand'
import { useMarkChangeRead } from '@/data/hooks'
import type { RequirementRow, StageInfo } from '@/data/types'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { DeonticBadge, StatusLabel, rolesLabel } from './badges'
import { RequirementCardView } from './RequirementCardView'

/**
 * Список требований (§3.4): сканируемые строки уровня 0,
 * сгруппированные по этапам ЖЦ; раскрытие 0→1→2 — фирменное взаимодействие.
 */
export function RequirementList({
  rows,
  stages,
  activeStage,
  productId,
  initialRequirementId,
  scrollToInitial,
}: {
  rows: RequirementRow[]
  stages: StageInfo[]
  activeStage: string | null
  productId: string
  initialRequirementId?: string
  /** Скроллим только при явном диплинке (?req=), не при дефолтном раскрытии */
  scrollToInitial?: boolean
}) {
  const [expandedId, setExpandedId] = useState<string | null>(
    initialRequirementId ?? null,
  )
  const markRead = useMarkChangeRead()
  const scrolledRef = useRef(false)

  // Документная нумерация — сквозная по товару, не зависит от фильтра
  const numberById = useMemo(() => {
    const map = new Map<string, number>()
    rows.forEach((r, i) => map.set(r.id, i + 1))
    return map
  }, [rows])

  const visibleStages = useMemo(() => {
    const filtered = activeStage ? stages.filter((s) => s.id === activeStage) : stages
    return filtered
      .map((stage) => ({
        stage,
        items: rows.filter((r) => r.stageId === stage.id),
      }))
      .filter((g) => g.items.length > 0)
  }, [rows, stages, activeStage])

  // Диплинк ?req= — проскроллить к требованию после загрузки
  useEffect(() => {
    if (!scrollToInitial || !initialRequirementId || scrolledRef.current) return
    const el = document.getElementById(`req-${initialRequirementId}`)
    if (el) {
      scrolledRef.current = true
      el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }, [scrollToInitial, initialRequirementId, rows])

  function toggle(row: RequirementRow) {
    const opening = expandedId !== row.id
    setExpandedId(opening ? row.id : null)
    if (opening && row.unread && row.changeId) markRead.mutate(row.changeId)
  }

  return (
    <div className="space-y-8">
      {visibleStages.map(({ stage, items }, gi) => (
        <section key={stage.id} aria-label={stage.name}>
          <header className="flex items-start gap-3 border-b pb-2">
            <span className="font-mono text-[11px] leading-4 text-muted-foreground">
              {String(gi + 1).padStart(2, '0')}
            </span>
            <h3 className="min-w-0 flex-1 font-mono text-[11px] leading-4 tracking-[0.06em] uppercase sm:tracking-[0.1em]">
              {stage.name}
            </h3>
            <span className="shrink-0 font-mono text-[11px] leading-4 text-muted-foreground">
              {items.length}
            </span>
          </header>
          <ul>
            {items.map((row) => (
              <RowItem
                key={row.id}
                row={row}
                number={numberById.get(row.id) ?? 0}
                expanded={expandedId === row.id}
                onToggle={() => toggle(row)}
                productId={productId}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function RowItem({
  row,
  number,
  expanded,
  onToggle,
  productId,
}: {
  row: RequirementRow
  number: number
  expanded: boolean
  onToggle: () => void
  productId: string
}) {
  return (
    <li
      id={`req-${row.id}`}
      className={cn(
        'transition-colors duration-300',
        expanded
          ? 'my-3 -mx-1 rounded-lg border bg-paper sm:-mx-3'
          : 'border-b border-border/70',
      )}
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={onToggle}
        className={cn(
          'group flex w-full items-start gap-3 px-1 py-3 text-left transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none sm:px-3',
          !expanded && 'hover:bg-accent/60',
        )}
      >
        <span className="relative mt-0.5 shrink-0">
          <span
            className={cn(
              'font-mono text-[11px] tabular-nums transition-colors',
              expanded ? 'text-primary' : 'text-muted-foreground',
            )}
          >
            {String(number).padStart(3, '0')}
          </span>
          {row.unread && (
            <span
              className="absolute -top-1 -left-2 size-1.5 rounded-full bg-primary"
              aria-label="непрочитанное изменение"
            />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className={cn('text-sm leading-snug', expanded ? 'font-semibold' : 'font-medium')}>
              {row.title}
            </span>
            {row.underReview && (
              <span className="stamp text-[9px] text-muted-foreground">
                {ru.requirement.underReview}
              </span>
            )}
          </span>
          <span className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground">
            <DeonticBadge deontic={row.deontic} />
            <span>{rolesLabel(row.roles)}</span>
            {row.authorityName && (
              <>
                <span aria-hidden className="text-border">·</span>
                <span>{row.authorityName}</span>
              </>
            )}
            {row.sanctionSummary && (
              <>
                <span aria-hidden className="text-border">·</span>
                {/* Красный — только санкции; у льготы санкции нет */}
                <span
                  className={cn(
                    'font-medium',
                    row.deontic === 'permission' ? 'text-muted-foreground' : 'text-sanction',
                  )}
                >
                  {row.sanctionSummary}
                </span>
              </>
            )}
          </span>
        </span>
        <span className="ml-2 flex shrink-0 items-center gap-2.5 self-center">
          <StatusLabel status={row.status} className="hidden sm:block" />
          <ChevronDown
            className={cn(
              'size-4 text-muted-foreground transition-transform duration-500 ease-[var(--ease-brand)]',
              expanded && 'rotate-180',
            )}
          />
        </span>
      </button>
      {row.status.kind !== 'active' && (
        <StatusLabel status={row.status} className="-mt-1 block px-1 pb-2 sm:hidden" />
      )}
      <Expand open={expanded}>
        {expanded && <RequirementCardView row={row} productId={productId} />}
      </Expand>
    </li>
  )
}
