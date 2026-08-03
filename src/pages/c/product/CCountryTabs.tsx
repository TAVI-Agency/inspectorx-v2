import { useState } from 'react'
import { Check, Info } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsIndicator, TabsList, TabsTab } from '@/components/ui/tabs'
import { useContentRequest } from '@/data/hooks'
import type { CountryCode } from '@/data/countries'
import type { CountryCoverage } from '@/data/types'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CCard } from '../ui'

/**
 * Табы стран на карточке товара (Задача 31, Блок 4): УЗ/КЗ/ОАЭ над секцией
 * требований. Смена таба меняет ?country= в URL — за перезагрузку данных
 * отвечает useProductBundle(productId, country) выше по дереву.
 */
export function CCountryTabs({
  coverage,
  country,
  onChange,
  className,
}: {
  coverage: CountryCoverage[]
  country: CountryCode
  onChange: (country: CountryCode) => void
  className?: string
}) {
  return (
    <Tabs
      className={className}
      value={country}
      onValueChange={(value) => onChange(value as CountryCode)}
    >
      {/* Три пилюли редко не влезают, но на узком экране с трёхзначным
          счётчиком (194) — не влезают: тот же скролл-трюк, что у CRouteNavMobile */}
      <div className="-mx-4 overflow-x-auto px-4">
        <TabsList aria-label={ru.product.countryTabsLabel}>
          <TabsIndicator />
          {coverage.map((c) => (
            <TabsTab key={c.country} value={c.country}>
              {ru.product.countryTabLabel(ru.countries[c.country], c.published, c.state)}
            </TabsTab>
          ))}
        </TabsList>
      </div>
    </Tabs>
  )
}

/** Плашка над списком у превью-страны: данные есть, но юрист их ещё не проверял. */
export function CCountryPreviewBanner({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'flex items-start gap-2.5 rounded-lg border border-border bg-secondary/50 px-3.5 py-2.5 text-xs leading-relaxed text-muted-foreground',
        className,
      )}
    >
      <Info aria-hidden className="mt-0.5 size-3.5 shrink-0" />
      <p>{ru.product.countryPreview}</p>
    </div>
  )
}

/**
 * Пустое состояние для страны без покрытия (state: 'none', сейчас — ОАЭ):
 * CTA пишет в content_requests — тот же анонимный механизм заявок, что и
 * пустой поиск (CSearch) и анонсы проверок (CCheckAnnouncePage).
 */
export function CCountryNoneState({
  productId,
  country,
  className,
}: {
  productId: string
  country: CountryCode
  className?: string
}) {
  const request = useContentRequest()
  const storageKey = `ix-notify-country-${productId}-${country}`
  const [done, setDone] = useState(() => localStorage.getItem(storageKey) === '1')

  function notify() {
    request.mutate(
      {
        kind: 'missing_section',
        // Мок-товары не существуют в products — реальную ссылку шлём только для настоящих id
        productId: productId.startsWith('mock-') ? undefined : productId,
        queryText: ru.countries[country],
      },
      {
        onSuccess: () => {
          localStorage.setItem(storageKey, '1')
          setDone(true)
        },
      },
    )
  }

  return (
    <CCard className={cn('p-8 text-center', className)}>
      <h2 className="text-lg font-semibold tracking-tight">{ru.product.countryNoneTitle}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
        {ru.product.countryNoneText}
      </p>
      {done ? (
        <p className="mt-5 inline-flex items-center gap-2 text-sm font-medium text-positive">
          <Check className="size-4" />
          {ru.product.countryNoneDone}
        </p>
      ) : (
        <Button className="mt-5" disabled={request.isPending} onClick={notify}>
          {request.isPending ? ru.common.sending : ru.product.countryNoneCta}
        </Button>
      )}
      {request.isError && (
        <p className="mt-2 text-xs text-destructive">{ru.product.countryNoneError}</p>
      )}
    </CCard>
  )
}
