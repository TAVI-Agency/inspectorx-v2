import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowUpRight, Check, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/app/auth'
import {
  useFollowProduct,
  usePortfolioIds,
  useProductBundle,
} from '@/data/hooks'
import type { Operation, TransportType } from '@/data/types'
import { parseCountryParam, type CountryCode } from '@/data/countries'
import {
  buildOperationNodes,
  filterRows,
  operationMeta,
  stagesOf,
} from '@/data/taxonomy'
import { serviceLinkForProduct } from '@/data/cross-links'
import { formatDate, formatHsCode } from '@/lib/format'
import { codeSystemLabel, sortCodesForDisplay } from '@/i18n/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CCard, CEyebrow, CLockedValue, CStatTile, CountUp } from './ui'
import { CRouteNav, CRouteNavMobile } from './CRouteNav'
import { CRequirementList } from './CRequirementList'
import { CCountryNoneState, CCountryPreviewBanner, CCountryTabs } from './product/CCountryTabs'
import { CCompareMatrixButton } from './product/CCompareMatrix'

/**
 * Досье товара в дизайне C: паспорт → приборные метрики → маршрут
 * (операции слева, этапы нитью в списке справа).
 */
export function CProductPage() {
  const { productId } = useParams<{ productId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const country = parseCountryParam(searchParams.get('country'))
  const { data, isLoading, isError, isFetching, isPlaceholderData } = useProductBundle(
    productId,
    country,
  )
  // placeholderData (Задача 31) держит на экране данные ПРЕЖНЕЙ страны, пока грузится
  // новая — без этого флага список/плашка preview молча врут под уже переключённым табом
  const switchingCountry = isFetching && isPlaceholderData

  const rows = useMemo(() => data?.rows ?? [], [data])
  const nodes = useMemo(() => buildOperationNodes(rows), [rows])

  const reqParam = searchParams.get('req')
  const deeplinkOp = reqParam ? rows.find((r) => r.id === reqParam)?.operation : undefined
  const defaultOp: Operation = deeplinkOp ?? nodes[0]?.meta.key ?? 'product'

  const [opState, setOpState] = useState<Operation | null>(null)
  const [transport, setTransport] = useState<TransportType | null>(null)
  const activeOp = opState ?? defaultOp

  /** Смена страны: сбрасывает выбор операции (у неё другой набор строк) и deep-link req */
  function selectCountry(next: CountryCode) {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev)
      if (next === 'UZ') params.delete('country')
      else params.set('country', next)
      params.delete('req')
      return params
    })
    setOpState(null)
    setTransport(null)
  }

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
  const countryState = passport.countries.find((c) => c.country === country)?.state ?? 'live'
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
            {/* Чипы кодов — из passport.codes (страно-независимо, Задача 33):
                лейбл по системе кода, а не по хардкоду «ТН ВЭД»/«ИКПУ» на конкретную страну. */}
            {sortCodesForDisplay(passport.codes).map((c) => (
              <span
                key={c.system}
                className="rounded-md bg-secondary px-2.5 py-1 font-mono text-xs text-secondary-foreground"
              >
                {codeSystemLabel(c.system)} {c.system === 'tnved' ? formatHsCode(c.code) : c.code}
              </span>
            ))}
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

      {/* Кросс-ссылка: этот товар продаёт услуга со своим паспортом (аптека, кафе) */}
      {(() => {
        const link = serviceLinkForProduct(passport.hsCode)
        if (!link) return null
        return (
          <Link to={link.to} className="group mt-5 block focus-visible:outline-none">
            <CCard className="flex items-center gap-4 p-4 transition-colors group-hover:border-primary/40 group-focus-visible:ring-2 group-focus-visible:ring-ring">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold tracking-tight">{link.title}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                  {link.text}
                </p>
              </div>
              <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary">
                {ru.service.crossCta}
                <ArrowUpRight className="size-3.5 transition-transform duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </span>
            </CCard>
          </Link>
        )
      })()}

      <div className="mt-7 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <CCountryTabs
          coverage={passport.countries}
          country={country}
          onChange={selectCountry}
        />
        <CCompareMatrixButton productId={passport.id} />
      </div>

      <div className="mt-5">
        {switchingCountry && (
          <div
            role="status"
            aria-live="polite"
            className="mb-3 flex items-center gap-2 text-xs font-medium text-muted-foreground"
          >
            <span
              aria-hidden
              className="size-3.5 shrink-0 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary"
            />
            {ru.product.countrySwitching}
          </div>
        )}

        {/* Пока грузится новая страна, данные ниже — ещё от прежней (placeholderData):
            приглушаем и блокируем клики, чтобы список требований не выглядел как
            уже актуальный под переключённым табом. Плашка preview — по той же причине
            только когда данные действительно её страны, не чужие. */}
        <div className={cn(switchingCountry && 'pointer-events-none opacity-40 transition-opacity')}>
          {countryState === 'none' ? (
            <CCountryNoneState productId={passport.id} country={country} />
          ) : (
            <>
              {!switchingCountry && countryState === 'preview' && (
                <CCountryPreviewBanner className="mb-5" />
              )}

              {rows.length === 0 ? (
                <CCard className="p-8 text-center">
                  <h2 className="text-lg font-semibold tracking-tight">
                    {ru.product.noRequirementsTitle}
                  </h2>
                  <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
                    {ru.product.noRequirementsText}
                  </p>
                </CCard>
              ) : (
                <div className="grid gap-7 lg:grid-cols-[240px_minmax(0,1fr)]">
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
            </>
          )}
        </div>
      </div>
    </div>
  )
}

/** Индекс сложности: 10 делений-рисок, как на приборе (общий для товара и услуги) */
export function ComplexityMeter({ value }: { value: number }) {
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
