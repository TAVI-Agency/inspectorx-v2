import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col items-start gap-4 px-4 py-24 sm:px-6">
      <p className="font-mono text-xs tracking-[0.08em] text-muted-foreground uppercase">
        Ошибка 404
      </p>
      <h1 className="text-2xl font-semibold tracking-tight">
        Такой страницы нет
      </h1>
      <Button render={<Link to="/" />} variant="outline">
        На главную
      </Button>
    </div>
  )
}
