import { useState } from 'react'
import { ArrowLeft, Bell, Camera, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useContentRequest, usePackagingChecklist } from '@/data/hooks'
import type { PackagingChecklist, PackagingLevel } from '@/data'
import type { SearchHit } from '@/data/types'
import type { UseQueryResult } from '@tanstack/react-query'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CCard, CEyebrow, CStatTile, CountUp } from '../ui'
import { CSearch } from '../CSearch'
import { CPackagingUpload } from './CPackagingUpload'

const t = ru.packagingCheck

type Step =
  | { name: 'pick' }
  | { name: 'checklist'; hit: SearchHit }
  | { name: 'upload'; hit: SearchHit }

/**
 * Проверка упаковки: выбор товара (общий поиск, перехваченный `onPick`) →
 * бесплатный тизер чек-листа «Что проверим» → загрузка макета/фото. Машина
 * состояний в одном компоненте — четыре шага брифа, `level` живёт отдельно
 * от `step`, чтобы его можно было менять и до, и после выбора товара.
 */
export function CPackagingCheckPage() {
  const [level, setLevel] = useState<PackagingLevel>('consumer')
  const [step, setStep] = useState<Step>({ name: 'pick' })

  const productId = step.name === 'pick' ? undefined : step.hit.id
  const checklist = usePackagingChecklist(productId, level)

  return (
    <div className="mx-auto max-w-3xl px-4 py-7 sm:px-8">
      <div className="flex items-center gap-3">
        {step.name !== 'pick' && (
          <Button
            variant="outline"
            size="icon"
            onClick={() => setStep({ name: 'pick' })}
            aria-label={t.changeProduct}
          >
            <ArrowLeft />
          </Button>
        )}
        <div>
          <CEyebrow>{ru.nav.checksSection}</CEyebrow>
          <h1 className="font-display mt-1 text-[22px] leading-tight font-medium tracking-tight sm:text-[28px]">
            {t.title}
          </h1>
        </div>
      </div>

      {step.name !== 'pick' && (
        <p className="mt-2 text-sm text-muted-foreground">{step.hit.displayName}</p>
      )}

      <div className="mt-6">
        {step.name === 'pick' && (
          <PickStep
            level={level}
            onLevel={setLevel}
            onPick={(hit) => setStep({ name: 'checklist', hit })}
          />
        )}
        {step.name === 'checklist' && (
          <ChecklistStep
            hit={step.hit}
            level={level}
            onLevel={setLevel}
            checklist={checklist}
            onUpload={() => setStep({ name: 'upload', hit: step.hit })}
          />
        )}
        {step.name === 'upload' &&
          (checklist.data ? (
            <CPackagingUpload
              productId={step.hit.id}
              level={level}
              hints={checklist.data.hints}
              onBack={() => setStep({ name: 'checklist', hit: step.hit })}
            />
          ) : (
            // Практически недостижимо: на upload переходят только с непустым
            // checklist.data (кнопка в ChecklistStep), а он остаётся в кэше
            // React Query под тем же ключом (productId, level). Явный текст
            // вместо пустого экрана — на случай гонки/сброса кэша.
            <CCard className="p-6 text-center text-sm text-muted-foreground">
              {t.noChecklistTitle}
            </CCard>
          ))}
      </div>
    </div>
  )
}

/** Переключатель уровня упаковки — тот же визуальный язык, что у переключателя товар/услуга в CSearch */
function LevelToggle({
  level,
  onChange,
  className,
}: {
  level: PackagingLevel
  onChange: (level: PackagingLevel) => void
  className?: string
}) {
  return (
    <div className={cn('inline-flex rounded-lg border border-border bg-card p-0.5', className)}>
      {(['consumer', 'transport'] as const).map((l) => (
        <button
          key={l}
          type="button"
          aria-pressed={level === l}
          onClick={() => onChange(l)}
          className={cn(
            'rounded-[7px] px-3.5 py-1.5 text-[13px] font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
            level === l
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {l === 'consumer' ? t.levelConsumer : t.levelTransport}
        </button>
      ))}
    </div>
  )
}

function PickStep({
  level,
  onLevel,
  onPick,
}: {
  level: PackagingLevel
  onLevel: (level: PackagingLevel) => void
  onPick: (hit: SearchHit) => void
}) {
  return (
    <div className="space-y-6">
      <div>
        <CEyebrow>{t.pickLevel}</CEyebrow>
        <LevelToggle level={level} onChange={onLevel} className="mt-2" />
      </div>
      <div>
        <p className="mb-3 text-sm text-muted-foreground">{t.pickProduct}</p>
        <CSearch
          autoFocus
          onPick={(hit) => {
            if (hit.kind !== 'product') return false
            onPick(hit)
            return true
          }}
        />
      </div>
    </div>
  )
}

function ChecklistStep({
  hit,
  level,
  onLevel,
  checklist,
  onUpload,
}: {
  hit: SearchHit
  level: PackagingLevel
  onLevel: (level: PackagingLevel) => void
  checklist: UseQueryResult<PackagingChecklist | null>
  onUpload: () => void
}) {
  const request = useContentRequest()
  const [notified, setNotified] = useState(false)

  if (checklist.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (checklist.isError) {
    return (
      <CCard className="p-6 text-center">
        <p className="text-sm text-destructive">{ru.common.error}</p>
        <Button variant="outline" className="mt-4" onClick={() => void checklist.refetch()}>
          {ru.common.retry}
        </Button>
      </CCard>
    )
  }

  if (!checklist.data) {
    // checklist.data === null — легитимный «нет чек-листа» (404 no_checklist);
    // undefined сюда доходит только на не-loading/не-error переходном тике
    // React Query (enabled всегда true — productId уже выбран) — тот же текст,
    // не пустой экран.
    // Отсутствие чек-листа ≠ «нарушений нет» — явный текст, не пустой зелёный экран
    return (
      <CCard className="p-8 text-center">
        <p className="text-base font-semibold">{t.noChecklistTitle}</p>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
          {t.noChecklistText}
        </p>
        {notified ? (
          <p className="mt-5 inline-flex items-center gap-2 text-sm font-medium text-positive">
            <Check className="size-4" />
            {t.notifyDone}
          </p>
        ) : (
          <Button
            variant="outline"
            className="mt-5"
            disabled={request.isPending}
            onClick={() =>
              request.mutate(
                {
                  kind: 'missing_section',
                  queryText: `Проверка упаковки: ${hit.displayName}`,
                  // Мок-товары (например, парацетамол) не существуют в products — реальную ссылку шлём только для настоящих id
                  productId: hit.id.startsWith('mock-') ? undefined : hit.id,
                },
                { onSuccess: () => setNotified(true) },
              )
            }
          >
            <Bell />
            {request.isPending ? ru.common.sending : t.notifyCta}
          </Button>
        )}
      </CCard>
    )
  }

  const c = checklist.data

  return (
    <div className="space-y-6">
      <LevelToggle level={level} onChange={onLevel} />

      <div>
        <h2 className="font-display text-lg font-medium tracking-tight">{c.title}</h2>
        <CEyebrow className="mt-2">{t.whatWeCheck}</CEyebrow>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <CStatTile
            label={t.counterCheckable}
            tone="positive"
            value={<CountUp value={c.counters.checkable} />}
            index={0}
          />
          <CStatTile label={t.counterPartial} value={<CountUp value={c.counters.partial} />} index={1} />
          <CStatTile
            label={t.counterNotCheckable}
            value={<CountUp value={c.counters.notCheckable} />}
            index={2}
          />
          <CStatTile label={t.counterNoGold} value={<CountUp value={c.counters.noGold} />} index={3} />
        </div>
      </div>

      {c.groups.length > 0 && (
        <div className="space-y-3">
          {c.groups.map((group) => (
            <CCard key={group.key} className="p-4">
              <p className="text-sm font-semibold">{group.title ?? group.key}</p>
              {group.items.length > 0 && (
                <ul className="mt-2 space-y-1.5">
                  {group.items.map((item) => (
                    <li key={item.key} className="flex items-start gap-2 text-sm text-muted-foreground">
                      <Check className="mt-0.5 size-3.5 shrink-0 text-positive" aria-hidden />
                      <span>{typeof item.title === 'string' ? item.title : item.key}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CCard>
          ))}
        </div>
      )}

      <Button onClick={onUpload}>
        <Camera />
        {t.uploadCta}
      </Button>
    </div>
  )
}
