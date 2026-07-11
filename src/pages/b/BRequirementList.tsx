import { useEffect, useMemo, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Expand } from '@/components/Expand'
import { useMarkChangeRead } from '@/data/hooks'
import type { RequirementRow, StageInfo } from '@/data/types'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { rolesLabel } from '@/pages/product/badges'
import { RequirementCardView } from '@/pages/product/RequirementCardView'
import { BCard, deonticChipClass } from './ui'

/**
 * Список требований дизайна Б: этапы — карточки-секции, строки со скруглением
 * и цветной плашкой типа. Раскрытие переиспускает RequirementCardView
 * (уровни 1–2 общие для обоих фронтов, перекрашиваются токенами).
 */
export function BRequirementList({
  rows,
  stages,
  activeStage,
  productId,
  initialRequirementId,
}: {
  rows: RequirementRow[]
  stages: StageInfo[]
  activeStage: string | null
  productId: string
  initialRequirementId?: string
}) {
  const [expandedId, setExpandedId] = useState<string | null>(initialRequirementId ?? null)
  const markRead = useMarkChangeRead()

  useEffect(() => {
    setExpandedId(initialRequirementId ?? null)
  }, [initialRequirementId])

  const numberById = useMemo(() => {
    const map = new Map<string, number>()
    rows.forEach((r, i) => map.set(r.id, i + 1))
    return map
  }, [rows])

  const visibleStages = useMemo(() => {
    const filtered = activeStage ? stages.filter((s) => s.id === activeStage) : stages
    return filtered
      .map((stage) => ({ stage, items: rows.filter((r) => r.stageId === stage.id) }))
      .filter((g) => g.items.length > 0)
  }, [rows, stages, activeStage])

  function toggle(row: RequirementRow) {
    const opening = expandedId !== row.id
    setExpandedId(opening ? row.id : null)
    if (opening && row.unread && row.changeId) markRead.mutate(row.changeId)
  }

  return (
    <div className="space-y-5">
      {visibleStages.map(({ stage, items }, gi) => (
        <BCard key={stage.id} className="overflow-hidden">
          <header className="flex items-center gap-3 border-b bg-secondary/40 px-4 py-3">
            <span className="grid size-6 shrink-0 place-items-center rounded-lg bg-primary/10 font-mono text-[11px] font-semibold text-primary">
              {gi + 1}
            </span>
            <h3 className="min-w-0 flex-1 text-sm font-semibold tracking-tight">
              {stage.name}
            </h3>
            <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
              {items.length}
            </span>
          </header>
          <ul className="divide-y">
            {items.map((row) => (
              <BRow
                key={row.id}
                row={row}
                number={numberById.get(row.id) ?? 0}
                expanded={expandedId === row.id}
                onToggle={() => toggle(row)}
                productId={productId}
              />
            ))}
          </ul>
        </BCard>
      ))}
    </div>
  )
}

function BRow({
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
    <li className={cn(expanded && 'bg-secondary/30')}>
      <button
        type="button"
        aria-expanded={expanded}
        onClick={onToggle}
        className="group flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors hover:bg-secondary/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <span className="relative mt-0.5 shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
          {String(number).padStart(2, '0')}
          {row.unread && (
            <span className="absolute -top-1 -left-2 size-1.5 rounded-full bg-primary" />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className={cn('text-[15px] leading-snug', expanded ? 'font-semibold' : 'font-medium')}>
              {row.title}
            </span>
            {row.underReview && (
              <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">
                {ru.requirement.underReview}
              </span>
            )}
          </span>
          <span className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-[11px] font-medium',
                deonticChipClass(row.deontic),
              )}
            >
              {ru.requirement.deontic[row.deontic]}
            </span>
            <span>{rolesLabel(row.roles)}</span>
            {row.authorityName && <span className="truncate">· {row.authorityName}</span>}
            {row.sanctionSummary && (
              <span
                className={cn(
                  'font-medium',
                  row.deontic === 'permission' ? 'text-muted-foreground' : 'text-sanction',
                )}
              >
                · {row.sanctionSummary}
              </span>
            )}
          </span>
        </span>
        <ChevronDown
          className={cn(
            'mt-1 size-4 shrink-0 text-muted-foreground transition-transform duration-300',
            expanded && 'rotate-180',
          )}
        />
      </button>
      <Expand open={expanded}>
        {expanded && <RequirementCardView row={row} productId={productId} />}
      </Expand>
    </li>
  )
}
