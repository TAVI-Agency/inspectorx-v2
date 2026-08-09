import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from 'react'

const KEY = 'ix-mock-subscriber'

interface AppModeCtx {
  /** Тумблер dev-меню «я подписчик» — показывает клиенту полный вид */
  mockSubscriber: boolean
  setMockSubscriber: (v: boolean) => void
}

const Ctx = createContext<AppModeCtx | null>(null)

export function AppModeProvider({ children }: { children: ReactNode }) {
  // В проде демо-режим всегда выключен: не читаем localStorage, иначе у старых
  // посетителей с сохранённым ix-mock-subscriber=1 включится мок-вид подписчика.
  const [mockSubscriber, setState] = useState(
    () => import.meta.env.DEV && localStorage.getItem(KEY) === '1',
  )

  const setMockSubscriber = useCallback((v: boolean) => {
    if (!import.meta.env.DEV) return
    setState(v)
    localStorage.setItem(KEY, v ? '1' : '0')
  }, [])

  return (
    <Ctx.Provider value={{ mockSubscriber, setMockSubscriber }}>
      {children}
    </Ctx.Provider>
  )
}

export function useAppMode(): AppModeCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAppMode outside AppModeProvider')
  return ctx
}
