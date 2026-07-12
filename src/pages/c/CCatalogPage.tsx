import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { exampleHits } from '@/data'
import { OPERATIONS } from '@/data/taxonomy'
import { formatHsCode, pluralize } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { CCard, CEyebrow } from './ui'
import { CSearch } from './CSearch'

/**
 * Реестр (/catalog): одна работа страницы — найти товар. Hero с авророй,
 * большой поиск и маршрут товара как подпись дизайна.
 */
export function CCatalogPage() {
  return (
    <div className="relative overflow-hidden">
      {/* Аврора: бирюза + латунь, очень тихо */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="c-aurora absolute -top-40 left-[8%] h-[26rem] w-[34rem] rounded-full bg-primary/14 blur-3xl" />
        <div className="c-aurora c-aurora-slow absolute -top-24 right-[4%] h-[20rem] w-[26rem] rounded-full bg-brass/12 blur-3xl" />
      </div>

      <div className="relative mx-auto max-w-6xl px-4 sm:px-8">
        <section className="pt-14 sm:pt-20">
          <div className="mx-auto max-w-3xl text-center">
            <CEyebrow className="text-foreground/60">
              {ru.marketing.eyebrow}
            </CEyebrow>
            <h1 className="font-display mt-4 text-[26px] leading-[1.2] font-medium tracking-tight text-balance sm:text-[38px]">
              Все требования закона к&nbsp;вашему товару
            </h1>
            <p className="mx-auto mt-4 max-w-xl text-[15px] leading-relaxed text-muted-foreground sm:text-base">
              {ru.landing.heroSubtitle} Каждое требование — со ссылкой на пункт закона.
            </p>
          </div>

          <div className="mx-auto mt-8 max-w-2xl">
            <CSearch autoFocus />
          </div>
        </section>

        {/* Подпись дизайна: путь товара от производства до границы */}
        <section aria-label="Путь товара" className="mt-14 sm:mt-16">
          <RouteStrip />
        </section>

        <section className="mt-12 pb-20 sm:mt-14">
          <CEyebrow>{ru.landing.examplesLabel}</CEyebrow>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {exampleHits.map((hit, i) => (
              <Link
                key={hit.id}
                to={hit.kind === 'service' ? `/service/${hit.id}` : `/product/${hit.id}`}
                className="group focus-visible:outline-none"
              >
                <CCard
                  className="c-rise h-full p-5 transition-all duration-300 group-hover:-translate-y-1 group-hover:border-primary/40 group-hover:shadow-[0_2px_4px_rgba(13,31,34,0.05),0_28px_48px_-24px_rgba(14,122,109,0.4)] group-focus-visible:ring-2 group-focus-visible:ring-ring"
                  style={{ '--i': i + 2 } as React.CSSProperties}
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="rounded-md bg-secondary px-2 py-1 font-mono text-[11px] text-secondary-foreground">
                      {hit.codeKind === 'hs'
                        ? formatHsCode(hit.code)
                        : `${ru.service.okedLabel} ${hit.code}`}
                    </span>
                    <ArrowUpRight className="size-4 text-muted-foreground transition-transform duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-primary" />
                  </div>
                  <h3 className="mt-4 text-[17px] font-semibold tracking-tight">
                    {hit.displayName}
                  </h3>
                  <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-muted-foreground">
                    {hit.officialName}
                  </p>
                  <div className="mt-4 flex items-center justify-between border-t border-border pt-3.5">
                    <span className="truncate pr-3 text-xs text-muted-foreground">
                      {hit.categoryName}
                    </span>
                    <span className="shrink-0 rounded-md bg-primary/10 px-2 py-1 text-xs font-semibold text-primary">
                      {pluralize(hit.requirementsCount, 'требование', 'требования', 'требований')}
                    </span>
                  </div>
                </CCard>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

/**
 * Горизонтальный маршрут: 7 операций как станции на пути товара.
 * Линия прорисовывается при загрузке, станции появляются каскадом.
 */
function RouteStrip() {
  const n = OPERATIONS.length
  const w = 720
  const pad = 46
  const step = (w - pad * 2) / (n - 1)
  const y = (i: number) => 34 + (i % 2 === 0 ? 0 : 10)

  const points = OPERATIONS.map((op, i) => ({
    op,
    x: pad + i * step,
    y: y(i),
  }))

  const d = points
    .map((p, i) => {
      if (i === 0) return `M ${p.x} ${p.y}`
      const prev = points[i - 1]
      const mx = (prev.x + p.x) / 2
      return `C ${mx} ${prev.y}, ${mx} ${p.y}, ${p.x} ${p.y}`
    })
    .join(' ')

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${w} 78`}
        className="mx-auto block w-full min-w-[560px] max-w-3xl"
        role="img"
        aria-label="Путь товара: от продукта и реализации до импорта, экспорта, транзита, реэкспорта и реимпорта"
      >
        <path
          d={d}
          pathLength={1}
          className="c-path-draw"
          fill="none"
          stroke="var(--primary)"
          strokeOpacity="0.45"
          strokeWidth="1.5"
        />
        {points.map((p, i) => (
          <g key={p.op.key} className="c-station" style={{ '--i': i } as React.CSSProperties}>
            <circle cx={p.x} cy={p.y} r="8" fill="var(--background)" />
            <circle
              cx={p.x}
              cy={p.y}
              r={p.op.isProcedure ? 4 : 5}
              fill={p.op.isProcedure ? 'var(--card)' : 'var(--primary)'}
              stroke="var(--primary)"
              strokeWidth="1.5"
            />
            <text
              x={p.x}
              y={p.y + 24}
              textAnchor="middle"
              className="font-mono uppercase"
              fontSize="9"
              letterSpacing="0.08em"
              fill="var(--muted-foreground)"
            >
              {p.op.label}
            </text>
          </g>
        ))}
      </svg>
      <p className="mt-2 text-center text-xs text-muted-foreground">
        Требования разложены по всему пути товара — от производства до таможенного поста
      </p>
    </div>
  )
}
