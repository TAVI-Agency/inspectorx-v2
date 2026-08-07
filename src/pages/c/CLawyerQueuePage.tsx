import { useState } from 'react'
import { BadgeCheck } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { usePhotoReviewQueue, useSubmitPhotoFindingReview } from '@/data/hooks'
import type { PhotoFindingQueueItem } from '@/data'
import type { ReviewVerdict } from '@/data/types'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { severityLabel } from './checks/report-utils'
import { CCard, CEyebrow } from './ui'
import { CLawyerGuard } from './CLawyerGuard'
import { CReviewQueueCard } from './CLawyerCabinet'

const t = ru.cabinet.lawyer
const tp = ru.packagingCheck

export function CLawyerQueuePage() {
  return (
    <CLawyerGuard>
      <div className="mx-auto max-w-3xl px-4 py-7 sm:px-8">
        <CEyebrow>{ru.cabinet.lawyer.dashboardEyebrow}</CEyebrow>
        <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight sm:text-[30px]">
          {ru.nav.lawyerQueue}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">{ru.cabinet.lawyer.queueHint}</p>

        <div className="mt-6">
          <CReviewQueueCard />
        </div>

        {/* Вторая секция — находки фотоконтроля, эскалированные подписчиками (Задача 14) */}
        <div className="mt-8">
          <CPhotoFindingQueueCard />
        </div>
      </div>
    </CLawyerGuard>
  )
}

const SEVERITY_TONE: Record<string, string> = {
  critical: 'bg-sanction/10 text-sanction ring-1 ring-sanction/25 ring-inset',
  major: 'bg-brass/10 text-brass ring-1 ring-brass/25 ring-inset',
  minor: 'bg-secondary text-secondary-foreground',
  info: 'bg-secondary text-muted-foreground',
}

/**
 * Очередь юриста по находкам фотоконтроля: `photo_finding_queue`
 * (`is_verified_lawyer()` внутри вью) — страница уже под `CLawyerGuard`,
 * поэтому `usePhotoReviewQueue(true)` без дополнительного условия.
 */
function CPhotoFindingQueueCard() {
  const { data: queue, isLoading, isError } = usePhotoReviewQueue(true)
  const [reviewing, setReviewing] = useState<PhotoFindingQueueItem | null>(null)
  // Диалог отправляет заключение, но строка остаётся в очереди до публикации
  // (вью фильтрует только `status = 'published'`) — локально прячем форму,
  // чтобы юрист не отправил второе заключение на ту же находку по ошибке.
  const [submittedIds, setSubmittedIds] = useState<Set<string>>(new Set())

  return (
    <div className="c-rise" style={{ '--i': 2 } as React.CSSProperties}>
      <CEyebrow title={t.photoQueueHint}>{t.photoQueueTitle}</CEyebrow>
      <CCard className="mt-2.5 overflow-hidden">
        {isLoading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-4/5" />
          </div>
        ) : isError ? (
          <p className="p-4 text-sm text-muted-foreground">{t.photoQueueError}</p>
        ) : (queue ?? []).length === 0 ? (
          <p className="p-4 text-sm leading-relaxed text-muted-foreground">{t.photoQueueEmpty}</p>
        ) : (
          <ul className="divide-y divide-border">
            {(queue ?? []).map((item) => (
              <CPhotoQueueRow
                key={item.findingId}
                item={item}
                submitted={submittedIds.has(item.findingId)}
                onReview={() => setReviewing(item)}
              />
            ))}
          </ul>
        )}
      </CCard>

      <CPhotoFindingReviewDialog
        item={reviewing}
        onOpenChange={(v) => {
          if (!v) setReviewing(null)
        }}
        onSubmitted={(findingId) =>
          setSubmittedIds((prev) => new Set(prev).add(findingId))
        }
      />
    </div>
  )
}

function CPhotoQueueRow({
  item,
  submitted,
  onReview,
}: {
  item: PhotoFindingQueueItem
  submitted: boolean
  onReview: () => void
}) {
  return (
    <li className="px-4 py-3.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span
          className={cn(
            'inline-flex h-[19px] items-center rounded-[6px] px-1.5 text-[11px] font-medium',
            SEVERITY_TONE[item.severity] ?? 'bg-secondary text-muted-foreground',
          )}
        >
          {severityLabel(item.severity)}
        </span>
        <span className="text-xs text-muted-foreground">{item.productKey}</span>
      </div>
      <p className="mt-1.5 text-sm">{item.message || item.ruleRef}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {tp.ruleRefLabel}: {item.ruleRef}
      </p>
      <div className="mt-2.5">
        {submitted ? (
          <p className="text-xs font-medium text-positive">{t.photoFinding.submitted}</p>
        ) : (
          <Button variant="outline" size="sm" onClick={onReview}>
            <BadgeCheck />
            {t.photoFinding.submitCta}
          </Button>
        )}
      </div>
    </li>
  )
}

const MIN_CHARS = 20
const VERDICTS: ReviewVerdict[] = ['confirm', 'inaccurate', 'outdated', 'addition']

/** Заключение юриста по находке — вердикт + текст (мин. 20 символов), те же правила, что у требований. */
function CPhotoFindingReviewDialog({
  item,
  onOpenChange,
  onSubmitted,
}: {
  item: PhotoFindingQueueItem | null
  onOpenChange: (v: boolean) => void
  onSubmitted: (findingId: string) => void
}) {
  const tr = ru.requirement.lawyerReviews
  const submit = useSubmitPhotoFindingReview()
  const [verdict, setVerdict] = useState<ReviewVerdict>('confirm')
  const [text, setText] = useState('')

  function reset() {
    submit.reset()
    setText('')
    setVerdict('confirm')
  }

  function handleOpenChange(v: boolean) {
    onOpenChange(v)
    if (!v) reset()
  }

  // 23505 — partial unique index photo_finding_reviews_pending_uidx
  // (lawyer_id, finding_id) where status='pending': строка в очереди не
  // исчезает сразу после сабмита (вью фильтрует только published), локальный
  // submittedIds теряется при перезагрузке — второй клик не должен пугать
  // юриста generic-текстом «не получилось», это ожидаемый повтор.
  const errorCode = (submit.error as { code?: string } | null)?.code
  const errorText =
    errorCode === '23505' ? t.photoFinding.duplicatePending : t.photoFinding.submitError

  return (
    <Dialog open={Boolean(item)} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t.photoFinding.dialogTitle}</DialogTitle>
          {item && (
            <DialogDescription className="line-clamp-2">
              {item.message || item.ruleRef}
            </DialogDescription>
          )}
        </DialogHeader>

        {item && (
          <div className="space-y-4">
            <fieldset>
              <legend className="text-sm font-medium">{tr.dialogVerdictLabel}</legend>
              <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                {VERDICTS.map((v) => (
                  <label
                    key={v}
                    className={cn(
                      'flex cursor-pointer flex-col gap-0.5 rounded-lg border px-3 py-2 transition-colors',
                      verdict === v
                        ? 'border-primary/50 bg-accent/40'
                        : 'border-border hover:border-primary/30',
                    )}
                  >
                    <span className="flex items-center gap-2 text-sm font-medium">
                      <input
                        type="radio"
                        name="photo-finding-verdict"
                        value={v}
                        checked={verdict === v}
                        onChange={() => setVerdict(v)}
                        className="accent-[var(--color-primary)]"
                      />
                      {tr.verdict[v]}
                    </span>
                    <span className="pl-5 text-xs leading-snug text-muted-foreground">
                      {tr.verdictHint[v]}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            <div>
              <label className="text-sm font-medium" htmlFor="photo-finding-review-text">
                {tr.dialogTextLabel}
              </label>
              <textarea
                id="photo-finding-review-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={5}
                placeholder={tr.dialogPlaceholder}
                className="mt-1.5 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
              <p
                className={cn(
                  'mt-1 text-right font-mono text-[11px] tabular-nums',
                  text.trim().length < MIN_CHARS ? 'text-muted-foreground' : 'text-positive',
                )}
              >
                {tr.charsCount(text.trim().length, MIN_CHARS)}
              </p>
            </div>

            {submit.isError && <p className="text-sm text-destructive">{errorText}</p>}

            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => handleOpenChange(false)}>
                {ru.common.cancel}
              </Button>
              <Button
                size="sm"
                disabled={text.trim().length < MIN_CHARS || submit.isPending}
                onClick={() =>
                  submit.mutate(
                    { findingId: item.findingId, verdict, commentText: text.trim() },
                    {
                      onSuccess: () => {
                        onSubmitted(item.findingId)
                        handleOpenChange(false)
                      },
                      // Дубликат — не техническая ошибка: заключение уже стоит в
                      // очереди на модерацию, прячем CTA так же, как при успехе.
                      onError: (err) => {
                        if ((err as { code?: string })?.code === '23505') {
                          onSubmitted(item.findingId)
                        }
                      },
                    },
                  )
                }
              >
                {submit.isPending ? ru.common.sending : ru.common.send}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
