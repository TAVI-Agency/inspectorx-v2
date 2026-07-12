import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Check, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/app/auth'
import {
  useFollowProduct,
  usePortfolioIds,
  useProductBundle,
} from '@/data/hooks'
import type { Operation, TransportType } from '@/data/types'
import {
  buildOperationNodes,
  filterRows,
  operationMeta,
  stagesOf,
} from '@/data/taxonomy'
import { formatDate, formatHsCode } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CCard, CEyebrow, CLockedValue, CStatTile, CountUp } from './ui'
import { CRouteNav, CRouteNavMobile } from './CRouteNav'
import { CRequirementList } from './CRequirementList'

/**
 * Досье товара в дизайне C: паспорт → приборные метрики → маршрут
 * (операции слева, этапы нитью в списке справа).
 */
export function CProductPage() {
  const { productId } = useParams<{ productId: string }>()
  const [searchParams] = useSearchParams()
  const { data, isLoading, isError } = useProductBundle(productId)

  const rows = useMemo(() => data?.rows ?? [], [data])
  const nodes = useMemo(() => buildOperationNodes(rows), [rows])

  const reqParam = searchParams.get('req')
  const deeplinkOp = reqParam ? rows.find((r) => r.id === reqParam)?.operation : undefined
  const defaultOp: Operation = deeplinkOp ?? nodes[0]?.meta.key ?? 'product'

  const [opState, setOpState] = useState<Operation | null>(null)
  const [transport, setTransport] = useState<TransportType | null>(null)
  const activeOp = opState ?? defaultOp

  const filteredRows = useMemo(
    () => filterRows(rows, activeOp, transport),
    [rows, activeOp, transport],
  )
  const stages = useMemo(() => stagesOf(filteredRows), [filteredRows])

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
          {isError ? ru.common.error : 'Товар не найден'}
        </h1>
        <Button nativeButton={false} render={<Link to="/catalog" />} variant="outline" className="mt-5">
          <ArrowLeft />
          {ru.common.back}
        </Button>
      </div>
    )
  }

  const { passport, metrics } = data
  const deeplinkInView = reqParam && filteredRows.some((r) => r.id === reqParam)
  const initialRequirementId = deeplinkInView ? reqParam : filteredRows[0]?.id

  function selectOp(op: Operation) {
    setOpState(op)
    setTransport(null)
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-7 sm:px-8">
      <Link
        to="/catalog"
        className="inline-flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" />
        {ru.common.registry}
      </Link>

      {/* Паспорт товара */}
      <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          {passport.categoryName && (
            <CEyebrow className="line-clamp-1 max-w-2xl" title={passport.categoryName}>
              {passport.categoryName}
            </CEyebrow>
          )}
          <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight text-balance sm:text-[30px]">
            {passport.displayName}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            {passport.officialName}
          </p>
          <div className="mt-3.5 flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-secondary px-2.5 py-1 font-mono text-xs text-secondary-foreground">
              {ru.product.hsLabel} {formatHsCode(passport.hsCode)}
            </span>
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
        </div>
        <FollowButton productId={passport.id} />
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

      {rows.length === 0 ? (
        <CCard className="mt-9 p-8 text-center">
          <h2 className="text-lg font-semibold tracking-tight">
            {ru.product.noRequirementsTitle}
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
            {ru.product.noRequirementsText}
          </p>
        </CCard>
      ) : (
        <div className="mt-9 grid gap-7 lg:grid-cols-[240px_minmax(0,1fr)]">
          <aside className="hidden lg:sticky lg:top-8 lg:block lg:self-start">
            <CRouteNav
              nodes={nodes}
              activeOp={activeOp}
              transport={transport}
              onSelectOp={selectOp}
              onSelectTransport={setTransport}
            />
          </aside>

          <div className="min-w-0">
            <div className="lg:hidden">
              <CRouteNavMobile
                nodes={nodes}
                activeOp={activeOp}
                transport={transport}
                onSelectOp={selectOp}
                onSelectTransport={setTransport}
              />
            </div>

            <div className="mt-5 flex flex-wrap items-baseline justify-between gap-3 lg:mt-0">
              <h2 className="text-lg font-semibold tracking-tight">
                {operationMeta(activeOp).full}
                <span className="ml-2 font-mono text-sm font-normal text-muted-foreground tabular-nums">
                  {filteredRows.length}
                </span>
              </h2>
            </div>

            <div className="mt-4">
              <CRequirementList
                key={`${activeOp}-${transport ?? 'all'}`}
                rows={filteredRows}
                stages={stages}
                productId={passport.id}
                initialRequirementId={initialRequirementId}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** Индекс сложности: 10 делений-рисок, как на приборе */
function ComplexityMeter({ value }: { value: number }) {
  return (
    <span
      className="inline-flex items-center gap-2 rounded-md bg-secondary px-2.5 py-1"
      title={`${ru.product.complexityLabel}: ${value}/10`}
    >
      <span className="flex items-end gap-[2px]" aria-hidden>
        {Array.from({ length: 10 }, (_, i) => (
          <span
            key={i}
            className={cn(
              'w-[3px] rounded-full',
              i % 3 === 0 ? 'h-3' : 'h-2',
              i < value ? 'bg-primary' : 'bg-foreground/15',
            )}
          />
        ))}
      </span>
      <span className="font-mono text-xs text-secondary-foreground tabular-nums">
        {value}/10
      </span>
    </span>
  )
}

function FollowButton({ productId }: { productId: string }) {
  const { session } = useAuth()
  const navigate = useNavigate()
  const follow = useFollowProduct()
  const { data: portfolio } = usePortfolioIds()
  const followed = portfolio?.ids.includes(productId) ?? false

  if (followed) {
    return (
      <Button variant="secondary" size="sm" disabled className="shrink-0">
        <Check className="size-4" />
        {ru.product.followedCta}
      </Button>
    )
  }
  return (
    <Button
      size="sm"
      className="shrink-0"
      disabled={follow.isPending}
      onClick={() => {
        if (!session) {
          navigate('/login')
          return
        }
        follow.mutate(productId)
      }}
    >
      <Plus className="size-4" />
      {ru.product.followCta}
    </Button>
  )
}
