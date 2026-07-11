import { Link } from 'react-router-dom'
import { Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'

/**
 * Пейволл-плейсхолдеры закрытых RLS полей. Муляж повторяет структуру
 * реального контента (та же типографика, тот же line-box) и блюрится;
 * реальный текст сюда не попадает никогда.
 */

/** Строка-муляж текста в реальной высоте строки */
function FakeLine({ w, strong }: { w: string; strong?: boolean }) {
  return (
    <span className="flex h-[1.25rem] items-center" style={{ width: w }}>
      <span
        className={cn(
          'h-2.5 w-full rounded-sm',
          strong
            ? 'bg-foreground/45 dark:bg-foreground/55'
            : 'bg-foreground/25 dark:bg-foreground/40',
        )}
      />
    </span>
  )
}

function FakeSectionLabel({ w = '7rem' }: { w?: string }) {
  return (
    <span className="flex h-4 items-center" style={{ width: w }}>
      <span className="h-2 w-full rounded-sm bg-foreground/30 dark:bg-foreground/45" />
    </span>
  )
}

/** Полная карточка: муляж «Суть / Как исполнить / Документы» как у подписчика */
export function PaywallGate({ className }: { className?: string }) {
  return (
    <div className={cn('relative overflow-hidden rounded-lg border', className)}>
      <div aria-hidden className="space-y-5 p-5 blur-[6px] select-none">
        <div className="space-y-2">
          <FakeSectionLabel />
          <FakeLine w="92%" />
          <FakeLine w="100%" />
          <FakeLine w="74%" />
        </div>
        <div className="space-y-2.5">
          <FakeSectionLabel w="6rem" />
          {['86%', '70%', '78%'].map((w, i) => (
            <div key={i} className="flex items-center gap-3">
              <span className="size-6 shrink-0 rounded-full border border-foreground/30 dark:border-foreground/45" />
              <FakeLine w={w} strong={i === 0} />
            </div>
          ))}
        </div>
        <div className="space-y-2">
          <FakeSectionLabel w="5rem" />
          <div className="h-10 rounded-md border border-foreground/20 dark:border-foreground/35" />
          <div className="h-10 rounded-md border border-foreground/20 dark:border-foreground/35" />
        </div>
      </div>
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-background/45 p-4 text-center dark:bg-background/55">
        <div className="flex items-center gap-1.5 text-sm font-medium">
          <Lock className="size-3.5" />
          {ru.paywall.locked}
        </div>
        <p className="max-w-xs text-xs text-muted-foreground">{ru.paywall.lockedText}</p>
        <Button size="sm" className="mt-1" nativeButton={false} render={<Link to="/pricing" />}>
          {ru.paywall.cta}
        </Button>
      </div>
    </div>
  )
}

/**
 * Панельный вариант (юр. слой): муляж серифной цитаты + реквизитов,
 * подпись без кнопки — на карточку остаётся один CTA. Весь блок — ссылка на тариф.
 */
export function PaywallPanel({ className }: { className?: string }) {
  return (
    <Link
      to="/pricing"
      className={cn(
        'relative block overflow-hidden rounded-md border transition-colors hover:border-foreground/30 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
        className,
      )}
      aria-label={`${ru.paywall.locked} — ${ru.paywall.cta}`}
    >
      <div aria-hidden className="blur-[6px] select-none">
        <div className="space-y-1.5 border-l-2 border-foreground/50 px-4 py-3 font-serif">
          <FakeLine w="88%" />
          <FakeLine w="94%" />
          <FakeLine w="63%" />
        </div>
        <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 border-t px-4 py-3">
          <FakeSectionLabel w="2.2rem" />
          <FakeLine w="72%" />
          <FakeSectionLabel w="2.8rem" />
          <FakeLine w="34%" />
          <FakeSectionLabel w="4rem" />
          <FakeLine w="46%" />
        </div>
      </div>
      <div className="absolute inset-0 flex items-center justify-center bg-background/45 dark:bg-background/55">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <Lock className="size-3.5" />
          {ru.paywall.locked}
        </span>
      </div>
    </Link>
  )
}

/** Метрика паспорта: муляж-значение в той же типографике, что открытые числа */
export function PaywallNumber({ className }: { className?: string }) {
  return (
    <span
      className={cn('inline-flex items-baseline gap-2', className)}
      aria-label={ru.paywall.locked}
    >
      <span
        aria-hidden
        className="text-2xl font-semibold tracking-tight text-foreground/80 blur-[7px] select-none"
      >
        24
      </span>
      <Lock aria-hidden className="size-3 translate-y-[-1px] text-muted-foreground" />
    </span>
  )
}
