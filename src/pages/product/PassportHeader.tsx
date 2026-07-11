import { Check, Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/app/auth'
import { useFollowProduct, usePortfolioIds } from '@/data/hooks'
import type { ProductPassport } from '@/data/types'
import { ru } from '@/i18n/ru'
import { formatDate, formatHsCode } from '@/lib/format'

/** Шапка-паспорт: название · коды · штампы «проверено» и сложность (§3.1) */
export function PassportHeader({ passport }: { passport: ProductPassport }) {
  const { session } = useAuth()
  const navigate = useNavigate()
  const { data: portfolio } = usePortfolioIds()
  const follow = useFollowProduct()
  const followed = portfolio?.ids.includes(passport.id) ?? false
  // Мок-товар нельзя добавить в chosen_products (FK на products)
  const canFollow = !passport.id.startsWith('mock-')

  return (
    <header>
      {passport.categoryName && (
        <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
          {passport.categoryName}
        </p>
      )}
      <div className="mt-2 flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 max-w-2xl">
          <h1 className="text-3xl font-semibold tracking-tight text-balance">
            {passport.displayName}
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {ru.product.officialNameLabel}: {passport.officialName}
          </p>
        </div>
        {canFollow && (
          <Button
            variant={followed ? 'secondary' : 'outline'}
            size="sm"
            disabled={follow.isPending || followed}
            onClick={() => {
              if (!session) {
                navigate('/login')
                return
              }
              follow.mutate(passport.id)
            }}
          >
            {followed ? <Check /> : <Plus />}
            {followed ? ru.product.followedCta : ru.product.followCta}
          </Button>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2.5">
        <span className="inline-flex items-baseline gap-2">
          <span className="font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
            {ru.product.hsLabel}
          </span>
          <span className="font-mono text-sm font-medium">
            {formatHsCode(passport.hsCode)}
          </span>
        </span>
        {passport.ikpuCode && (
          <span className="inline-flex items-baseline gap-2">
            <span className="font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
              {ru.product.ikpuLabel}
            </span>
            <span className="font-mono text-sm font-medium">{passport.ikpuCode}</span>
          </span>
        )}
        {typeof passport.complexity === 'number' && (
          <span className="stamp text-muted-foreground">
            {ru.product.complexity(passport.complexity)}
          </span>
        )}
        {passport.verifiedAt && (
          <span className="stamp -rotate-1 text-positive">
            {ru.product.checkedStamp(formatDate(passport.verifiedAt))}
          </span>
        )}
      </div>
    </header>
  )
}
