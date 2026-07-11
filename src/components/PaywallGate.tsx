import { Link } from 'react-router-dom'
import { Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'

/**
 * Пейволл-плейсхолдер закрытого поля. Сервер (RLS) не отдал данные —
 * рисуем блюр-строки и CTA на тариф. Никогда не рендерит реальный контент.
 */
export function PaywallGate({
  className,
  compact,
}: {
  className?: string
  compact?: boolean
}) {
  return (
    <div
      className={cn('relative overflow-hidden rounded-lg border', className)}
      aria-label={ru.paywall.locked}
    >
      {/* Блюр-имитация закрытого текста */}
      <div
        aria-hidden
        className={cn(
          'space-y-2.5 p-4 opacity-70 blur-[6px] select-none',
          compact ? 'p-3' : 'p-5',
        )}
      >
        <div className="h-3 w-3/4 rounded bg-foreground/25" />
        <div className="h-3 w-full rounded bg-foreground/15" />
        <div className="h-3 w-5/6 rounded bg-foreground/15" />
        {!compact && (
          <>
            <div className="h-3 w-2/3 rounded bg-foreground/15" />
            <div className="mt-4 h-3 w-1/2 rounded bg-foreground/25" />
            <div className="h-3 w-4/5 rounded bg-foreground/15" />
          </>
        )}
      </div>
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-background/40 p-4 text-center">
        <div className="flex items-center gap-1.5 text-sm font-medium">
          <Lock className="size-3.5" />
          {ru.paywall.locked}
        </div>
        {!compact && (
          <p className="max-w-xs text-xs text-muted-foreground">
            {ru.paywall.lockedText}
          </p>
        )}
        <Button size={compact ? 'xs' : 'sm'} className="mt-1" nativeButton={false} render={<Link to="/pricing" />}>
          {ru.paywall.cta}
        </Button>
      </div>
    </div>
  )
}

/** Мини-версия для метрик паспорта: блюр-число + подпись */
export function PaywallNumber({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-baseline gap-1.5', className)}>
      <span
        aria-hidden
        className="text-2xl font-semibold tracking-tight blur-[7px] select-none"
      >
        12
      </span>
      <Lock className="size-3 self-center text-muted-foreground" />
    </span>
  )
}
