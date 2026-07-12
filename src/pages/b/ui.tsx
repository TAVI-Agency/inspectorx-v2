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
import type { RequirementCategory } from '@/data/taxonomy'
import { CATEGORY_LABEL } from '@/data/taxonomy'
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

/** Цветной чип «рода требования» (NTM) — палитра независима от темы. */
const CATEGORY_TONE: Record<RequirementCategory, string> = {
  tbt: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-300',
  sps: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-300',
  marking: 'bg-amber-500/10 text-amber-600 dark:text-amber-300',
  licensing: 'bg-violet-500/10 text-violet-600 dark:text-violet-300',
  fiscal: 'bg-rose-500/10 text-rose-600 dark:text-rose-300',
  currency: 'bg-cyan-500/10 text-cyan-700 dark:text-cyan-300',
  customs: 'bg-slate-500/10 text-slate-600 dark:text-slate-300',
  origin: 'bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-300',
}

export function CategoryChip({ category }: { category: RequirementCategory }) {
  return (
    <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', CATEGORY_TONE[category])}>
      {CATEGORY_LABEL[category]}
    </span>
  )
}

/** Стиль плашки типа требования (деонтика) в дизайне Б. */
export function deonticChipClass(deontic: 'obligation' | 'prohibition' | 'permission'): string {
  if (deontic === 'prohibition')
    return 'bg-sanction/10 text-sanction ring-1 ring-inset ring-sanction/20'
  if (deontic === 'permission')
    return 'bg-positive/10 text-positive ring-1 ring-inset ring-positive/20'
  return 'bg-secondary text-muted-foreground ring-1 ring-inset ring-border'
}
