import { useMemo, useState } from 'react'
import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom'
import { Check, Lock, Plus } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import {
  useProductBundle,
  useFollowProduct,
  usePortfolioIds,
} from '@/data/hooks'
import { useAuth } from '@/app/auth'
import type { Operation, TransportType } from '@/data/types'
import {
  buildOperationNodes,
  filterRows,
  stagesOf,
  operationMeta,
  transportLabel,
  OPERATION_GROUPS,
} from '@/data/taxonomy'
import { formatHsCode } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { BCard, StatTile, OPERATION_ICON } from './ui'
import { BRequirementList } from './BRequirementList'

export function BProductPage() {
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
  const activeNode = nodes.find((n) => n.meta.key === activeOp)

  const filteredRows = useMemo(
    () => filterRows(rows, activeOp, transport),
    [rows, activeOp, transport],
  )
  const stages = useMemo(() => stagesOf(filteredRows), [filteredRows])

  if (isLoading) {
    return (
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
        <Skeleton className="h-8 w-72" />
        <div className="grid gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-24 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight">
          {isError ? ru.common.error : 'Товар не найден'}
        </h1>
        <Button nativeButton={false} render={<Link to="/b" />} variant="outline" className="mt-4">
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
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* Паспорт */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{passport.categoryName}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            {passport.displayName}
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            {passport.officialName}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="rounded-lg bg-secondary px-2.5 py-1 font-mono text-xs">
              {ru.product.hsLabel} {formatHsCode(passport.hsCode)}
            </span>
            {passport.complexity != null && (
              <span className="rounded-lg bg-secondary px-2.5 py-1 text-xs font-medium">
                {ru.product.complexity(passport.complexity)}
              </span>
            )}
            {passport.verifiedAt && (
              <span className="inline-flex items-center gap-1.5 rounded-lg bg-positive/10 px-2.5 py-1 text-xs font-medium text-positive">
                <Check className="size-3.5" />
                {ru.product.checkedStamp(formatDate(passport.verifiedAt))}
              </span>
            )}
          </div>
        </div>
        <FollowButton productId={passport.id} />
      </div>

      {/* Плитки метрик */}
      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label={ru.product.metrics.requirements} value={metrics.requirements} tone="primary" />
        <StatTile
          label={ru.product.metrics.documents}
          value={metrics.documents.state === 'ok' ? metrics.documents.value : <LockedValue />}
        />
        <StatTile
          label={ru.product.metrics.maxSanction}
          value={metrics.maxSanction.state === 'ok' ? metrics.maxSanction.value : <LockedValue />}
          tone={metrics.maxSanction.state === 'ok' ? 'sanction' : 'default'}
        />
        <StatTile
          label={ru.product.metrics.changes30d}
          value={metrics.changes30d}
          tone={metrics.changes30d > 0 ? 'primary' : 'default'}
        />
      </div>

      {rows.length === 0 ? (
        <BCard className="mt-8 p-8 text-center">
          <h2 className="text-lg font-semibold">{ru.product.noRequirementsTitle}</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            {ru.product.noRequirementsText}
          </p>
        </BCard>
      ) : (
        <div className="mt-8 grid gap-6 lg:grid-cols-[230px_minmax(0,1fr)]">
          {/* Сайдбар операций */}
          <aside className="lg:sticky lg:top-20 lg:self-start">
            <nav className="space-y-5">
              {OPERATION_GROUPS.map((group) => {
                const groupNodes = nodes.filter((n) => n.meta.group === group.key)
                if (groupNodes.length === 0) return null
                return (
                  <div key={group.key}>
                    <p className="px-2 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                      {group.title}
                    </p>
                    <div className="mt-2 space-y-1">
                      {groupNodes.map((node) => {
                        const Icon = OPERATION_ICON[node.meta.key]
                        const active = activeOp === node.meta.key
                        return (
                          <button
                            key={node.meta.key}
                            type="button"
                            onClick={() => selectOp(node.meta.key)}
                            title={node.meta.full}
                            className={cn(
                              'flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-sm transition-colors',
                              active
                                ? 'bg-primary text-primary-foreground shadow-sm'
                                : 'text-foreground hover:bg-secondary',
                            )}
                          >
                            <Icon className="size-4 shrink-0 opacity-90" />
                            <span className="min-w-0 flex-1 truncate text-left">
                              {node.meta.label}
                            </span>
                            <span
                              className={cn(
                                'font-mono text-[11px] tabular-nums',
                                active ? 'text-primary-foreground/80' : 'text-muted-foreground',
                              )}
                            >
                              {node.count}
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </nav>
          </aside>

          {/* Контент */}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-semibold tracking-tight">
                {operationMeta(activeOp).full}
                <span className="ml-2 font-mono text-sm font-normal text-muted-foreground">
                  {filteredRows.length}
                </span>
              </h2>
              {activeNode && activeNode.transports.length > 0 && (
                <div className="flex rounded-xl bg-secondary p-0.5">
                  <TransBtn label="Все" active={transport === null} onClick={() => setTransport(null)} />
                  {activeNode.transports.map((t) => (
                    <TransBtn
                      key={t}
                      label={transportLabel(t)}
                      active={transport === t}
                      onClick={() => setTransport(t)}
                    />
                  ))}
                </div>
              )}
            </div>

            <div className="mt-5">
              <BRequirementList
                key={`${activeOp}-${transport ?? 'all'}`}
                rows={filteredRows}
                stages={stages}
                activeStage={null}
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

function TransBtn({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'rounded-[10px] px-3 py-1.5 text-[13px] font-medium transition-colors',
        active ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {label}
    </button>
  )
}

function LockedValue() {
  return (
    <span className="inline-flex items-center gap-1 text-base text-muted-foreground">
      <Lock className="size-3.5" />
      <span className="tracking-widest">•••</span>
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
          navigate('/b/login')
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

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}
