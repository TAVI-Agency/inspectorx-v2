import { useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CornerDownLeft, Search } from 'lucide-react'
import { useContentRequest, useSearchQuery } from '@/data/hooks'
import type { SearchHit, SearchKind } from '@/data/types'
import { useDebounced } from '@/lib/use-debounced'
import { formatHsCode } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'

/**
 * Большой поиск реестра: переключатель товар/услуга, подсказки с официальным
 * названием кода, полная клавиатурная навигация. Пустой результат — заявка
 * на наполнение (missing_product).
 */
export function CSearch({
  autoFocus,
  onPick,
}: {
  autoFocus?: boolean
  /** Перехват выбора подсказки: true — выбор остаётся на странице (без навигации). */
  onPick?: (hit: SearchHit) => boolean
}) {
  const navigate = useNavigate()
  const listboxId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)

  const [kind, setKind] = useState<SearchKind>('product')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)

  const debounced = useDebounced(query, 200)
  const { data: hits, isFetching } = useSearchQuery(debounced, kind)
  const showEmpty = debounced.trim().length >= 2 && !isFetching && (hits?.length ?? 0) === 0

  const request = useContentRequest()
  const [requested, setRequested] = useState(false)

  useEffect(() => setCursor(0), [debounced, kind])
  useEffect(() => {
    setRequested(false)
    request.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced])

  // Клик мимо — закрыть подсказки
  useEffect(() => {
    function onDown(e: PointerEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [])

  function go(hit: SearchHit) {
    setOpen(false)
    if (onPick?.(hit)) return
    navigate(hit.kind === 'service' ? `/service/${hit.id}` : `/product/${hit.id}`)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open || !hits || hits.length === 0) {
      if (e.key === 'Escape') setOpen(false)
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => (c + 1) % hits.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => (c - 1 + hits.length) % hits.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const hit = hits[cursor]
      if (hit) go(hit)
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const dropdownVisible = open && debounced.trim().length >= 2

  return (
    <div ref={rootRef} className="relative">
      {/* Переключатель вида поиска */}
      <div className="mb-3 inline-flex rounded-lg border border-border bg-card p-0.5">
        {(['product', 'service'] as const).map((k) => (
          <button
            key={k}
            type="button"
            aria-pressed={kind === k}
            onClick={() => {
              setKind(k)
              inputRef.current?.focus()
            }}
            className={cn(
              'rounded-[7px] px-3.5 py-1.5 text-[13px] font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
              kind === k
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {k === 'product' ? ru.landing.kindProduct : ru.landing.kindService}
          </button>
        ))}
      </div>

      <div
        className={cn(
          'flex items-center gap-3 rounded-xl border bg-card px-4 shadow-[0_2px_4px_rgba(13,31,34,0.04),0_20px_44px_-28px_rgba(13,31,34,0.35)] transition-colors',
          dropdownVisible ? 'rounded-b-none border-primary/50' : 'focus-within:border-primary/50',
        )}
      >
        <Search className="size-5 shrink-0 text-muted-foreground" />
        <input
          ref={inputRef}
          autoFocus={autoFocus}
          role="combobox"
          aria-expanded={dropdownVisible}
          aria-controls={listboxId}
          aria-autocomplete="list"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder={
            kind === 'product' ? ru.landing.searchPlaceholder : ru.landing.searchPlaceholderService
          }
          className="h-14 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground/70 sm:text-lg"
        />
        {isFetching && (
          <span
            aria-hidden
            className="size-4 shrink-0 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary"
          />
        )}
      </div>

      {dropdownVisible && (
        <div className="absolute inset-x-0 top-full z-30 overflow-hidden rounded-b-xl border border-t-0 border-primary/50 bg-popover shadow-[0_28px_56px_-24px_rgba(13,31,34,0.45)]">
          {hits && hits.length > 0 && (
            <ul id={listboxId} role="listbox" className="max-h-[19rem] overflow-y-auto py-1.5">
              {hits.map((hit, i) => (
                <li key={hit.id} role="option" aria-selected={i === cursor}>
                  <button
                    type="button"
                    onClick={() => go(hit)}
                    onPointerEnter={() => setCursor(i)}
                    className={cn(
                      'flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors',
                      i === cursor && 'bg-accent/60',
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[15px] font-medium">
                        {hit.displayName}
                      </span>
                      {hit.officialName !== hit.displayName && (
                        <span className="block truncate text-xs text-muted-foreground">
                          {hit.officialName}
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 rounded-md bg-secondary px-2 py-1 font-mono text-[11px] text-secondary-foreground">
                      {hit.codeKind === 'hs' ? formatHsCode(hit.code) : hit.code}
                    </span>
                    {i === cursor && (
                      <CornerDownLeft className="size-3.5 shrink-0 text-muted-foreground" />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {showEmpty && (
            <div className="px-5 py-6 text-center">
              <p className="text-sm font-medium">
                {ru.landing.searchEmptyTitle} «{debounced.trim()}»
              </p>
              <p className="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-muted-foreground">
                {ru.landing.searchEmptyText}
              </p>
              {requested ? (
                <p className="mt-3 text-sm font-medium text-positive">
                  {ru.landing.searchEmptyDone}
                </p>
              ) : (
                <button
                  type="button"
                  disabled={request.isPending}
                  onClick={() =>
                    request.mutate(
                      { kind: 'missing_product', queryText: debounced.trim() },
                      { onSuccess: () => setRequested(true) },
                    )
                  }
                  className="mt-3 inline-flex h-8 items-center rounded-lg bg-primary px-3.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/85 disabled:opacity-60"
                >
                  {request.isPending ? ru.common.sending : ru.landing.searchEmptyCta}
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
