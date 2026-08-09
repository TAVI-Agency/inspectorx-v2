import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Check, ShieldCheck, X } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/app/auth'
import { useIsModerator, useModerateReview, useModerationQueue } from '@/data/hooks'
import type { PhotoModerationItem } from '@/data'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { severityLabel } from './checks/report-utils'
import { CCard, CEyebrow } from './ui'

const t = ru.moderation
const tv = ru.requirement.lawyerReviews

/**
 * Экран модерации заключений юристов по находкам фотоконтроля.
 *
 * Решение владельца («б»): заключение попадает в отчёт клиента только после
 * публикации модератором — автопубликации нет. Единственный путь смены
 * статуса — RPC `moderate_photo_finding_review`
 * (20260810160000_photo_review_moderation.sql); гард ниже — только про UX,
 * настоящая граница живёт в базе.
 */
export function CModerationPage() {
  return (
    <CModeratorGuard>
      <div className="mx-auto max-w-3xl px-4 py-7 sm:px-8">
        <CEyebrow>{t.eyebrow}</CEyebrow>
        <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight sm:text-[30px]">
          {t.title}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">{t.hint}</p>

        <div className="mt-6">
          <CModerationQueue />
        </div>
      </div>
    </CModeratorGuard>
  )
}

/** Раздел модератора: флаг `profiles.is_moderator`, ставит владелец SQL-ом. */
function CModeratorGuard({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth()
  const { data: moderator, isLoading } = useIsModerator()
  if (loading || (session && isLoading)) return null
  if (moderator) return <>{children}</>
  return (
    <div className="mx-auto max-w-6xl px-4 py-24 sm:px-8">
      <CCard className="mx-auto max-w-md p-8 text-center">
        <span className="mx-auto grid size-12 place-items-center rounded-full border border-primary/40 bg-accent text-accent-foreground">
          <ShieldCheck className="size-5" />
        </span>
        <h1 className="mt-4 text-xl font-semibold tracking-tight">{t.denyTitle}</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{t.denyText}</p>
        {!session && (
          <Button className="mt-5" nativeButton={false} render={<Link to="/login" />}>
            {ru.common.signIn}
          </Button>
        )}
      </CCard>
    </div>
  )
}

const SEVERITY_TONE: Record<string, string> = {
  critical: 'bg-sanction/10 text-sanction ring-1 ring-sanction/25 ring-inset',
  major: 'bg-brass/10 text-brass ring-1 ring-brass/25 ring-inset',
  minor: 'bg-secondary text-secondary-foreground',
  info: 'bg-secondary text-muted-foreground',
}

type Decision = 'published' | 'rejected'

function CModerationQueue() {
  const { data: queue, isLoading, isError } = useModerationQueue(true)
  const [pending, setPending] = useState<{ item: PhotoModerationItem; decision: Decision } | null>(
    null,
  )
  // Решённые в этой сессии строки: очередь инвалидируется после мутации, но до
  // прихода свежих данных карточка не должна предлагать решить то же ещё раз.
  const [done, setDone] = useState<Map<string, Decision>>(new Map())

  return (
    <div className="c-rise" style={{ '--i': 1 } as React.CSSProperties}>
      <CCard className="overflow-hidden">
        {isLoading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-4/5" />
          </div>
        ) : isError ? (
          <p className="p-4 text-sm text-muted-foreground">{t.error}</p>
        ) : (queue ?? []).length === 0 ? (
          <p className="p-4 text-sm leading-relaxed text-muted-foreground">{t.empty}</p>
        ) : (
          <ul className="divide-y divide-border">
            {(queue ?? []).map((item) => (
              <CModerationRow
                key={item.reviewId}
                item={item}
                decided={done.get(item.reviewId)}
                onDecide={(decision) => setPending({ item, decision })}
              />
            ))}
          </ul>
        )}
      </CCard>

      <CModerationConfirmDialog
        pending={pending}
        onOpenChange={(v) => {
          if (!v) setPending(null)
        }}
        onDecided={(reviewId, decision) =>
          setDone((prev) => new Map(prev).set(reviewId, decision))
        }
      />
    </div>
  )
}

function CModerationRow({
  item,
  decided,
  onDecide,
}: {
  item: PhotoModerationItem
  decided?: Decision
  onDecide: (decision: Decision) => void
}) {
  return (
    <li className="px-4 py-4">
      {/* Контекст находки: что именно оспорил клиент */}
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
      <p className="mt-1.5 text-sm">
        <span className="text-muted-foreground">{t.findingLabel}: </span>
        {item.message || item.ruleRef}
      </p>

      {/* Заключение юриста */}
      <div className="mt-3 rounded-lg bg-secondary/40 px-3 py-2.5">
        <p className="text-xs text-muted-foreground">
          {t.lawyerLabel}: {item.lawyerName}
          {item.lawyerCredentials ? ` · ${item.lawyerCredentials}` : ''}
        </p>
        <p className="mt-1 text-[13px] font-medium">{tv.verdict[item.verdict]}</p>
        <p className="mt-1 text-sm leading-relaxed whitespace-pre-line">{item.commentText}</p>
      </div>

      <div className="mt-3">
        {decided ? (
          <p
            className={cn(
              'text-xs font-medium',
              decided === 'published' ? 'text-positive' : 'text-muted-foreground',
            )}
          >
            {decided === 'published' ? t.published : t.rejected}
          </p>
        ) : (
          <div className="flex gap-2">
            <Button size="sm" onClick={() => onDecide('published')}>
              <Check />
              {t.publish}
            </Button>
            <Button variant="outline" size="sm" onClick={() => onDecide('rejected')}>
              <X />
              {t.reject}
            </Button>
          </div>
        )}
      </div>
    </li>
  )
}

/** Подтверждение: оба решения необратимы (RPC пускает переход только из pending). */
function CModerationConfirmDialog({
  pending,
  onOpenChange,
  onDecided,
}: {
  pending: { item: PhotoModerationItem; decision: Decision } | null
  onOpenChange: (v: boolean) => void
  onDecided: (reviewId: string, decision: Decision) => void
}) {
  const moderate = useModerateReview()
  const publishing = pending?.decision === 'published'

  function handleOpenChange(v: boolean) {
    onOpenChange(v)
    if (!v) moderate.reset()
  }

  // `review_not_pending` — решение уже принято (вторая вкладка/двойной клик):
  // это не сбой, а устаревший экран, и текст должен об этом сказать прямо.
  const message = (moderate.error as { message?: string } | null)?.message ?? ''
  const errorText = message.includes('review_not_pending') ? t.alreadyModerated : t.actionError

  return (
    <Dialog open={Boolean(pending)} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {publishing ? t.confirmPublishTitle : t.confirmRejectTitle}
          </DialogTitle>
          <DialogDescription>
            {publishing ? t.confirmPublishText : t.confirmRejectText}
          </DialogDescription>
        </DialogHeader>

        {pending && (
          <div className="space-y-4">
            <p className="line-clamp-4 rounded-lg bg-secondary/40 px-3 py-2.5 text-sm leading-relaxed">
              {pending.item.commentText}
            </p>

            {moderate.isError && <p className="text-sm text-destructive">{errorText}</p>}

            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => handleOpenChange(false)}>
                {ru.common.cancel}
              </Button>
              <Button
                size="sm"
                disabled={moderate.isPending}
                onClick={() =>
                  moderate.mutate(
                    { reviewId: pending.item.reviewId, decision: pending.decision },
                    {
                      onSuccess: () => {
                        onDecided(pending.item.reviewId, pending.decision)
                        handleOpenChange(false)
                      },
                    },
                  )
                }
              >
                {publishing ? t.publish : t.reject}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
