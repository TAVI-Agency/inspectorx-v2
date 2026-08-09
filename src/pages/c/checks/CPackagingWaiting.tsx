import { Link } from 'react-router-dom'
import { AlertTriangle, Check, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { InspectionBundle, PhotoInspectionEventRow } from '@/data'
import { ru } from '@/i18n/ru'
import { failReasonLabel, isRefundableReason, stageLabel } from './report-utils'
import { CCard, CEyebrow } from '../ui'

const t = ru.packagingCheck

/**
 * Экран ожидания: живые стадии, пока `bundle.inspection.status` в
 * `(queued, running)`, и текст причины отказа на `failed`. Поллинг живёт в
 * `useInspectionBundle`/`useInspectionEvents` (Задача 11) — этот компонент
 * только рендерит то, что уже пришло. Терминальный `done` сюда не попадает:
 * `CPackagingReportPage` показывает вместо него полноценный отчёт.
 */
export function CPackagingWaiting({
  bundle,
  events,
}: {
  bundle: InspectionBundle
  events: PhotoInspectionEventRow[] | undefined
}) {
  const { inspection, assets } = bundle
  const sourceKind = inspection.source_kind === 'master_pdf' ? 'master_pdf' : 'photo'

  if (inspection.status === 'failed') {
    const reason = inspection.last_error ?? ''
    const refundable = isRefundableReason(reason)
    return (
      <CCard className="p-6 sm:p-8">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-sanction" aria-hidden />
          <div>
            <p className="text-base font-semibold">{t.failedTitle}</p>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
              {reason ? failReasonLabel(reason) : ru.common.error}
            </p>
            {refundable && (
              <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                {t.failedRefundable}
              </p>
            )}
          </div>
        </div>
        <Button className="mt-5" nativeButton={false} render={<Link to="/checks/packaging" />}>
          {t.startOverCta}
        </Button>
      </CCard>
    )
  }

  // Стадии, которые уже прошли — из событий; 'done'/'failed' сюда не рендерим
  // (терминальные исходы показывает сам родитель), 'rejudge_of'/'retake_of' —
  // тоже не стадии прогресса, а detail-поля события 'received'/'done'.
  const passedStages = (events ?? []).filter((e) => e.stage !== 'done' && e.stage !== 'failed')

  return (
    <CCard className="p-6 sm:p-8">
      <div className="flex items-center gap-3">
        <Loader2 className="size-5 shrink-0 animate-spin text-primary" aria-hidden />
        <div>
          <p className="text-base font-semibold">{t.waitingTitle}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">{t.waitingHint}</p>
        </div>
      </div>

      {passedStages.length > 0 && (
        <ul className="mt-5 space-y-2">
          {passedStages.map((e) => (
            <li key={e.id} className="flex items-center gap-2.5 text-sm">
              <Check className="size-4 shrink-0 text-positive" aria-hidden />
              <span>{stageLabel(e.stage, sourceKind)}</span>
            </li>
          ))}
        </ul>
      )}

      {assets.length > 0 && (
        <div className="mt-6">
          <CEyebrow>{t.framesTitle}</CEyebrow>
          <ul className="mt-2 flex flex-wrap gap-2">
            {assets.map((a) => (
              <li
                key={a.idx}
                className="rounded-[6px] border border-border px-2 py-1 text-xs text-muted-foreground"
              >
                {t.frameLabel(a.idx)}
                {a.face_name !== 'unknown' && ` · ${a.face_name}`}
              </li>
            ))}
          </ul>
        </div>
      )}
    </CCard>
  )
}
