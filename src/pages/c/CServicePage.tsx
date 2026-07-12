import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowUpRight, BadgeCheck, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useServiceBundle } from '@/data/hooks'
import type { StageInfo } from '@/data/types'
import { inProgressStageIds, productLinkForService } from '@/data/cross-links'
import { formatDate } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CCard, CEyebrow, CLockedValue, CStatTile, CountUp } from './ui'
import { ComplexityMeter } from './CProductPage'
import { CRequirementList } from './CRequirementList'

/**
 * Досье услуги в дизайне C — зеркало досье товара. Формула паспорта:
 * режим допуска × 6 этапов жизни бизнеса. Вместо нити операций слева —
 * нить этапов (у услуги нет транспорта и таможенных процедур).
 */
export function CServicePage() {
  const { serviceId } = useParams<{ serviceId: string }>()
  const { data, isLoading, isError } = useServiceBundle(serviceId)

  const inProgress = useMemo(
    () => (serviceId ? inProgressStageIds(serviceId) : new Set<string>()),
    [serviceId],
  )
  const crossLink = serviceId ? productLinkForService(serviceId) : null

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-8">
        <Skeleton className="h-9 w-72" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-72 w-full" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-24 sm:px-8">
        <h1 className="font-display text-2xl font-medium tracking-tight">
          {isError ? ru.common.error : ru.service.notFound}
        </h1>
        <Button nativeButton={false} render={<Link to="/catalog" />} variant="outline" className="mt-5">
          <ArrowLeft />
          {ru.common.back}
        </Button>
      </div>
    )
  }

  const { passport, rows, stages, metrics } = data

  return (
    <div className="mx-auto max-w-6xl px-4 py-7 sm:px-8">
      <Link
        to="/catalog"
        className="inline-flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" />
        {ru.common.registry}
      </Link>

      {/* Паспорт услуги */}
      <div className="mt-4 min-w-0">
        <CEyebrow>{ru.service.eyebrow}</CEyebrow>
        <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight text-balance sm:text-[30px]">
          {passport.displayName}
        </h1>
        <div className="mt-3.5 flex flex-wrap items-center gap-2">
          {passport.admissionMode && (
            <span
              title={ru.service.admissionHint[passport.admissionMode]}
              className="inline-flex items-center gap-1.5 rounded-md border border-brass/45 bg-brass/10 px-2.5 py-1 font-mono text-[11px] font-medium tracking-[0.05em] text-brass uppercase"
            >
              <BadgeCheck className="size-3.5" />
              {ru.service.admission[passport.admissionMode]}
            </span>
          )}
          {passport.okedCode && (
            <span className="rounded-md bg-secondary px-2.5 py-1 font-mono text-xs text-secondary-foreground">
              {ru.service.okedLabel} {passport.okedCode}
            </span>
          )}
          {passport.ikpuCode && (
            <span className="rounded-md bg-secondary px-2.5 py-1 font-mono text-xs text-secondary-foreground">
              {ru.product.ikpuLabel} {passport.ikpuCode}
            </span>
          )}
          {passport.complexity != null && <ComplexityMeter value={passport.complexity} />}
          {passport.verifiedAt && (
            <span className="inline-flex items-center gap-1.5 rounded-md border border-positive/40 px-2.5 py-1 font-mono text-[11px] font-medium tracking-[0.05em] text-positive uppercase">
              <Check className="size-3.5" />
              {ru.product.checkedStamp(formatDate(passport.verifiedAt))}
            </span>
          )}
        </div>
        {passport.authorityName && (
          <p className="mt-2.5 text-sm text-muted-foreground">
            {ru.service.authorityLabel[passport.admissionMode ?? 'license']}:{' '}
            <span className="font-medium text-foreground">{passport.authorityName}</span>
          </p>
        )}
      </div>

      {/* Приборная панель */}
      <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <CStatTile
          index={0}
          label={ru.product.metrics.requirements}
          value={<CountUp value={metrics.requirements} />}
          tone="primary"
        />
        <CStatTile
          index={1}
          label={ru.product.metrics.documents}
          value={
            metrics.documents.state === 'ok' ? (
              <CountUp value={metrics.documents.value} />
            ) : (
              <CLockedValue />
            )
          }
        />
        <CStatTile
          index={2}
          label={ru.product.metrics.maxSanction}
          value={metrics.maxSanction.state === 'ok' ? metrics.maxSanction.value : <CLockedValue />}
          tone={metrics.maxSanction.state === 'ok' ? 'sanction' : 'default'}
        />
        <CStatTile
          index={3}
          label={ru.product.metrics.changes30d}
          value={<CountUp value={metrics.changes30d} />}
          tone={metrics.changes30d > 0 ? 'primary' : 'default'}
          hint={metrics.changes30d === 0 ? ru.product.quiet30d : undefined}
        />
      </div>

      {/* Кросс-ссылка: у товара, который продаёт эта услуга, — свой паспорт */}
      {crossLink && (
        <Link to={crossLink.to} className="group mt-5 block focus-visible:outline-none">
          <CCard className="flex items-center gap-4 p-4 transition-colors group-hover:border-primary/40 group-focus-visible:ring-2 group-focus-visible:ring-ring">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold tracking-tight">{crossLink.title}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                {crossLink.text}
              </p>
            </div>
            <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary">
              {ru.service.crossCta}
              <ArrowUpRight className="size-3.5 transition-transform duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </span>
          </CCard>
        </Link>
      )}

      {rows.length === 0 ? (
        <CCard className="mt-9 p-8 text-center">
          <h2 className="text-lg font-semibold tracking-tight">
            {ru.service.noRequirementsTitle}
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
            {ru.service.noRequirementsText}
          </p>
        </CCard>
      ) : (
        <div className="mt-9 grid gap-7 lg:grid-cols-[240px_minmax(0,1fr)]">
          <aside className="hidden lg:sticky lg:top-8 lg:block lg:self-start">
            <CServiceStageNav stages={stages} />
          </aside>

          <div className="min-w-0">
            <div className="lg:hidden">
              <CServiceStageNavMobile stages={stages} />
            </div>

            <div className="mt-5 flex flex-wrap items-baseline justify-between gap-3 lg:mt-0">
              <h2 className="text-lg font-semibold tracking-tight">
                {ru.service.routeTitle}
                <span className="ml-2 font-mono text-sm font-normal text-muted-foreground tabular-nums">
                  {rows.length}
                </span>
              </h2>
            </div>

            <div className="mt-4">
              <CRequirementList
                rows={rows}
                stages={stages}
                initialRequirementId={rows[0]?.id}
                inProgressStageIds={inProgress}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function scrollToStage(stageId: string) {
  // scrollIntoView/smooth в этом лейауте прерываются (scroll anchoring) —
  // считаем позицию сами и скроллим мгновенно
  const el = document.getElementById(`stage-${stageId}`)
  if (!el) return
  const top = window.scrollY + el.getBoundingClientRect().top - 88 // ≈ scroll-mt-24
  window.scrollTo({ top: Math.max(0, top) })
}

/** Нить этапов жизни бизнеса — станции маршрута услуги (вместо операций товара) */
function CServiceStageNav({ stages }: { stages: StageInfo[] }) {
  const [active, setActive] = useState<string | null>(null)
  return (
    <nav aria-label={ru.service.routeSubtitle} className="relative">
      <span
        aria-hidden
        className="c-thread absolute top-3 bottom-3 left-[13px] w-px bg-gradient-to-b from-primary/60 via-primary/35 to-primary/60"
      />
      <p className="pl-9 font-mono text-[10px] font-medium tracking-[0.12em] text-muted-foreground uppercase">
        {ru.service.routeSubtitle}
      </p>
      <ul className="mt-1.5 space-y-0.5">
        {stages.map((stage, i) => {
          const isActive = active === stage.id
          return (
            <li key={stage.id} className="c-station" style={{ '--i': i } as React.CSSProperties}>
              <button
                type="button"
                aria-current={isActive ? 'true' : undefined}
                onClick={() => {
                  setActive(stage.id)
                  scrollToStage(stage.id)
                }}
                className={cn(
                  'group relative flex w-full items-center gap-2.5 rounded-lg py-2 pr-2.5 pl-9 text-left text-sm transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                  isActive
                    ? 'bg-accent font-semibold text-accent-foreground'
                    : 'text-foreground/80 hover:bg-secondary/60 hover:text-foreground',
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    'absolute top-1/2 left-[8.5px] size-[10px] -translate-y-1/2 rounded-full border-2 bg-card transition-all',
                    isActive
                      ? 'scale-110 border-primary bg-primary ring-4 ring-primary/15'
                      : 'border-primary/50 group-hover:border-primary',
                  )}
                />
                <span
                  className={cn(
                    'font-mono text-[11px] font-semibold tabular-nums',
                    isActive ? 'text-primary' : 'text-muted-foreground',
                  )}
                >
                  {i + 1}
                </span>
                <span className="min-w-0 flex-1 truncate">{stage.name}</span>
                <span
                  className={cn(
                    'font-mono text-[11px] tabular-nums',
                    isActive ? 'font-medium text-primary' : 'text-muted-foreground',
                  )}
                >
                  {stage.count}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

/** Мобильная версия маршрута услуги: горизонтальные станции-чипы */
function CServiceStageNavMobile({ stages }: { stages: StageInfo[] }) {
  const [active, setActive] = useState<string | null>(null)
  return (
    <div className="-mx-4 overflow-x-auto px-4">
      <div className="flex w-max gap-1.5">
        {stages.map((stage, i) => {
          const isActive = active === stage.id
          return (
            <button
              key={stage.id}
              type="button"
              aria-pressed={isActive}
              onClick={() => {
                setActive(stage.id)
                scrollToStage(stage.id)
              }}
              className={cn(
                'flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[13px] font-medium transition-colors',
                isActive
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border bg-card text-muted-foreground',
              )}
            >
              <span className="font-mono text-[11px] tabular-nums opacity-75">{i + 1}</span>
              {stage.name}
              <span className="font-mono text-[11px] tabular-nums opacity-75">{stage.count}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
