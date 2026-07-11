import { useEffect, useId, useRef, useState, useSyncExternalStore } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { useContentRequest, useSearchQuery } from '@/data/hooks'
import type { SearchHit, SearchKind } from '@/data/types'
import { ru } from '@/i18n/ru'
import { formatHsCode } from '@/lib/format'
import { useDebounced } from '@/lib/use-debounced'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

const narrowQuery = window.matchMedia('(max-width: 639px)')
function useIsNarrow(): boolean {
  return useSyncExternalStore(
    (cb) => {
      narrowQuery.addEventListener('change', cb)
      return () => narrowQuery.removeEventListener('change', cb)
    },
    () => narrowQuery.matches,
  )
}

/**
 * Поисковая строка с автоподсказками — входная дверь продукта (§3b).
 * У результата всегда видно официальное название кода + категорию,
 * чтобы пользователь сам заметил неверный код.
 */
export function SearchBox({
  size = 'compact',
  autoFocus,
  className,
}: {
  size?: 'hero' | 'compact'
  autoFocus?: boolean
  className?: string
}) {
  const navigate = useNavigate()
  const listboxId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const [kind, setKind] = useState<SearchKind>('product')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [requested, setRequested] = useState(false)

  const debounced = useDebounced(query)
  const { data: hits, isFetching } = useSearchQuery(debounced, kind)
  const contentRequest = useContentRequest()
  const isNarrow = useIsNarrow()

  const placeholder =
    kind === 'product'
      ? isNarrow
        ? ru.landing.searchPlaceholderShort
        : ru.landing.searchPlaceholder
      : isNarrow
        ? ru.landing.searchPlaceholderServiceShort
        : ru.landing.searchPlaceholderService

  const showEmpty =
    open &&
    debounced.trim().length >= 2 &&
    !isFetching &&
    (hits?.length ?? 0) === 0

  const showList = open && (hits?.length ?? 0) > 0

  useEffect(() => {
    setActive(-1)
    setRequested(false)
  }, [debounced, kind])

  // Клик вне — закрыть
  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [])

  function go(hit: SearchHit) {
    setOpen(false)
    navigate(`/product/${hit.id}`)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!showList) return
    const n = hits!.length
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => (a + 1) % n)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => (a - 1 + n) % n)
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault()
      go(hits![active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const hero = size === 'hero'

  return (
    <div ref={rootRef} className={cn('relative', className)}>
      <div
        className={cn(
          'flex items-center gap-2 rounded-lg border bg-paper transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/40',
          hero ? 'h-14 pr-2 pl-4' : 'h-9 pr-1 pl-3',
        )}
      >
        <Search
          className={cn('shrink-0 text-muted-foreground', hero ? 'size-5' : 'size-4')}
        />
        <input
          type="text"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listboxId}
          aria-autocomplete="list"
          autoFocus={autoFocus}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          className={cn(
            'min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted-foreground',
            hero ? 'text-lg' : 'text-sm',
          )}
        />
        <div
          className={cn(
            'flex shrink-0 rounded-md bg-muted p-0.5',
            hero ? '' : 'hidden sm:flex',
          )}
          role="radiogroup"
          aria-label="Тип поиска"
        >
          {(['product', 'service'] as const).map((k) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={kind === k}
              onClick={() => setKind(k)}
              className={cn(
                'rounded-[5px] px-3 text-xs font-medium transition-colors',
                hero ? 'py-2.5' : 'py-1',
                kind === k
                  ? 'bg-paper text-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {k === 'product' ? ru.landing.kindProduct : ru.landing.kindService}
            </button>
          ))}
        </div>
      </div>

      {(showList || showEmpty) && (
        <div className="absolute inset-x-0 top-full z-30 mt-1.5 overflow-hidden rounded-lg border bg-popover">
          {showList && (
            <ul id={listboxId} role="listbox" className="max-h-96 overflow-y-auto">
              {hits!.map((hit, i) => (
                <li key={hit.id} role="option" aria-selected={i === active}>
                  <button
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => go(hit)}
                    onMouseEnter={() => setActive(i)}
                    className={cn(
                      'flex w-full items-baseline gap-3 px-4 py-2.5 text-left transition-colors',
                      i === active && 'bg-accent',
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">
                        {hit.displayName}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {hit.officialName}
                        {hit.categoryName ? ` · ${hit.categoryName}` : ''}
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-xs text-muted-foreground">
                      {formatHsCode(hit.code)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {showEmpty && (
            <div className="px-4 py-4">
              <p className="text-sm font-medium">
                {ru.landing.searchEmptyTitle} «{debounced.trim()}»
              </p>
              {requested || contentRequest.isSuccess ? (
                <p className="mt-1 text-sm text-positive">
                  {ru.landing.searchEmptyDone}
                </p>
              ) : (
                <>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {ru.landing.searchEmptyText}
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-3"
                    disabled={contentRequest.isPending}
                    onClick={() =>
                      contentRequest.mutate(
                        { kind: 'missing_product', queryText: debounced.trim() },
                        { onSuccess: () => setRequested(true) },
                      )
                    }
                  >
                    {ru.landing.searchEmptyCta}
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
