import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { FadeIn } from '@/components/FadeIn'
import { SearchBox } from '@/components/SearchBox'
import { TelemetryLine } from '@/app/layout/TelemetryLine'
import { exampleHits } from '@/data'
import { ru } from '@/i18n/ru'
import { formatHsCode, pluralize } from '@/lib/format'

/**
 * Витринный вход (реестр): рабочий поиск + примеры.
 * Маркетинговая часть («как это работает» и т.д.) живёт на лендинге «/».
 */
export function CatalogPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6">
      {/* Hero: рабочий поиск — входная дверь продукта */}
      <section className="mx-auto max-w-3xl pt-16 pb-10 sm:pt-24">
        <FadeIn>
          <p className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
            {ru.marketing.eyebrow}
          </p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            {ru.landing.heroTitle}
          </h1>
          <p className="mt-4 max-w-xl text-lg text-muted-foreground">
            {ru.landing.heroSubtitle}
          </p>
        </FadeIn>
        <FadeIn delayMs={80}>
          <SearchBox size="hero" className="mt-8" autoFocus />
          <TelemetryLine className="mt-3 px-1" />
        </FadeIn>
      </section>

      {/* Три примера */}
      <section className="mx-auto max-w-3xl pb-20">
        <FadeIn delayMs={120}>
          <p className="text-sm text-muted-foreground">{ru.landing.examplesLabel}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {exampleHits.map((hit) => (
              <Link
                key={hit.id}
                to={`/product/${hit.id}`}
                className="group rounded-lg border bg-paper p-4 transition-colors hover:border-foreground/25 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{hit.displayName}</span>
                  <ArrowRight className="size-4 shrink-0 text-muted-foreground transition-transform duration-300 ease-[var(--ease-brand)] group-hover:translate-x-0.5" />
                </div>
                <p className="mt-2 font-mono text-xs text-muted-foreground">
                  {formatHsCode(hit.code)}
                </p>
                <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
                  {hit.categoryName}
                </p>
                <p className="mt-3 text-xs font-medium text-primary">
                  {pluralize(hit.requirementsCount, 'требование', 'требования', 'требований')}
                </p>
              </Link>
            ))}
          </div>
        </FadeIn>
      </section>
    </div>
  )
}
