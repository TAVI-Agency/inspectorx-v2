import { Link } from 'react-router-dom'
import { ArrowRight, Bell, Check, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { useChangeFeed, useMarkChangeRead, usePortfolioIds } from '@/data/hooks'
import type { ChangeCard } from '@/data/types'
import { daysUntil, formatDate } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CCard, CEyebrow } from './ui'

/**
 * Изменения: лента было/стало по товарам портфеля — станции на нити времени
 * (перенос секции «Лента изменений» из CCabinetPage, полноэкранная страница).
 */
export function CChangesPage() {
  const { session } = useAuth()
  const { mockSubscriber } = useAppMode()
  const { data: portfolio } = usePortfolioIds()
  const ids = portfolio?.ids ?? []
  const { data: feed } = useChangeFeed(ids.length > 0 ? ids : undefined)

  if (!session && !mockSubscriber) return <CLoginCard />

  return (
    <div className="mx-auto max-w-3xl px-4 py-7 sm:px-8">
      <CEyebrow>Мониторинг</CEyebrow>
      <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight sm:text-[30px]">
        {ru.changesPage.title}
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">{ru.changesPage.subtitle}</p>

      {ids.length === 0 ? (
        <CCard className="mt-6 p-6">
          <p className="text-sm font-medium">{ru.changesPage.emptyPortfolioTitle}</p>
          <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
            {ru.changesPage.emptyPortfolioText}
          </p>
          <Button size="sm" variant="outline" className="mt-4" nativeButton={false} render={<Link to="/catalog" />}>
            {ru.changesPage.emptyPortfolioCta}
          </Button>
        </CCard>
      ) : feed && feed.items.length > 0 ? (
        <div className="relative mt-6">
          <span
            aria-hidden
            className="c-thread absolute top-4 bottom-4 left-[7px] hidden w-px bg-gradient-to-b from-primary/50 via-primary/25 to-transparent sm:block"
          />
          <div className="space-y-4">
            {feed.items.map((c, i) => (
              <CFeedCard key={c.id} card={c} index={i} />
            ))}
          </div>
        </div>
      ) : (
        <CCard className="mt-6 p-6 text-sm text-muted-foreground">{ru.cabinet.feedQuiet}</CCard>
      )}
    </div>
  )
}

const IMPORTANCE_TONE: Record<ChangeCard['importance'], string> = {
  high: 'bg-sanction/10 text-sanction ring-1 ring-sanction/25 ring-inset',
  medium: 'bg-primary/10 text-primary ring-1 ring-primary/25 ring-inset',
  low: 'bg-secondary text-muted-foreground',
}

function CFeedCard({ card, index }: { card: ChangeCard; index: number }) {
  const markRead = useMarkChangeRead()
  const days = card.effectiveDate ? daysUntil(card.effectiveDate) : null

  return (
    <div
      className="c-rise relative sm:pl-8"
      style={{ '--i': index } as React.CSSProperties}
    >
      {/* Станция на нити времени */}
      <span
        aria-hidden
        className={cn(
          'absolute top-5 left-[3px] hidden size-[9px] rounded-full border-2 bg-card sm:block',
          card.unread ? 'c-unread border-primary bg-primary' : 'border-primary/45',
        )}
      />
      <CCard className={cn('p-4 sm:p-5', card.isDraftNpa && 'opacity-65')}>
        <div className="flex items-center justify-between gap-2">
          <span className="min-w-0 flex-1 truncate text-xs font-medium text-muted-foreground">
            {card.productName}
            {card.stageName ? ` · ${card.stageName}` : ''}
          </span>
          <span
            className={cn(
              'shrink-0 rounded-[6px] px-2 py-0.5 text-[11px] font-medium',
              card.isDraftNpa ? 'bg-secondary text-muted-foreground' : IMPORTANCE_TONE[card.importance],
            )}
          >
            {card.isDraftNpa ? ru.cabinet.draftNpa : ru.cabinet.importance[card.importance]}
          </span>
        </div>

        <h3 className="mt-2 text-[15px] font-semibold tracking-tight">{card.title}</h3>

        {(card.was || card.now) && (
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {card.was && (
              <div className="rounded-lg bg-secondary/60 p-3">
                <p className="font-mono text-[10px] tracking-[0.1em] text-muted-foreground uppercase">
                  {ru.requirement.card.was}
                </p>
                <p className="mt-1 text-sm text-muted-foreground line-through decoration-sanction/40">
                  {card.was}
                </p>
              </div>
            )}
            {card.now && (
              <div className="rounded-lg bg-accent/60 p-3 ring-1 ring-primary/15 ring-inset">
                <p className="font-mono text-[10px] tracking-[0.1em] text-primary uppercase">
                  {ru.requirement.card.now}
                </p>
                <p className="mt-1 text-sm font-medium">{card.now}</p>
              </div>
            )}
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
          <span className="font-mono">{formatDate(card.date)}</span>
          {card.effectiveDate && days != null && (
            <span className={cn('font-medium', days >= 0 && days <= 14 && 'text-sanction')}>
              {days >= 0
                ? ru.cabinet.effectiveIn(days, formatDate(card.effectiveDate))
                : ru.cabinet.effectiveAlready}
            </span>
          )}
          {card.inFavor && <span className="font-medium text-positive">{ru.cabinet.inFavor}</span>}
        </div>

        {card.inFavor ? (
          <p className="mt-2.5 rounded-lg border border-positive/25 bg-positive/5 px-3 py-2 text-[13px] leading-relaxed text-positive">
            <span className="font-semibold">{ru.cabinet.whatToDo}:</span> {ru.cabinet.nothingToDo}
          </p>
        ) : card.action ? (
          <p className="mt-2.5 rounded-lg border border-border bg-background/60 px-3 py-2 text-[13px] leading-relaxed">
            <span className="font-semibold">{ru.cabinet.whatToDo}:</span> {card.action}
          </p>
        ) : null}

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          {card.requirementId && (
            <Link
              to={`/product/${card.productId}?req=${card.requirementId}`}
              className="inline-flex items-center gap-1 text-[13px] font-medium text-primary underline-offset-2 hover:underline"
            >
              {ru.cabinet.toRequirement}
              <ArrowRight className="size-3.5" />
            </Link>
          )}
          {card.isDraftNpa && card.discussionUrl && (
            <a
              href={card.discussionUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[13px] font-medium text-muted-foreground underline-offset-2 hover:underline"
            >
              {ru.cabinet.draftNpaLink}
              <ExternalLink className="size-3" />
            </a>
          )}
          {card.unread && (
            <button
              type="button"
              disabled={markRead.isPending}
              onClick={() => markRead.mutate(card.id)}
              className="ml-auto inline-flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground disabled:opacity-60"
            >
              <Check className="size-3.5" />
              {ru.cabinet.markRead}
            </button>
          )}
        </div>
      </CCard>
    </div>
  )
}

function CLoginCard() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-24 sm:px-8">
      <CCard className="mx-auto max-w-md p-8 text-center">
        <span className="mx-auto grid size-12 place-items-center rounded-full border border-primary/40 bg-accent text-accent-foreground">
          <Bell className="size-5" />
        </span>
        <h1 className="mt-4 text-xl font-semibold tracking-tight">{ru.auth.loginRequired}</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {ru.cabinet.portfolioEmpty.text}
        </p>
        <Button className="mt-5" nativeButton={false} render={<Link to="/login" />}>
          {ru.common.signIn}
        </Button>
      </CCard>
    </div>
  )
}
