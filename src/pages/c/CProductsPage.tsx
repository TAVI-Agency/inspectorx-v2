import { Link } from 'react-router-dom'
import { ArrowRight, Bell, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { useChangeFeed, usePortfolioIds } from '@/data/hooks'
import type { PortfolioItem } from '@/data/types'
import { formatDate, formatHsCode, pluralize } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CCard, CEyebrow } from './ui'

/** Мои товары: портфель как сетка карточек, сводка недели одной строкой. */
export function CProductsPage() {
  const { session } = useAuth()
  const { mockSubscriber } = useAppMode()
  const { data: portfolio } = usePortfolioIds()
  const ids = portfolio?.ids ?? []
  const { data: feed } = useChangeFeed(ids.length > 0 ? ids : undefined)

  if (!session && !mockSubscriber) return <CLoginCard />

  const week = feed?.week

  return (
    <div className="mx-auto max-w-6xl px-4 py-7 sm:px-8">
      <CEyebrow>Портфель</CEyebrow>
      <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight sm:text-[30px]">
        {ru.products.title}
      </h1>
      {week && (
        <p className="mt-2 text-sm text-muted-foreground">
          {ru.cabinet.weekSummary(
            pluralize(week.changes, 'изменение', 'изменения', 'изменений'),
            week.actionsRequired,
            week.nearestDeadline ? formatDate(week.nearestDeadline) : '',
          )}
          {week.changes > 0 && (
            <>
              {' · '}
              <Link to="/changes" className="font-medium text-primary underline-offset-2 hover:underline">
                {ru.products.weekLink}
              </Link>
            </>
          )}
        </p>
      )}

      {feed && feed.portfolio.length > 0 ? (
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {feed.portfolio.map((item, i) => (
            <CProductCard key={item.productId} item={item} index={i} />
          ))}
          <CAddTile index={feed.portfolio.length} />
        </div>
      ) : (
        <CCard className="mx-auto mt-10 max-w-md p-8 text-center">
          <p className="text-[15px] font-semibold tracking-tight">{ru.cabinet.portfolioEmpty.title}</p>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {ru.cabinet.portfolioEmpty.text}
          </p>
          <Button className="mt-5" nativeButton={false} render={<Link to="/catalog" />}>
            {ru.cabinet.portfolioEmpty.cta}
          </Button>
        </CCard>
      )}
    </div>
  )
}

const STATUS_TONE: Record<PortfolioItem['statusKind'], string> = {
  deadline: 'bg-sanction',
  noAction: 'bg-positive',
  quiet: 'bg-muted-foreground/40',
}

/** ОДНА строка статуса: дедлайн / в вашу пользу / без действий / тишина */
function statusText(item: PortfolioItem): string {
  if (item.statusKind === 'deadline')
    return ru.products.status.deadline(
      pluralize(Math.max(item.recentCount, 1), 'изменение', 'изменения', 'изменений'),
      formatDate(item.statusLine),
    )
  if (item.statusKind === 'noAction' && item.allInFavor)
    return ru.products.status.inFavor(
      pluralize(item.recentCount, 'изменение', 'изменения', 'изменений'),
    )
  if (item.statusKind === 'noAction') return ru.products.status.noAction
  return ru.products.status.quiet
}

function CProductCard({ item, index }: { item: PortfolioItem; index: number }) {
  return (
    <Link to={`/product/${item.productId}`} className="group block focus-visible:outline-none">
      <CCard
        className="c-rise flex h-full flex-col p-4 transition-all duration-300 group-hover:-translate-y-0.5 group-hover:border-primary/40 group-focus-visible:ring-2 group-focus-visible:ring-ring"
        style={{ '--i': index } as React.CSSProperties}
      >
        <div className="flex items-start justify-between gap-2">
          <p className="min-w-0 truncate text-[15px] font-semibold tracking-tight">
            {item.displayName}
          </p>
          {item.unreadCount > 0 && (
            <span className="shrink-0 rounded-md bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
              {ru.cabinet.unreadShort(item.unreadCount)}
            </span>
          )}
        </div>
        <p className="mt-1 font-mono text-xs text-muted-foreground">{formatHsCode(item.hsCode)}</p>
        <p className="mt-3 flex items-center gap-1.5 border-t border-border pt-3 text-xs text-muted-foreground">
          <span className={cn('size-1.5 shrink-0 rounded-full', STATUS_TONE[item.statusKind])} />
          <span className="truncate">{statusText(item)}</span>
          <ArrowRight className="ml-auto size-3.5 shrink-0 transition-transform duration-300 group-hover:translate-x-0.5 group-hover:text-primary" />
        </p>
      </CCard>
    </Link>
  )
}

function CAddTile({ index }: { index: number }) {
  return (
    <Link to="/catalog" className="group block focus-visible:outline-none">
      <div
        className="c-rise flex h-full min-h-[124px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-input p-4 text-center transition-colors group-hover:border-primary/50 group-hover:bg-accent/30 group-focus-visible:ring-2 group-focus-visible:ring-ring"
        style={{ '--i': index } as React.CSSProperties}
      >
        <span className="grid size-9 place-items-center rounded-full bg-secondary text-muted-foreground transition-colors group-hover:bg-primary/10 group-hover:text-primary">
          <Plus className="size-4.5" />
        </span>
        <p className="text-sm font-medium">{ru.products.addTile}</p>
        <p className="text-xs text-muted-foreground">{ru.products.addTileHint}</p>
      </div>
    </Link>
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
