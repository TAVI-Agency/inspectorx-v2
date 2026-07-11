import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * Анимированное раскрытие (grid-rows 0fr→1fr, фирменная кривая).
 * prefers-reduced-motion: мгновенно, layout не ломается.
 */
export function Expand({
  open,
  children,
  className,
}: {
  open: boolean
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'grid transition-[grid-template-rows] duration-500 ease-[var(--ease-brand)] motion-reduce:transition-none',
        open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
        className,
      )}
    >
      <div className="min-h-0 overflow-hidden">{children}</div>
    </div>
  )
}
