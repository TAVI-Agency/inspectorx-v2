import { useState } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { useContentRequest, useProductBundle } from '@/data/hooks'
import { ru } from '@/i18n/ru'
import { PassportHeader } from './PassportHeader'
import { MetricsStrip } from './MetricsStrip'
import { StageChips } from './StageChips'
import { RequirementList } from './RequirementList'

export function ProductPage() {
  const { productId } = useParams<{ productId: string }>()
  const [searchParams] = useSearchParams()
  const { data, isLoading, isError } = useProductBundle(productId)
  const [activeStage, setActiveStage] = useState<string | null>(null)

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

  const { passport, rows, stages, metrics } = data

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
            <StageChips
              stages={stages}
              active={activeStage}
              onChange={setActiveStage}
              total={rows.length}
            />
          </div>
          <div className="mt-6">
            {/* Без диплинка раскрываем первую строку: аноним сразу видит,
                как выглядит карточка и что именно за пейволлом */}
            <RequirementList
              rows={rows}
              stages={stages}
              activeStage={activeStage}
              productId={passport.id}
              initialRequirementId={searchParams.get('req') ?? rows[0]?.id}
              scrollToInitial={searchParams.has('req')}
            />
          </div>
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
