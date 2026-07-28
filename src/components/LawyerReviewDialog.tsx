import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useSubmitLawyerReview } from '@/data/hooks'
import type { ReviewVerdict } from '@/data/types'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'

const MIN_CHARS = 20
const VERDICTS: ReviewVerdict[] = ['confirm', 'inaccurate', 'outdated', 'addition']

/**
 * «Оставить заключение» — форма верифицированного юриста.
 * Вердикт + текст (мин. 20 символов) → строка pending на премодерацию.
 */
export function LawyerReviewDialog({
  open,
  onOpenChange,
  requirementId,
  requirementTitle,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  requirementId: string
  requirementTitle: string
}) {
  const t = ru.requirement.lawyerReviews
  const submit = useSubmitLawyerReview()
  const [verdict, setVerdict] = useState<ReviewVerdict>('confirm')
  const [text, setText] = useState('')

  function handleOpenChange(v: boolean) {
    onOpenChange(v)
    if (!v && submit.isSuccess) {
      submit.reset()
      setText('')
      setVerdict('confirm')
    }
  }

  // 23505 — частичный уникальный индекс: второе pending на то же требование
  const errorCode = (submit.error as { code?: string } | null)?.code
  const errorText = errorCode === '23505' ? t.duplicatePending : t.submitError

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t.dialogTitle}</DialogTitle>
          <DialogDescription className="line-clamp-2">
            {requirementTitle}
          </DialogDescription>
        </DialogHeader>

        {submit.isSuccess ? (
          <p className="text-sm text-positive">{t.submitted}</p>
        ) : (
          <div className="space-y-4">
            <fieldset>
              <legend className="text-sm font-medium">{t.dialogVerdictLabel}</legend>
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
                        name="verdict"
                        value={v}
                        checked={verdict === v}
                        onChange={() => setVerdict(v)}
                        className="accent-[var(--color-primary)]"
                      />
                      {t.verdict[v]}
                    </span>
                    <span className="pl-5 text-xs leading-snug text-muted-foreground">
                      {t.verdictHint[v]}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            <div>
              <label className="text-sm font-medium" htmlFor="review-text">
                {t.dialogTextLabel}
              </label>
              <textarea
                id="review-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={5}
                placeholder={t.dialogPlaceholder}
                className="mt-1.5 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
              <p
                className={cn(
                  'mt-1 text-right font-mono text-[11px] tabular-nums',
                  text.trim().length < MIN_CHARS
                    ? 'text-muted-foreground'
                    : 'text-positive',
                )}
              >
                {t.charsCount(text.trim().length, MIN_CHARS)}
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
                  submit.mutate({ requirementId, verdict, commentText: text.trim() })
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
