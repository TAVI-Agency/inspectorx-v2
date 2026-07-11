import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App.tsx'
import { ThemeProvider } from './app/theme'
import { AppModeProvider } from './app/app-mode'
import { AuthProvider } from './app/auth'
import './index.css'

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
