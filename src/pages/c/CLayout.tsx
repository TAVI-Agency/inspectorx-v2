import { useCallback, useEffect, useState } from 'react'
import { Outlet, ScrollRestoration } from 'react-router-dom'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CRail } from './shell/CRail'
import { CHeader } from './shell/CHeader'
import { CMobileTabs, CMobileTop } from './shell/CMobileNav'

const RAIL_KEY = 'ix-rail-collapsed'

/**
 * Оболочка дизайна C: слева сворачиваемый рейл-кокпит, сверху минимальная
 * шапка (контекст + колокольчик), на мобильном — топ-бар и нижние табы.
 */
export function CLayout() {
  // Порталы (диалоги, поповеры) рендерятся в body — вне поддерева .theme-c.
  // Пока открыт дизайн C, тема живёт на body, чтобы порталы не теряли токены.
  useEffect(() => {
    document.body.classList.add('theme-c')
    return () => document.body.classList.remove('theme-c')
  }, [])

  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(RAIL_KEY) === '1')
  const toggle = useCallback(() => {
    setCollapsed((v) => {
      localStorage.setItem(RAIL_KEY, v ? '0' : '1')
      return !v
    })
  }, [])

  return (
    <div className="theme-c min-h-svh bg-background font-sans text-foreground antialiased">
      <CRail collapsed={collapsed} onToggle={toggle} />
      <CMobileTop />
      <div
        className={cn(
          'flex min-h-svh flex-col pb-16 transition-[padding] duration-200 lg:pb-0',
          collapsed ? 'lg:pl-16' : 'lg:pl-[248px]',
        )}
      >
        <CHeader />
        <main className="flex-1">
          <Outlet />
        </main>
        <CFooter />
      </div>
      <CMobileTabs />
      <ScrollRestoration />
    </div>
  )
}

/** Монограмма: узел маршрута — кольцо с точкой-станцией */
export function CMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'relative grid size-9 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground',
        className,
      )}
    >
      <svg viewBox="0 0 24 24" className="size-5" fill="none" aria-hidden>
        <path
          d="M4 17c4-.5 5.5-8 9-9.5 2-.86 5 .5 6 3"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <circle cx="4.5" cy="17" r="2" fill="currentColor" />
        <circle cx="19" cy="10.2" r="2" fill="currentColor" />
      </svg>
    </span>
  )
}

function CFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-col gap-1.5 px-4 py-6 text-[12px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <p>{ru.footer.disclaimer}</p>
        <p className="shrink-0">
          <a href="mailto:hello@inspectorx.uz" className="hover:text-foreground">
            {ru.footer.email}
          </a>
          {' · '}
          {ru.footer.rights}
        </p>
      </div>
    </footer>
  )
}
