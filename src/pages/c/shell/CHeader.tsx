import { useRouteCrumb } from './nav'
import { CNotificationCenter } from './CNotificationCenter'

/** Минимальная шапка: контекст страницы + колокольчик. Больше ничего. */
export function CHeader() {
  const crumb = useRouteCrumb()
  return (
    <header className="sticky top-0 z-30 hidden h-12 items-center justify-between border-b border-border bg-background/85 px-6 backdrop-blur-lg lg:flex">
      <p className="font-mono text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase">
        {crumb}
      </p>
      <CNotificationCenter />
    </header>
  )
}
