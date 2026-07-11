import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useMarkChangeRead } from '@/data/hooks'
import type { ChangeCard } from '@/data/types'
import { ru } from '@/i18n/ru'
import { daysUntil, formatDate } from '@/lib/format'
import { cn } from '@/lib/utils'

function ImportanceBadge({ importance }: { importance: ChangeCard['importance'] }) {
  return (
    <span
      className={cn(
        'inline-flex h-[18px] items-center rounded px-1.5 text-[11px] font-medium',
        importance === 'high' && 'bg-primary/12 text-primary',
        importance === 'medium' && 'bg-secondary text-secondary-foreground',
        importance === 'low' && 'text-muted-foreground',
      )}
    >
      {ru.cabinet.importance[importance]}
    </span>
  )
}

function WasNow({ was, now }: { was?: string; now?: string }) {
  return (
    <div className="mt-3 space-y-2 rounded-md border bg-background/50 p-3 text-sm">
      {was && (
        <p className="leading-relaxed text-muted-foreground">
          <span className="font-mono text-[10px] tracking-[0.08em] uppercase">
            {ru.requirement.card.was}:{' '}
          </span>
          <span className="line-through decoration-foreground/30">{was}</span>
        </p>
      )}
      {now && (
        <p className="leading-relaxed">
          <span className="font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
            {ru.requirement.card.now}:{' '}
          </span>
          {now}
        </p>
      )}
    </div>
  )
}

/** Карточка изменения в ленте (§3a.3) */
export function ChangeCardItem({ card }: { card: ChangeCard }) {
  const markRead = useMarkChangeRead()
  const [showDiff, setShowDiff] = useState(false)

  // Проект НПА — ещё не право: приглушённая карточка без пугающих бейджей
  if (card.isDraftNpa) {
    return (
      <li className="rounded-lg border border-dashed p-4 opacity-75">
        <p className="font-mono text-[10px] tracking-[0.1em] text-muted-foreground uppercase">
          {ru.cabinet.draftNpa}
        </p>
        <p className="mt-1.5 text-sm">{card.title}</p>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
          <span>{card.productName}</span>
          <span>{formatDate(card.date)}</span>
          {card.discussionUrl && (
            <a
              href={card.discussionUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 hover:text-foreground"
            >
              {ru.cabinet.draftNpaLink}
              <ExternalLink className="size-3" />
            </a>
          )}
        </div>
      </li>
    )
  }

  const hasDiff = Boolean(card.was || card.now)
  const diffVisible = card.importance === 'high' || showDiff
  const days = card.effectiveDate ? daysUntil(card.effectiveDate) : null

  return (
    <li className={cn('rounded-lg border bg-paper p-4', card.unread && 'border-primary/40')}>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        {card.unread && (
          <span className="size-1.5 rounded-full bg-primary" aria-label="непрочитанное" />
        )}
        <ImportanceBadge importance={card.importance} />
        <span className="font-mono text-[11px] text-muted-foreground">
          {card.productName}
          {card.stageName ? ` · ${card.stageName}` : ''} · {formatDate(card.date)}
        </span>
      </div>

      <h3 className="mt-2 text-[15px] leading-snug font-semibold text-balance">
        {card.title}
      </h3>

      {hasDiff && diffVisible && <WasNow was={card.was} now={card.now} />}

      {(card.effectiveDate || card.action || card.inFavor) && (
        <div className="mt-3 space-y-1.5 text-sm">
          {card.effectiveDate && days !== null && (
            <p
              className={cn(
                'font-medium',
                days >= 0 && days <= 30 ? 'text-primary' : 'text-muted-foreground',
              )}
            >
              {days >= 0
                ? ru.cabinet.effectiveIn(days, formatDate(card.effectiveDate))
                : ru.cabinet.effectiveAlready}
            </p>
          )}
          {card.inFavor && (
            <p className="font-medium text-positive">{ru.cabinet.inFavor}</p>
          )}
          {(card.action || card.inFavor) && (
            <p className="leading-relaxed">
              <span className="font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
                {ru.cabinet.whatToDo}:{' '}
              </span>
              {card.action ?? ru.cabinet.nothingToDo}
            </p>
          )}
        </div>
      )}

      <div className="mt-3.5 flex flex-wrap items-center gap-1.5 border-t pt-3">
        {card.requirementId && (
          <Button
            variant="outline"
            size="xs"
            nativeButton={false}
            render={
              <Link to={`/product/${card.productId}?req=${card.requirementId}`} />
            }
          >
            {ru.cabinet.toRequirement}
            <ArrowRight data-icon="inline-end" />
          </Button>
        )}
        {hasDiff && !diffVisible && (
          <Button variant="ghost" size="xs" onClick={() => setShowDiff(true)}>
            Сравнить редакции
          </Button>
        )}
        {card.unread && (
          <Button
            variant="ghost"
            size="xs"
            className="text-muted-foreground"
            disabled={markRead.isPending}
            onClick={() => markRead.mutate(card.id)}
          >
            {ru.cabinet.markRead}
          </Button>
        )}
      </div>
    </li>
  )
}
