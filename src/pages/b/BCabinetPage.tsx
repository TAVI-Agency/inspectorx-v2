import { Link } from 'react-router-dom'
import { ArrowRight, Bell } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { usePortfolioIds, useChangeFeed } from '@/data/hooks'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import type { ChangeCard, PortfolioItem } from '@/data/types'
import { formatDate, formatHsCode } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { BCard, StatTile } from './ui'

export function BCabinetPage() {
  const { session } = useAuth()
  const { mockSubscriber } = useAppMode()
  const { data: portfolio } = usePortfolioIds()
  const ids = portfolio?.ids ?? []
  const { data: feed } = useChangeFeed(ids.length > 0 ? ids : undefined)

  if (!session && !mockSubscriber) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-24 sm:px-6">
        <BCard className="mx-auto max-w-md p-8 text-center">
          <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-accent text-accent-foreground">
            <Bell className="size-6" />
          </span>
          <h1 className="mt-4 text-xl font-semibold tracking-tight">{ru.auth.loginRequired}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {ru.cabinet.portfolioEmpty.text}
          </p>
          <Button className="mt-5" nativeButton={false} render={<Link to="/b/login" />}>
            {ru.common.signIn}
          </Button>
        </BCard>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{ru.cabinet.title}</h1>

      {/* Сводка недели */}
      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <StatTile label="Товаров в портфеле" value={ids.length} tone="primary" />
        <StatTile label="Изменений за неделю" value={feed?.week.changes ?? 0} />
        <StatTile
          label="Требуют действий"
          value={feed?.week.actionsRequired ?? 0}
          tone={(feed?.week.actionsRequired ?? 0) > 0 ? 'sanction' : 'default'}
          hint={feed?.week.nearestDeadline ? `ближайший срок ${formatDate(feed.week.nearestDeadline)}` : undefined}
        />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        {/* Портфель */}
        <section className="min-w-0">
          <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            Портфель
          </h2>
          {feed && feed.portfolio.length > 0 ? (
            <div className="mt-3 space-y-3">
              {feed.portfolio.map((item) => (
                <PortfolioCard key={item.productId} item={item} />
              ))}
            </div>
          ) : (
            <BCard className="mt-3 p-6 text-sm text-muted-foreground">
              {ru.cabinet.portfolioEmpty.text}
            </BCard>
          )}
        </section>

        {/* Лента изменений */}
        <section className="min-w-0">
          <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            {ru.cabinet.feedTitle}
          </h2>
          {feed && feed.items.length > 0 ? (
            <div className="mt-3 space-y-3">
              {feed.items.map((c) => (
                <FeedCard key={c.id} card={c} />
              ))}
            </div>
          ) : (
            <BCard className="mt-3 p-6 text-sm text-muted-foreground">{ru.cabinet.feedQuiet}</BCard>
          )}
        </section>
      </div>
    </div>
  )
}

function PortfolioCard({ item }: { item: PortfolioItem }) {
  return (
    <Link to={`/b/product/${item.productId}`} className="group block">
      <BCard className="flex items-center gap-3 p-4 transition-colors group-hover:border-primary/40">
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold tracking-tight">{item.displayName}</p>
          <p className="mt-0.5 font-mono text-xs text-muted-foreground">
            {formatHsCode(item.hsCode)}
          </p>
        </div>
        {item.unreadCount > 0 && (
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
            {ru.cabinet.unreadShort(item.unreadCount)}
          </span>
        )}
        <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
      </BCard>
    </Link>
  )
}

const importanceTone: Record<ChangeCard['importance'], string> = {
  high: 'bg-sanction/10 text-sanction',
  medium: 'bg-primary/10 text-primary',
  low: 'bg-secondary text-muted-foreground',
}

function FeedCard({ card }: { card: ChangeCard }) {
  return (
    <BCard className={cn('p-4', card.isDraftNpa && 'opacity-70')}>
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-muted-foreground">
          {card.productName}
          {card.stageName ? ` · ${card.stageName}` : ''}
        </span>
        <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium', importanceTone[card.importance])}>
          {card.isDraftNpa ? ru.cabinet.draftNpa : ru.cabinet.importance[card.importance]}
        </span>
      </div>
      <h3 className="mt-1.5 text-[15px] font-semibold tracking-tight">{card.title}</h3>
      {(card.was || card.now) && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {card.was && (
            <div className="rounded-lg bg-secondary/50 p-2.5">
              <p className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                {ru.requirement.card.was}
              </p>
              <p className="mt-1 text-sm line-through decoration-sanction/40">{card.was}</p>
            </div>
          )}
          {card.now && (
            <div className="rounded-lg bg-primary/[0.07] p-2.5 ring-1 ring-inset ring-primary/15">
              <p className="text-[10px] font-semibold tracking-wide text-primary uppercase">
                {ru.requirement.card.now}
              </p>
              <p className="mt-1 text-sm font-medium">{card.now}</p>
            </div>
          )}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="font-mono">{formatDate(card.date)}</span>
        {card.effectiveDate && <span>· вступает {formatDate(card.effectiveDate)}</span>}
        {card.action && !card.inFavor && (
          <span className="font-medium text-foreground">· {ru.cabinet.whatToDo}: {card.action}</span>
        )}
        {card.inFavor && <span className="text-positive">· {ru.cabinet.inFavor}</span>}
        {card.requirementId && (
          <Link
            to={`/b/product/${card.productId}?req=${card.requirementId}`}
            className="text-primary hover:underline"
          >
            {ru.cabinet.toRequirement} →
          </Link>
        )}
      </div>
    </BCard>
  )
}
