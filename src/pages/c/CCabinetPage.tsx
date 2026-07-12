import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Bell, Check, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { useChangeFeed, useMarkChangeRead, usePortfolioIds } from '@/data/hooks'
import type { ChangeCard, PortfolioItem } from '@/data/types'
import {
  loadDigestSettings,
  saveDigestSettings,
  type DigestSettings as Digest,
} from '@/data/mock/read-store'
import { daysUntil, formatDate, formatHsCode, pluralize } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CCard, CEyebrow, CStatTile, CountUp } from './ui'

/**
 * Кабинет: пульт слежения. Портфель товаров слева, лента изменений — станции
 * на нити времени (та же метафора маршрута), дайджест-настройки.
 */
export function CCabinetPage() {
  const { session } = useAuth()
  const { mockSubscriber } = useAppMode()
  const { data: portfolio } = usePortfolioIds()
  const ids = portfolio?.ids ?? []
  const { data: feed } = useChangeFeed(ids.length > 0 ? ids : undefined)

  if (!session && !mockSubscriber) {
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

  const week = feed?.week

  return (
    <div className="mx-auto max-w-6xl px-4 py-7 sm:px-8">
      <CEyebrow>Пульт слежения</CEyebrow>
      <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight sm:text-[30px]">
        {ru.cabinet.title}
      </h1>
      {week && (
        <p className="mt-2 text-sm text-muted-foreground">
          {ru.cabinet.weekSummary(
            pluralize(week.changes, 'изменение', 'изменения', 'изменений'),
            week.actionsRequired,
            week.nearestDeadline ? formatDate(week.nearestDeadline) : '',
          )}
        </p>
      )}

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <CStatTile index={0} label="Товаров в портфеле" value={<CountUp value={ids.length} />} tone="primary" />
        <CStatTile index={1} label="Изменений за неделю" value={<CountUp value={week?.changes ?? 0} />} />
        <CStatTile
          index={2}
          label="Требуют действий"
          value={<CountUp value={week?.actionsRequired ?? 0} />}
          tone={(week?.actionsRequired ?? 0) > 0 ? 'sanction' : 'positive'}
          hint={
            week?.nearestDeadline
              ? `ближайший срок ${formatDate(week.nearestDeadline)}`
              : undefined
          }
        />
      </div>

      <div className="mt-9 grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <section className="min-w-0 space-y-6">
          <div>
            <CEyebrow>Портфель</CEyebrow>
            {feed && feed.portfolio.length > 0 ? (
              <div className="mt-3 space-y-2.5">
                {feed.portfolio.map((item, i) => (
                  <CPortfolioCard key={item.productId} item={item} index={i} />
                ))}
              </div>
            ) : (
              <CCard className="mt-3 p-6">
                <p className="text-sm font-medium">{ru.cabinet.portfolioEmpty.title}</p>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                  {ru.cabinet.portfolioEmpty.text}
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-4"
                  nativeButton={false}
                  render={<Link to="/catalog" />}
                >
                  {ru.cabinet.portfolioEmpty.cta}
                </Button>
              </CCard>
            )}
          </div>

          <CDigestSettings />
        </section>

        <section className="min-w-0">
          <CEyebrow>{ru.cabinet.feedTitle}</CEyebrow>
          {feed && feed.items.length > 0 ? (
            <div className="relative mt-3">
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
            <CCard className="mt-3 p-6 text-sm text-muted-foreground">
              {ru.cabinet.feedQuiet}
            </CCard>
          )}
        </section>
      </div>
    </div>
  )
}

const STATUS_TONE: Record<PortfolioItem['statusKind'], string> = {
  deadline: 'bg-sanction',
  noAction: 'bg-positive',
  quiet: 'bg-muted-foreground/40',
}

function CPortfolioCard({ item, index }: { item: PortfolioItem; index: number }) {
  const statusText =
    item.statusKind === 'deadline'
      ? ru.cabinet.productStatus.deadline(formatDate(item.statusLine))
      : item.statusKind === 'noAction'
        ? ru.cabinet.productStatus.noAction
        : ru.cabinet.productStatus.quiet

  return (
    <Link to={`/product/${item.productId}`} className="group block focus-visible:outline-none">
      <CCard
        className="c-rise flex items-center gap-3.5 p-4 transition-all duration-300 group-hover:-translate-y-0.5 group-hover:border-primary/40 group-focus-visible:ring-2 group-focus-visible:ring-ring"
        style={{ '--i': index } as React.CSSProperties}
      >
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-semibold tracking-tight">{item.displayName}</p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
            <span className="font-mono">{formatHsCode(item.hsCode)}</span>
            <span className="inline-flex items-center gap-1.5">
              <span className={cn('size-1.5 rounded-full', STATUS_TONE[item.statusKind])} />
              {statusText}
            </span>
          </p>
        </div>
        {item.unreadCount > 0 && (
          <span className="shrink-0 rounded-md bg-primary/10 px-2 py-1 text-xs font-semibold text-primary">
            {ru.cabinet.unreadShort(item.unreadCount)}
          </span>
        )}
        <ArrowRight className="size-4 shrink-0 text-muted-foreground transition-transform duration-300 group-hover:translate-x-0.5 group-hover:text-primary" />
      </CCard>
    </Link>
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

        {card.action && !card.inFavor && (
          <p className="mt-2.5 rounded-lg border border-border bg-background/60 px-3 py-2 text-[13px] leading-relaxed">
            <span className="font-semibold">{ru.cabinet.whatToDo}:</span> {card.action}
          </p>
        )}

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

/** Настройка дайджеста: как присылать изменения (мок, localStorage) */
function CDigestSettings() {
  const [settings, setSettings] = useState<Digest>(loadDigestSettings)
  const [savedFlash, setSavedFlash] = useState(false)

  useEffect(() => {
    if (!savedFlash) return
    const t = setTimeout(() => setSavedFlash(false), 2000)
    return () => clearTimeout(t)
  }, [savedFlash])

  function update(patch: Partial<Digest>) {
    const next = { ...settings, ...patch }
    setSettings(next)
    saveDigestSettings(next)
    setSavedFlash(true)
  }

  return (
    <CCard className="p-4 sm:p-5">
      <h2 className="text-sm font-semibold tracking-tight">{ru.cabinet.digestTitle}</h2>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{ru.cabinet.digestText}</p>
      <div className="mt-3.5 space-y-3">
        <label className="flex items-center gap-3 text-sm">
          <Switch
            size="sm"
            checked={settings.email}
            onCheckedChange={(v) => update({ email: v })}
          />
          {ru.cabinet.digestEmail}
        </label>
        <label className="flex items-center gap-3 text-sm">
          <Switch
            size="sm"
            checked={settings.telegram}
            onCheckedChange={(v) => update({ telegram: v })}
          />
          {ru.cabinet.digestTelegram}
        </label>
      </div>
      <p
        aria-live="polite"
        className={cn(
          'mt-2.5 text-xs text-positive transition-opacity duration-300',
          savedFlash ? 'opacity-100' : 'opacity-0',
        )}
      >
        {ru.cabinet.digestSaved}
      </p>
    </CCard>
  )
}
