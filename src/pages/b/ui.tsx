import type { ReactNode } from 'react'
import {
  Package,
  Store,
  ArrowDownToLine,
  ArrowUpFromLine,
  ArrowLeftRight,
  RotateCcw,
  RotateCw,
  type LucideIcon,
} from 'lucide-react'
import type { Operation } from '@/data/types'
import { cn } from '@/lib/utils'

/** Мягкая карточка «кокпита» — крупный радиус, тонкая тень. */
export function BCard({
  className,
  children,
}: {
  className?: string
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        'rounded-2xl border bg-card shadow-[0_1px_2px_rgba(16,24,40,0.04),0_16px_32px_-24px_rgba(16,24,40,0.25)]',
        className,
      )}
    >
      {children}
    </div>
  )
}

/** Плитка метрики. */
export function StatTile({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'default' | 'primary' | 'positive' | 'sanction'
}) {
  const toneClass =
    tone === 'primary'
      ? 'text-primary'
      : tone === 'positive'
        ? 'text-positive'
        : tone === 'sanction'
          ? 'text-sanction'
          : 'text-foreground'
  return (
    <BCard className="p-4">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className={cn('mt-1.5 text-2xl font-semibold tracking-tight tabular-nums', toneClass)}>
        {value}
      </p>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
    </BCard>
  )
}

export const OPERATION_ICON: Record<Operation, LucideIcon> = {
  product: Package,
  realization: Store,
  import: ArrowDownToLine,
  export: ArrowUpFromLine,
  transit: ArrowLeftRight,
  re_export: RotateCcw,
  re_import: RotateCw,
}

/** Стиль плашки типа требования (деонтика) в дизайне Б. */
export function deonticChipClass(deontic: 'obligation' | 'prohibition' | 'permission'): string {
  if (deontic === 'prohibition')
    return 'bg-sanction/10 text-sanction ring-1 ring-inset ring-sanction/20'
  if (deontic === 'permission')
    return 'bg-positive/10 text-positive ring-1 ring-inset ring-positive/20'
  return 'bg-secondary text-muted-foreground ring-1 ring-inset ring-border'
}
