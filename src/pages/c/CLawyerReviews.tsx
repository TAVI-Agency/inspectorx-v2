import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BadgeCheck,
  CircleCheck,
  Clock,
  MessageSquarePlus,
  ThumbsDown,
  ThumbsUp,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/app/auth'
import {
  useLawyerReviews,
  useMyLawyerProfile,
  useSetReviewVote,
} from '@/data/hooks'
import type { LawyerReview, RequirementRow, ReviewVerdict } from '@/data/types'
import { formatDate } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { LawyerReviewDialog } from '@/components/LawyerReviewDialog'
import { CEyebrow } from './ui'

const VERDICT_ICON: Record<ReviewVerdict, LucideIcon> = {
  confirm: CircleCheck,
  inaccurate: TriangleAlert,
  outdated: Clock,
  addition: MessageSquarePlus,
}

/** Чип вердикта: подтверждение — изумруд, замечания — предупреждение, дополнение — нейтраль */
export function CVerdictChip({ verdict }: { verdict: ReviewVerdict }) {
  const Icon = VERDICT_ICON[verdict]
  return (
    <span
      className={cn(
        'inline-flex h-[19px] shrink-0 items-center gap-1 rounded-[6px] px-1.5 text-[11px] font-medium',
        verdict === 'confirm' &&
          'bg-positive/10 text-positive ring-1 ring-positive/25 ring-inset',
        (verdict === 'inaccurate' || verdict === 'outdated') &&
          'bg-sanction/10 text-sanction ring-1 ring-sanction/25 ring-inset',
        verdict === 'addition' && 'bg-secondary text-secondary-foreground',
      )}
    >
      <Icon className="size-3" />
      {ru.requirement.lawyerReviews.verdict[verdict]}
    </span>
  )
}

/**
 * Секция «Проверка юристами» в раскрытой карточке требования.
 * Published-заключения видят все; свои pending юрист видит с пометкой.
 */
export function CLawyerReviewsSection({ row }: { row: RequirementRow }) {
  const t = ru.requirement.lawyerReviews
  const { session } = useAuth()
  const { data: reviews, isLoading, isError } = useLawyerReviews(row.id)
  const { data: lawyerProfile } = useMyLawyerProfile()
  const [dialogOpen, setDialogOpen] = useState(false)

  const verified = lawyerProfile?.status === 'verified'
  const hasOwnPending = (reviews ?? []).some((r) => r.isMine && r.status === 'pending')

  return (
    <section>
      <CEyebrow>{t.title}</CEyebrow>

      {isLoading ? (
        <div className="mt-3 space-y-2">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : isError ? (
        <p className="mt-2 text-sm text-muted-foreground">{t.loadError}</p>
      ) : (
        <>
          {(reviews ?? []).length === 0 ? (
            <p className="mt-2 text-sm text-muted-foreground">{t.empty}</p>
          ) : (
            <div className="mt-3 space-y-2.5">
              {(reviews ?? []).map((review) => (
                <CReviewItem
                  key={review.id}
                  review={review}
                  requirementId={row.id}
                  isAuthed={Boolean(session)}
                />
              ))}
            </div>
          )}

          {verified && (
            <div className="mt-3">
              {hasOwnPending ? (
                <p className="text-xs text-muted-foreground">{t.pendingExists}</p>
              ) : (
                <Button variant="outline" size="sm" onClick={() => setDialogOpen(true)}>
                  <BadgeCheck />
                  {t.leaveReview}
                </Button>
              )}
            </div>
          )}

          <p className="mt-3 text-[11px] text-muted-foreground/80">{t.disclaimer}</p>
        </>
      )}

      <LawyerReviewDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        requirementId={row.id}
        requirementTitle={row.title}
      />
    </section>
  )
}

function CReviewItem({
  review,
  requirementId,
  isAuthed,
}: {
  review: LawyerReview
  requirementId: string
  isAuthed: boolean
}) {
  const t = ru.requirement.lawyerReviews
  return (
    <article
      className={cn(
        'rounded-lg border border-border bg-card p-3.5 sm:p-4',
        review.status === 'pending' && 'border-dashed opacity-80',
      )}
    >
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <CVerdictChip verdict={review.verdict} />
        <span className="text-sm font-semibold tracking-tight">{review.lawyerName}</span>
        {review.credentials && (
          <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
            {review.credentials}
          </span>
        )}
        {review.status === 'pending' && (
          <span className="rounded-[6px] bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
            {t.onModeration}
          </span>
        )}
      </header>

      <p className="mt-2 text-sm leading-relaxed whitespace-pre-line">
        {review.commentText}
      </p>

      {review.officialReply && (
        <div className="mt-3 rounded-lg border border-positive/25 bg-positive/[0.05] p-3">
          <p className="inline-flex items-center gap-1.5 font-mono text-[10px] font-medium tracking-[0.08em] text-positive uppercase">
            <BadgeCheck className="size-3.5" />
            {t.officialReply}
          </p>
          <p className="mt-1.5 text-sm leading-relaxed">{review.officialReply}</p>
        </div>
      )}

      <footer className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {review.status === 'published' && (
          <CVoteControls review={review} requirementId={requirementId} isAuthed={isAuthed} />
        )}
        <span className="ml-auto font-mono text-[11px] text-muted-foreground">
          {formatDate(review.createdAt)}
        </span>
      </footer>
    </article>
  )
}

/**
 * Голоса «помогло/не помогло». Аноним видит счётчики, клик ведёт на /login;
 * за собственное заключение голосовать нельзя — только счётчики.
 */
function CVoteControls({
  review,
  requirementId,
  isAuthed,
}: {
  review: LawyerReview
  requirementId: string
  isAuthed: boolean
}) {
  const t = ru.requirement.lawyerReviews
  const setVote = useSetReviewVote(requirementId)

  if (!isAuthed) {
    return (
      <Link
        to="/login"
        aria-label={t.loginToVote}
        title={t.loginToVote}
        className="inline-flex items-center gap-3 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <span className="inline-flex items-center gap-1.5">
          <ThumbsUp className="size-3.5" />
          {t.helpful}
          <span className="font-mono tabular-nums">{review.helpful}</span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <ThumbsDown className="size-3.5" />
          {t.notHelpful}
          <span className="font-mono tabular-nums">{review.notHelpful}</span>
        </span>
      </Link>
    )
  }

  if (review.isMine) {
    return (
      <span className="inline-flex items-center gap-3 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <ThumbsUp className="size-3.5" />
          {t.helpful}
          <span className="font-mono tabular-nums">{review.helpful}</span>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <ThumbsDown className="size-3.5" />
          {t.notHelpful}
          <span className="font-mono tabular-nums">{review.notHelpful}</span>
        </span>
      </span>
    )
  }

  const vote = (value: 1 | -1) =>
    setVote.mutate({
      reviewId: review.id,
      vote: review.myVote === value ? null : value,
    })

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        aria-pressed={review.myVote === 1}
        onClick={() => vote(1)}
        className={cn(
          'inline-flex h-7 items-center gap-1.5 rounded-lg border px-2 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
          review.myVote === 1
            ? 'border-positive/45 bg-positive/10 text-positive'
            : 'border-border text-muted-foreground hover:border-positive/40 hover:text-positive',
        )}
      >
        <ThumbsUp className="size-3.5" />
        {t.helpful}
        <span className="font-mono tabular-nums">{review.helpful}</span>
      </button>
      <button
        type="button"
        aria-pressed={review.myVote === -1}
        onClick={() => vote(-1)}
        className={cn(
          'inline-flex h-7 items-center gap-1.5 rounded-lg border px-2 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
          review.myVote === -1
            ? 'border-sanction/45 bg-sanction/10 text-sanction'
            : 'border-border text-muted-foreground hover:border-sanction/40 hover:text-sanction',
        )}
      >
        <ThumbsDown className="size-3.5" />
        {t.notHelpful}
        <span className="font-mono tabular-nums">{review.notHelpful}</span>
      </button>
    </span>
  )
}
