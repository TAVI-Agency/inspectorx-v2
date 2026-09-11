import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App.tsx'
import { ThemeProvider } from './app/theme'
import { AppModeProvider } from './app/app-mode'
import { AuthProvider } from './app/auth'
import { initObservability } from './lib/observability'
import './index.css'

// Sentry и аналитика включаются только при заданных VITE_SENTRY_DSN / VITE_PLAUSIBLE_DOMAIN / VITE_YM_ID; без них — no-op.
initObservability(import.meta.env)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AppModeProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </AppModeProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
)
