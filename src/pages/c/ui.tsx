import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowDownToLine,
  ArrowLeftRight,
  ArrowUpFromLine,
  Lock,
  Package,
  RotateCcw,
  RotateCw,
  Store,
  type LucideIcon,
} from 'lucide-react'
import type { Deontic, Operation } from '@/data/types'
import type { RequirementCategory } from '@/data/taxonomy'
import { CATEGORY_LABEL } from '@/data/taxonomy'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'

/**
 * UI-кит дизайна C «Маршрут товара». Самодостаточен: ничего не импортирует
 * из дизайнов A/Б, чтобы их можно было удалить без последствий.
 */

/** Карточка-прибор: белая панель с точёной тенью и тонкой рамкой */
export function CCard({
  className,
  children,
  style,
}: {
  className?: string
  children: ReactNode
  style?: React.CSSProperties
}) {
  return (
    <div
      style={style}
      className={cn(
        'rounded-xl border border-border bg-card shadow-[0_1px_1px_rgba(13,31,34,0.03),0_12px_28px_-20px_rgba(13,31,34,0.28)]',
        className,
      )}
    >
      {children}
    </div>
  )
}

/** Моно-надпись раздела: РЕКВИЗИТ интерфейса */
export function CEyebrow({
  className,
  children,
  title,
}: {
  className?: string
  children: ReactNode
  title?: string
}) {
  return (
    <p
      title={title}
      className={cn(
        'font-mono text-[10px] font-medium tracking-[0.14em] text-muted-foreground uppercase',
        className,
      )}
    >
      {children}
    </p>
  )
}

/** Число, которое «набегает» при появлении (приборная стрелка) */
export function CountUp({
  value,
  className,
  duration = 900,
}: {
  value: number
  className?: string
  duration?: number
}) {
  const [shown, setShown] = useState(0)
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || value === 0) {
      setShown(value)
      return
    }
    let raf = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      setShown(Math.round(value * eased))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, duration])

  return (
    <span ref={ref} className={cn('tabular-nums', className)}>
      {shown}
    </span>
  )
}

/** Приборная плитка метрики */
export function CStatTile({
  label,
  value,
  hint,
  tone = 'default',
  index = 0,
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'default' | 'primary' | 'sanction' | 'positive'
  index?: number
}) {
  const toneClass =
    tone === 'primary'
      ? 'text-primary'
      : tone === 'sanction'
        ? 'text-sanction'
        : tone === 'positive'
          ? 'text-positive'
          : 'text-foreground'
  return (
    <CCard className="c-rise p-4" style={{ '--i': index } as React.CSSProperties}>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className={cn('font-display mt-2 text-[22px] leading-none font-medium tracking-tight', toneClass)}>
        {value}
      </p>
      {hint && <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p>}
    </CCard>
  )
}

/** Закрытая метрика: размытые цифры + замок, ведёт на тариф */
export function CLockedValue() {
  return (
    <Link
      to="/pricing"
      className="group inline-flex items-baseline gap-1.5 rounded focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      aria-label={ru.paywall.locked}
    >
      <span aria-hidden className="text-foreground/70 blur-[6px] select-none">
        24
      </span>
      <Lock aria-hidden className="size-3.5 self-center text-brass transition-transform group-hover:scale-110" />
    </Link>
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

/** Чип деонтики: запрет — кармин, льгота — изумруд, обязанность — нейтраль */
export function CDeonticChip({ deontic }: { deontic: Deontic }) {
  return (
    <span
      className={cn(
        'inline-flex h-[19px] shrink-0 items-center rounded-[6px] px-1.5 text-[11px] font-medium',
        deontic === 'obligation' && 'bg-secondary text-secondary-foreground',
        deontic === 'prohibition' && 'bg-sanction/10 text-sanction ring-1 ring-sanction/25 ring-inset',
        deontic === 'permission' && 'bg-positive/10 text-positive ring-1 ring-positive/25 ring-inset',
      )}
    >
      {ru.requirement.deontic[deontic]}
    </span>
  )
}

/** Род требования (NTM): приглушённый контурный чип, без радуги */
export function CCategoryChip({ category }: { category: RequirementCategory }) {
  return (
    <span className="inline-flex h-[19px] shrink-0 items-center rounded-[6px] border border-border px-1.5 text-[11px] font-medium text-muted-foreground">
      {CATEGORY_LABEL[category]}
    </span>
  )
}

/** Гербовая печать раннего доступа: латунное кольцо с замком */
export function CSeal({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        'relative grid size-11 shrink-0 place-items-center rounded-full border border-brass/45 text-brass',
        className,
      )}
    >
      <span className="absolute inset-[3px] rounded-full border border-dashed border-brass/55" />
      <Lock className="size-4" />
    </span>
  )
}

/** Муляжная строка текста для пейволла */
function FakeLine({ w, strong }: { w: string; strong?: boolean }) {
  return (
    <span className="flex h-5 items-center" style={{ width: w }}>
      <span
        className={cn(
          'h-2.5 w-full rounded-sm',
          strong ? 'bg-foreground/40 dark:bg-foreground/55' : 'bg-foreground/20 dark:bg-foreground/40',
        )}
      />
    </span>
  )
}

/**
 * Пейволл карточки: муляж содержимого под блюром, латунная печать и CTA.
 * Реальный закрытый текст сюда не попадает никогда — RLS не отдал.
 */
export function CPaywallGate({ className }: { className?: string }) {
  return (
    <div className={cn('relative overflow-hidden rounded-lg border border-brass/30', className)}>
      <div aria-hidden className="space-y-5 p-5 blur-[6px] select-none">
        <div className="space-y-2">
          <FakeLine w="7rem" />
          <FakeLine w="94%" strong />
          <FakeLine w="100%" />
          <FakeLine w="71%" />
        </div>
        <div className="space-y-2.5">
          <FakeLine w="6rem" />
          {['84%', '68%', '76%'].map((w, i) => (
            <div key={i} className="flex items-center gap-3">
              <span className="size-6 shrink-0 rounded-full border border-foreground/30" />
              <FakeLine w={w} strong={i === 0} />
            </div>
          ))}
        </div>
        <div className="space-y-2">
          <FakeLine w="5rem" />
          <div className="h-10 rounded-md border border-foreground/20" />
          <div className="h-10 rounded-md border border-foreground/20" />
        </div>
      </div>
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-2.5 bg-background/50 p-4 text-center dark:bg-background/60">
        <CSeal />
        <p className="text-sm font-semibold">{ru.paywall.locked}</p>
        <p className="max-w-xs text-xs leading-relaxed text-muted-foreground">
          {ru.paywall.lockedText}
        </p>
        <Link
          to="/pricing"
          className="mt-1 inline-flex h-8 items-center rounded-lg bg-primary px-3.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/85 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {ru.paywall.cta}
        </Link>
      </div>
    </div>
  )
}

/** Пейволл юридического слоя: муляж цитаты + реквизитов, весь блок — ссылка */
export function CPaywallPanel({ className }: { className?: string }) {
  return (
    <Link
      to="/pricing"
      className={cn(
        'relative block overflow-hidden rounded-lg border border-brass/30 transition-colors hover:border-brass/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
        className,
      )}
      aria-label={`${ru.paywall.locked} — ${ru.paywall.cta}`}
    >
      <div aria-hidden className="blur-[6px] select-none">
        <div className="space-y-1.5 border-l-2 border-foreground/50 px-4 py-3">
          <FakeLine w="88%" />
          <FakeLine w="95%" />
          <FakeLine w="60%" />
        </div>
        <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 border-t px-4 py-3">
          <FakeLine w="2.2rem" />
          <FakeLine w="70%" />
          <FakeLine w="2.8rem" />
          <FakeLine w="32%" />
        </div>
      </div>
      <div className="absolute inset-0 flex items-center justify-center gap-2 bg-background/50 dark:bg-background/60">
        <Lock className="size-3.5 text-brass" />
        <span className="text-sm font-semibold">{ru.paywall.locked}</span>
      </div>
    </Link>
  )
}

/** Метка доверия: проверено юристом / официальный ответ / AI-черновик */
export function CTrustStamp({
  trust,
  date,
  className,
}: {
  trust: 'ai_draft' | 'lawyer_verified' | 'official_answer'
  date?: string
  className?: string
}) {
  const verified = trust !== 'ai_draft'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-[4px] border px-2 py-0.5 font-mono text-[10px] font-medium tracking-[0.08em] uppercase',
        verified ? 'border-positive/40 text-positive' : 'border-border text-muted-foreground',
        className,
      )}
    >
      <span className={cn('size-1.5 rounded-full', verified ? 'bg-positive' : 'bg-muted-foreground/50')} />
      {trust === 'lawyer_verified'
        ? ru.requirement.trust.lawyer_verified(date ?? '—')
        : trust === 'official_answer'
          ? ru.requirement.trust.official_answer
          : ru.requirement.trust.ai_draft}
    </span>
  )
}
