import { useEffect, useRef, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** Появление при скролле (cubic-bezier(.16,1,.3,1)); reduced-motion — без анимации */
export function FadeIn({
  children,
  className,
  delayMs = 0,
}: {
  children: ReactNode
  className?: string
  delayMs?: number
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    // Уже в вьюпорте на маунте (above-the-fold) — показываем сразу, не дожидаясь
    // асинхронного колбэка IO: иначе первый экран может «залипнуть» скрытым.
    if (el.getBoundingClientRect().top < window.innerHeight) {
      el.classList.add('is-visible')
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            el.classList.add('is-visible')
            io.disconnect()
          }
        }
      },
      { threshold: 0.1 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      className={cn('fade-in-up', className)}
      style={delayMs ? { transitionDelay: `${delayMs}ms` } : undefined}
    >
      {children}
    </div>
  )
}
