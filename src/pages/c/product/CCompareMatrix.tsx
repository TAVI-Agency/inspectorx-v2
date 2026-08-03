import { useState } from 'react'
import { Check, Columns3 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useComparisonMatrix } from '@/data/hooks'
import type { ComparisonMatrix } from '@/data/types'
import type { CountryCode } from '@/data/countries'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'

/**
 * Кнопка «Сравнить страны» + диалог с матрицей категория × страна
 * (Задача 32, Блок 4). Бесплатный тизер — только есть/нет требований
 * категории и самый тревожный lifecycle, без деталей и цитат закона за
 * пейволлом (решение грил-сессии №4). Тело диалога монтируется только
 * пока он открыт — useComparisonMatrix не грузится на каждый визит
 * страницы товара.
 */
export function CCompareMatrixButton({ productId }: { productId: string }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="shrink-0"
        onClick={() => setOpen(true)}
      >
        <Columns3 className="size-4" />
        {ru.product.compareCta}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{ru.product.compareDialogTitle}</DialogTitle>
            <DialogDescription>{ru.product.compareDialogText}</DialogDescription>
          </DialogHeader>
          {open && <CCompareMatrixBody productId={productId} />}
        </DialogContent>
      </Dialog>
    </>
  )
}

function CCompareMatrixBody({ productId }: { productId: string }) {
  const { data, isLoading, isError } = useComparisonMatrix(productId)

  if (isError) {
    return <p className="text-sm text-destructive">{ru.product.compareError}</p>
  }

  if (isLoading || !data) {
    return (
      <div className="space-y-2">
        {/* 8 — число активных категорий в requirement_categories (см. миграцию) */}
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    )
  }

  return (
    <div>
      {/* Мобайл: таблица шире диалога — скроллим горизонтально внутри своего контейнера */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[420px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-secondary/50 text-xs font-medium text-muted-foreground">
              <th className="px-3 py-2 text-left font-medium">
                {ru.product.compareCategoryHeader}
              </th>
              {data.countries.map((country) => (
                <th key={country} className="px-3 py-2 text-center font-medium">
                  {ru.countries[country]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.categories.map((cat) => (
              <tr key={cat.slug}>
                <td className="px-3 py-2.5 font-medium whitespace-nowrap">{cat.name}</td>
                {data.countries.map((country) => (
                  <td key={country} className="px-3 py-2.5 text-center">
                    <CCompareCell
                      cell={data.cells[cat.slug]?.[country] ?? { state: 'absent' }}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
        <li className="inline-flex items-center gap-1.5">
          <Check aria-hidden className="size-3.5 text-positive" />
          {ru.product.compareLegendPresent}
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden>—</span>
          {ru.product.compareLegendAbsent}
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden className="size-1.5 rounded-full bg-primary" />
          {ru.product.compareLegendPreview}
        </li>
      </ul>
    </div>
  )
}

function CCompareCell({
  cell,
}: {
  cell: ComparisonMatrix['cells'][string][CountryCode]
}) {
  if (cell.state === 'absent') {
    return (
      <span aria-hidden className="text-muted-foreground">
        —
      </span>
    )
  }

  const badge =
    cell.worstLifecycle && cell.worstLifecycle !== 'in_force' ? cell.worstLifecycle : null

  return (
    <span className="inline-flex items-center justify-center gap-1.5">
      <Check aria-label={ru.product.compareLegendPresent} className="size-4 text-positive" />
      {cell.state === 'preview' && (
        <span
          aria-hidden
          title={ru.product.compareLegendPreview}
          className="size-1.5 rounded-full bg-primary"
        />
      )}
      {badge && (
        <span
          className={cn(
            'rounded-[6px] px-1 py-0.5 text-[10px] font-medium whitespace-nowrap',
            badge === 'repealed' || badge === 'expiring'
              ? 'bg-sanction/10 text-sanction'
              : 'bg-secondary text-muted-foreground',
          )}
        >
          {ru.product.compareLifecycleLabel[badge]}
        </span>
      )}
    </span>
  )
}
