import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

export type ThemeSetting = 'light' | 'dark' | 'system'

const KEY = 'ix-theme'

interface ThemeCtx {
  setting: ThemeSetting
  resolved: 'light' | 'dark'
  setSetting: (t: ThemeSetting) => void
  toggle: () => void
}

const Ctx = createContext<ThemeCtx | null>(null)

function systemPrefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function loadSetting(): ThemeSetting {
  const raw = localStorage.getItem(KEY)
  return raw === 'light' || raw === 'dark' || raw === 'system' ? raw : 'system'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [setting, setSettingState] = useState<ThemeSetting>(loadSetting)
  const [systemDark, setSystemDark] = useState(systemPrefersDark)

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const resolved: 'light' | 'dark' =
    setting === 'system' ? (systemDark ? 'dark' : 'light') : setting

  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolved === 'dark')
  }, [resolved])

  const setSetting = useCallback((t: ThemeSetting) => {
    setSettingState(t)
    localStorage.setItem(KEY, t)
  }, [])

  const toggle = useCallback(() => {
    setSetting(resolved === 'dark' ? 'light' : 'dark')
  }, [resolved, setSetting])

  return (
    <Ctx.Provider value={{ setting, resolved, setSetting, toggle }}>
      {children}
    </Ctx.Provider>
  )
}

export function useTheme(): ThemeCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useTheme outside ThemeProvider')
  return ctx
}
