import { Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { useChangeFeed, usePortfolioIds } from '@/data/hooks'
import type { PortfolioItem } from '@/data/types'
import { ru } from '@/i18n/ru'
import { formatDate, formatHsCode, pluralize } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ChangeCardItem } from './ChangeCardItem'
import { DigestSettings } from './DigestSettings'

export function CabinetPage() {
  const { session, loading } = useAuth()
  const { mockSubscriber } = useAppMode()
  const { data: portfolio, isLoading: idsLoading } = usePortfolioIds()
  const feed = useChangeFeed(portfolio?.ids)

  if (loading || idsLoading) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 px-4 py-8 sm:px-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  // Ни входа, ни демо-режима — приглашаем войти
  if (!session && !mockSubscriber) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-24 text-center sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight">{ru.cabinet.title}</h1>
        <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
          {ru.auth.loginRequired}
        </p>
        <div className="mt-5 flex justify-center gap-2">
          <Button nativeButton={false} render={<Link to="/login" />} size="sm">
            {ru.common.signIn}
          </Button>
          <Button
            nativeButton={false}
            render={<Link to="/register" />}
            variant="outline"
            size="sm"
          >
            {ru.common.register}
          </Button>
        </div>
      </div>
    )
  }

  const ids = portfolio?.ids ?? []

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <header className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">{ru.cabinet.title}</h1>
        {feed.data && feed.data.week.changes > 0 && (
          <p className="text-sm text-muted-foreground">
            {ru.cabinet.weekSummary(
              pluralize(feed.data.week.changes, 'изменение', 'изменения', 'изменений'),
              feed.data.week.actionsRequired,
              formatDate(feed.data.week.nearestDeadline),
            )}
          </p>
        )}
      </header>

      {ids.length === 0 ? (
        <EmptyPortfolio />
      ) : (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(feed.data?.portfolio ?? []).map((item) => (
              <PortfolioCard key={item.productId} item={item} />
            ))}
          </div>

          <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,1fr)_300px]">
            <section aria-label={ru.cabinet.feedTitle} className="min-w-0">
              <h2 className="font-mono text-[11px] tracking-[0.1em] uppercase">
                {ru.cabinet.feedTitle}
              </h2>
              {feed.data && feed.data.items.length === 0 && (
                <p className="mt-4 rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                  {ru.cabinet.feedQuiet}
                </p>
              )}
              <ul className="mt-3 space-y-3">
                {(feed.data?.items ?? []).map((card) => (
                  <ChangeCardItem key={card.id} card={card} />
                ))}
              </ul>
            </section>
            <div className="lg:sticky lg:top-16 lg:self-start">
              <DigestSettings />
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function PortfolioCard({ item }: { item: PortfolioItem }) {
  return (
    <Link
      to={`/product/${item.productId}`}
      className="group rounded-lg border bg-paper p-4 transition-colors hover:border-foreground/25 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-semibold">{item.displayName}</span>
        {item.unreadCount > 0 && (
          <span className="shrink-0 rounded-full bg-primary/12 px-2 py-0.5 text-[11px] font-medium text-primary">
            {ru.cabinet.unreadShort(item.unreadCount)}
          </span>
        )}
      </div>
      <p className="mt-1 font-mono text-xs text-muted-foreground">
        {formatHsCode(item.hsCode)}
      </p>
      <p
        className={cn(
          'mt-3 text-xs',
          item.statusKind === 'deadline' ? 'font-medium text-primary' : 'text-muted-foreground',
        )}
      >
        {item.statusKind === 'deadline' &&
          ru.cabinet.productStatus.deadline(formatDate(item.statusLine))}
        {item.statusKind === 'noAction' && ru.cabinet.productStatus.noAction}
        {item.statusKind === 'quiet' && ru.cabinet.productStatus.quiet}
      </p>
    </Link>
  )
}

/** Новый пользователь без товаров */
function EmptyPortfolio() {
  return (
    <div className="mt-10 rounded-lg border border-dashed p-10 text-center">
      <h2 className="text-lg font-semibold">{ru.cabinet.portfolioEmpty.title}</h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
        {ru.cabinet.portfolioEmpty.text}
      </p>
      <Button className="mt-5" size="sm" nativeButton={false} render={<Link to="/" />}>
        <Search />
        {ru.cabinet.portfolioEmpty.cta}
      </Button>
    </div>
  )
}
