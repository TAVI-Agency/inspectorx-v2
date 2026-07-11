import { PaywallNumber } from '@/components/PaywallGate'
import type { SummaryMetrics } from '@/data/types'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'

/** Сводка паспорта: 4 метрики (§3.2). Закрытые — блюр, серверный пейволл. */
export function MetricsStrip({ metrics }: { metrics: SummaryMetrics }) {
  return (
    <dl className="grid grid-cols-2 overflow-hidden rounded-lg border bg-paper lg:grid-cols-4">
      <Metric label={ru.product.metrics.requirements}>
        <span className="text-2xl font-semibold tracking-tight">
          {metrics.requirements}
        </span>
      </Metric>
      <Metric label={ru.product.metrics.documents} className="border-l">
        {metrics.documents.state === 'ok' ? (
          <span className="text-2xl font-semibold tracking-tight">
            {metrics.documents.value}
          </span>
        ) : (
          <PaywallNumber />
        )}
      </Metric>
      <Metric
        label={ru.product.metrics.maxSanction}
        className="border-t lg:border-t-0 lg:border-l"
      >
        {metrics.maxSanction.state === 'ok' ? (
          <span className="text-2xl font-semibold tracking-tight text-sanction">
            {metrics.maxSanction.value}
          </span>
        ) : (
          <PaywallNumber />
        )}
      </Metric>
      <Metric label={ru.product.metrics.changes30d} className="border-t border-l lg:border-t-0">
        <span
          className={cn(
            'text-2xl font-semibold tracking-tight',
            metrics.changes30d > 0 && 'text-primary',
          )}
        >
          {metrics.changes30d}
        </span>
      </Metric>
    </dl>
  )
}

function Metric({
  label,
  children,
  className,
}: {
  label: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('px-4 py-3.5', className)}>
      <dt className="font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
        {label}
      </dt>
      <dd className="mt-1.5">{children}</dd>
    </div>
  )
}
