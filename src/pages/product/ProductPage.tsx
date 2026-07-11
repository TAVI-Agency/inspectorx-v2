import { useMemo, useState } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { useContentRequest, useProductBundle } from '@/data/hooks'
import type { Operation, TransportType } from '@/data/types'
import { buildOperationNodes, filterRows, stagesOf } from '@/data/taxonomy'
import { ru } from '@/i18n/ru'
import { PassportHeader } from './PassportHeader'
import { MetricsStrip } from './MetricsStrip'
import { StageChips } from './StageChips'
import { RequirementList } from './RequirementList'
import { OperationNav, TransportSwitcher } from './OperationNav'

export function ProductPage() {
  const { productId } = useParams<{ productId: string }>()
  const [searchParams] = useSearchParams()
  const { data, isLoading, isError } = useProductBundle(productId)

  const rows = useMemo(() => data?.rows ?? [], [data])
  const nodes = useMemo(() => buildOperationNodes(rows), [rows])

  // Операция по умолчанию: из диплинка ?req=, иначе первая доступная
  const reqParam = searchParams.get('req')
  const deeplinkOp = reqParam
    ? rows.find((r) => r.id === reqParam)?.operation
    : undefined
  const defaultOp: Operation = deeplinkOp ?? nodes[0]?.meta.key ?? 'product'

  const [opState, setOpState] = useState<Operation | null>(null)
  const [transport, setTransport] = useState<TransportType | null>(null)
  const [activeStage, setActiveStage] = useState<string | null>(null)
  const activeOp = opState ?? defaultOp

  const activeNode = nodes.find((n) => n.meta.key === activeOp)
  const filteredRows = useMemo(
    () => filterRows(rows, activeOp, transport),
    [rows, activeOp, transport],
  )
  const stages = useMemo(() => stagesOf(filteredRows), [filteredRows])

  function selectOp(op: Operation) {
    setOpState(op)
    setTransport(null)
    setActiveStage(null)
  }
  function selectTransport(t: TransportType | null) {
    setTransport(t)
    setActiveStage(null)
  }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-9 w-96 max-w-full" />
        <Skeleton className="h-24 w-full" />
        <div className="space-y-3 pt-4">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight">
          {isError ? ru.common.error : 'Товар не найден'}
        </h1>
        <Button nativeButton={false} render={<Link to="/catalog" />} variant="outline" className="mt-4">
          {ru.common.back}
        </Button>
      </div>
    )
  }

  const { passport, metrics } = data
  // Диплинк раскрываем, если он попадает в текущую операцию; иначе — первую строку
  const deeplinkInView = reqParam && filteredRows.some((r) => r.id === reqParam)
  const initialRequirementId = deeplinkInView ? reqParam : filteredRows[0]?.id

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PassportHeader passport={passport} />
      <div className="mt-6">
        <MetricsStrip metrics={metrics} />
      </div>

      {rows.length === 0 ? (
        <EmptyRequirements productId={passport.id} />
      ) : (
        <>
          <div className="mt-8">
            <OperationNav nodes={nodes} active={activeOp} onChange={selectOp} />
          </div>

          {activeNode && activeNode.transports.length > 0 && (
            <div className="mt-5">
              <TransportSwitcher
                available={activeNode.transports}
                active={transport}
                onChange={selectTransport}
              />
            </div>
          )}

          {filteredRows.length === 0 ? (
            <p className="mt-8 rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
              По этому фильтру требований нет.
            </p>
          ) : (
            <>
              <div className="mt-6">
                <StageChips
                  stages={stages}
                  active={activeStage}
                  onChange={setActiveStage}
                  total={filteredRows.length}
                />
              </div>
              <div className="mt-6">
                <RequirementList
                  key={`${activeOp}-${transport ?? 'all'}`}
                  rows={filteredRows}
                  stages={stages}
                  activeStage={activeStage}
                  productId={passport.id}
                  initialRequirementId={initialRequirementId}
                  scrollToInitial={Boolean(deeplinkInView)}
                />
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

/** Товар без наполнения: честная пометка + заявка (§3b.3) */
function EmptyRequirements({ productId }: { productId: string }) {
  const request = useContentRequest()
  return (
    <div className="mt-10 rounded-lg border border-dashed p-8 text-center">
      <h2 className="text-lg font-semibold">{ru.product.noRequirementsTitle}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        {ru.product.noRequirementsText}
      </p>
      {request.isSuccess ? (
        <p className="mt-4 text-sm font-medium text-positive">{ru.product.notifyDone}</p>
      ) : (
        <Button
          className="mt-4"
          size="sm"
          disabled={request.isPending}
          onClick={() =>
            request.mutate({
              kind: 'fill_product',
              productId: productId.startsWith('mock-') ? undefined : productId,
            })
          }
        >
          {ru.product.notifyWhenReady}
        </Button>
      )}
    </div>
  )
}
