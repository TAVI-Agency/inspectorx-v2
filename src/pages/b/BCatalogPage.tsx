import { Link } from 'react-router-dom'
import { ArrowRight, FileText } from 'lucide-react'
import { SearchBox } from '@/components/SearchBox'
import { useTelemetry } from '@/data/hooks'
import { exampleHits } from '@/data'
import { ru } from '@/i18n/ru'
import { formatHsCode, pluralize } from '@/lib/format'
import { BCard } from './ui'

export function BCatalogPage() {
  const { data: telemetry } = useTelemetry()
  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6">
      {/* Hero */}
      <section className="pt-14 pb-10 sm:pt-20">
        <div className="mx-auto max-w-3xl text-center">
          <span className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-medium text-muted-foreground shadow-sm">
            <span className="size-1.5 rounded-full bg-positive" />
            {telemetry
              ? ru.header.monitoring(String(telemetry.actsCount)) + ' актов'
              : 'Реестр требований · Узбекистан'}
          </span>
          <h1 className="mt-5 text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            Все требования к товару — в одном кокпите
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-muted-foreground">
            Найдите товар по названию или коду ТН ВЭД — и получите чек-лист: что сделать,
            какие документы, сроки и санкции.
          </p>
          <div className="mx-auto mt-8 max-w-2xl">
            <SearchBox size="hero" basePath="/b/product" autoFocus />
          </div>
        </div>
      </section>

      {/* Featured */}
      <section className="pb-20">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
            Примеры товаров
          </h2>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {exampleHits.map((hit) => (
            <Link
              key={hit.id}
              to={`/b/product/${hit.id}`}
              className="group focus-visible:outline-none"
            >
              <BCard className="h-full p-5 transition-all group-hover:-translate-y-0.5 group-hover:shadow-[0_1px_2px_rgba(16,24,40,0.05),0_24px_44px_-24px_rgba(79,70,229,0.4)] group-focus-visible:ring-2 group-focus-visible:ring-ring">
                <div className="flex items-start justify-between gap-3">
                  <span className="grid size-10 place-items-center rounded-xl bg-accent text-accent-foreground">
                    <FileText className="size-5" />
                  </span>
                  <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                </div>
                <h3 className="mt-4 font-semibold tracking-tight">{hit.displayName}</h3>
                <p className="mt-1 line-clamp-1 text-sm text-muted-foreground">
                  {hit.categoryName}
                </p>
                <div className="mt-4 flex items-center justify-between border-t pt-3">
                  <span className="font-mono text-xs text-muted-foreground">
                    {formatHsCode(hit.code)}
                  </span>
                  <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                    {pluralize(hit.requirementsCount, 'требование', 'требования', 'требований')}
                  </span>
                </div>
              </BCard>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
