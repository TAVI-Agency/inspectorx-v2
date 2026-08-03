import { useEffect, useMemo, useState } from 'react'
import { BadgeCheck, ChevronDown, TriangleAlert } from 'lucide-react'
import { Expand } from '@/components/Expand'
import { useMarkChangeRead, useReviewStats } from '@/data/hooks'
import type { RequirementReviewStats, RequirementRow, StageInfo } from '@/data/types'
import { categoryChipOf } from '@/data/taxonomy'
import { formatDate, pluralize } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CCard, CCategoryChip, CDeonticChip, CLifecycleBadge } from './ui'
import { CRequirementCard } from './CRequirementCard'

/**
 * Список требований: этапы — станции на той же нити маршрута, что и
 * навигация операций. Внутри этапа — нумерованные строки, раскрывающиеся
 * в карточку уровней 1–2.
 */
export function CRequirementList({
  rows,
  stages,
  productId,
  initialRequirementId,
  inProgressStageIds,
}: {
  rows: RequirementRow[]
  stages: StageInfo[]
  /** Товар — для формы вопроса; у услуг не передаётся */
  productId?: string
  initialRequirementId?: string
  /** Этапы с неопубликованными карточками — пометка «раздел в работе» */
  inProgressStageIds?: Set<string>
}) {
  const [expandedId, setExpandedId] = useState<string | null>(initialRequirementId ?? null)
  const markRead = useMarkChangeRead()
  // Бейджи «Подтвердил юрист»: один агрегирующий запрос по строкам страницы
  const { data: reviewStats } = useReviewStats(rows.map((r) => r.id))

  useEffect(() => {
    setExpandedId(initialRequirementId ?? null)
  }, [initialRequirementId])

  const numberById = useMemo(() => {
    const map = new Map<string, number>()
    rows.forEach((r, i) => map.set(r.id, i + 1))
    return map
  }, [rows])

  const groups = useMemo(
    () =>
      stages
        .map((stage) => ({ stage, items: rows.filter((r) => r.stageId === stage.id) }))
        .filter((g) => g.items.length > 0),
    [rows, stages],
  )

  function toggle(row: RequirementRow) {
    const opening = expandedId !== row.id
    setExpandedId(opening ? row.id : null)
    if (opening && row.unread && row.changeId) markRead.mutate(row.changeId)
  }

  return (
    <div className="relative">
      {/* Нить этапов — продолжение маршрута */}
      <span
        aria-hidden
        className="c-thread absolute top-4 bottom-4 left-[15px] hidden w-px bg-gradient-to-b from-primary/50 via-primary/25 to-transparent sm:block"
      />
      <div className="space-y-6">
        {groups.map(({ stage, items }, gi) => (
          <section
            key={stage.id}
            id={`stage-${stage.id}`}
            className="c-rise relative scroll-mt-24 sm:pl-11"
            style={{ '--i': gi } as React.CSSProperties}
          >
            {/* Станция этапа */}
            <span
              aria-hidden
              className="absolute top-0.5 left-0 hidden size-8 place-items-center rounded-full border border-primary/45 bg-card font-mono text-[12px] font-semibold text-primary sm:grid"
            >
              {gi + 1}
            </span>
            <header className="flex items-baseline gap-2.5 pt-1">
              <h3 className="min-w-0 text-[15px] font-semibold tracking-tight">
                <span className="mr-1.5 font-mono text-[12px] font-semibold text-primary sm:hidden">
                  {gi + 1}.
                </span>
                {stage.name}
              </h3>
              <span className="shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
                {items.length}
              </span>
              {inProgressStageIds?.has(stage.id) && (
                <span className="shrink-0 rounded-[6px] bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                  {ru.service.inProgress}
                </span>
              )}
            </header>
            <CCard className="mt-2.5 overflow-hidden">
              <ul className="divide-y divide-border">
                {items.map((row) => (
                  <CRow
                    key={row.id}
                    row={row}
                    number={numberById.get(row.id) ?? 0}
                    expanded={expandedId === row.id}
                    onToggle={() => toggle(row)}
                    productId={productId}
                    reviewStats={reviewStats?.[row.id]}
                  />
                ))}
              </ul>
            </CCard>
          </section>
        ))}
      </div>
    </div>
  )
}

/** Бейдж проверки юристом: подтверждения — изумруд, замечание — предупреждение */
function CReviewBadge({ stats }: { stats: RequirementReviewStats }) {
  const t = ru.requirement.lawyerReviews
  if (stats.confirms > 0) {
    return (
      <span className="inline-flex items-center gap-1 rounded-[6px] bg-positive/10 px-1.5 py-0.5 text-[10px] font-medium text-positive">
        <BadgeCheck className="size-3" />
        {stats.confirms === 1
          ? t.badgeConfirmedOne
          : t.badgeConfirmedMany(pluralize(stats.confirms, 'юрист', 'юриста', 'юристов'))}
      </span>
    )
  }
  if (stats.disputes > 0) {
    return (
      <span className="inline-flex items-center gap-1 rounded-[6px] bg-sanction/10 px-1.5 py-0.5 text-[10px] font-medium text-sanction">
        <TriangleAlert className="size-3" />
        {t.badgeDispute}
      </span>
    )
  }
  return null
}

function CRow({
  row,
  number,
  expanded,
  onToggle,
  productId,
  reviewStats,
}: {
  row: RequirementRow
  number: number
  expanded: boolean
  onToggle: () => void
  productId?: string
  reviewStats?: RequirementReviewStats
}) {
  return (
    <li
      className={cn(
        'transition-colors',
        expanded && 'bg-accent/25',
        // Отменённое требование — история для юзера, не скрываем, а приглушаем
        row.lifecycle === 'repealed' && 'opacity-60',
      )}
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={onToggle}
        className="group flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors hover:bg-secondary/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none sm:px-5"
      >
        <span className="relative mt-0.5 shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
          {String(number).padStart(2, '0')}
          {row.unread && (
            <span className="c-unread absolute -top-1.5 -right-2 size-1.5 rounded-full bg-primary" />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span
              className={cn(
                'text-[15px] leading-snug',
                expanded ? 'font-semibold' : 'font-medium',
              )}
            >
              {row.title}
            </span>
            {row.underReview && (
              <span className="rounded-[6px] bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                {ru.requirement.underReview}
              </span>
            )}
            <CLifecycleBadge
              lifecycle={row.lifecycle}
              effectiveFrom={row.effectiveFrom}
              transitionUntil={row.transitionUntil}
              validTo={row.validTo}
            />
            {reviewStats && <CReviewBadge stats={reviewStats} />}
          </span>
          <span className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <CDeonticChip deontic={row.deontic} />
            {(() => {
              const category = categoryChipOf(row)
              return category && <CCategoryChip category={category} />
            })()}
            {row.nature && (
              <span className="rounded-[6px] bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                {ru.requirement.nature[row.nature]}
              </span>
            )}
            <span className="truncate">
              {row.roles.map((r) => ru.requirement.roles[r]).join(', ')}
            </span>
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
            {row.status.kind !== 'active' && (
              <span className="font-medium text-primary">
                ·{' '}
                {row.status.kind === 'changed'
                  ? ru.requirement.status.changed(formatDate(row.status.date))
                  : ru.requirement.status.upcoming(formatDate(row.status.date))}
              </span>
            )}
          </span>
        </span>
        <ChevronDown
          className={cn(
            'mt-1 size-4 shrink-0 text-muted-foreground transition-transform duration-300 ease-[var(--ease-brand)]',
            expanded && 'rotate-180 text-primary',
          )}
        />
      </button>
      <Expand open={expanded}>
        {expanded && <CRequirementCard row={row} productId={productId} />}
      </Expand>
    </li>
  )
}
