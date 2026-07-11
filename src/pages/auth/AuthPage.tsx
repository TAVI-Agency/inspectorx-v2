export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      {mode === 'login' ? 'Вход' : 'Регистрация'} — в работе
    </div>
  )
}
