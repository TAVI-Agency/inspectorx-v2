import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Clock,
  Download,
  Scale,
  Send,
  Share2,
  ThumbsDown,
  ThumbsUp,
  Trophy,
} from 'lucide-react'
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
import {
  useLawyerApplication,
  useLeaderboard,
  useMyLawyerProfile,
  useMyReviews,
  useReviewQueue,
} from '@/data/hooks'
import type { LawyerProfile, MyReviewItem, ReviewQueueItem } from '@/data/types'
import {
  downloadCanvasPng,
  drawShareCard,
  SHARE_CARD_H,
  SHARE_CARD_W,
} from '@/lib/share-card'
import { formatDate } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CCard, CEyebrow } from './ui'
import { CVerdictChip } from './CLawyerReviews'

const t = ru.cabinet.lawyer

// ── Заявка «стать экспертом» (левая колонка кабинета) ──────────────

/**
 * Состояния до верификации: приглашение → форма → «на рассмотрении» →
 * (при отказе) «отклонена» + повторная подача. Verified рисуется дешбордом.
 */
export function CLawyerApplicationCard() {
  const { session } = useAuth()
  const { data: profile, isLoading } = useMyLawyerProfile()
  const [formOpen, setFormOpen] = useState(false)

  if (!session || isLoading || profile?.status === 'verified') return null

  if (profile?.status === 'pending') {
    return (
      <CCard className="p-4 sm:p-5">
        <p className="inline-flex items-center gap-2 text-sm font-semibold tracking-tight">
          <Clock className="size-4 text-brass" />
          {t.pendingTitle}
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
          {t.pendingText}
        </p>
      </CCard>
    )
  }

  if (profile?.status === 'rejected' && !formOpen) {
    return (
      <CCard className="p-4 sm:p-5">
        <p className="text-sm font-semibold tracking-tight">{t.rejectedTitle}</p>
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
          {t.rejectedText}
        </p>
        <Button size="sm" variant="outline" className="mt-3.5" onClick={() => setFormOpen(true)}>
          {t.reapplyCta}
        </Button>
      </CCard>
    )
  }

  if (!profile && !formOpen) {
    return (
      <CCard className="p-4 sm:p-5">
        <p className="inline-flex items-center gap-2 text-sm font-semibold tracking-tight">
          <Scale className="size-4 text-primary" />
          {t.becomeTitle}
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{t.becomeText}</p>
        <Button size="sm" className="mt-3.5" onClick={() => setFormOpen(true)}>
          {t.becomeCta}
        </Button>
      </CCard>
    )
  }

  return <CLawyerApplicationForm profile={profile ?? null} onDone={() => setFormOpen(false)} />
}

function CLawyerApplicationForm({
  profile,
  onDone,
}: {
  profile: LawyerProfile | null
  onDone: () => void
}) {
  const apply = useLawyerApplication()
  const [name, setName] = useState(profile?.displayName ?? '')
  const [credentials, setCredentials] = useState(profile?.credentials ?? '')
  const [licenseNo, setLicenseNo] = useState(profile?.licenseNo ?? '')
  const [specializations, setSpecializations] = useState(profile?.specializations ?? '')
  const [touched, setTouched] = useState(false)

  const nameError = touched && !name.trim() ? t.form.nameRequired : null
  const credError = touched && !credentials.trim() ? t.form.credentialsRequired : null

  function submit() {
    setTouched(true)
    if (!name.trim() || !credentials.trim()) return
    apply.mutate(
      {
        displayName: name.trim(),
        credentials: credentials.trim(),
        licenseNo: licenseNo.trim() || undefined,
        specializations: specializations.trim() || undefined,
      },
      { onSuccess: onDone },
    )
  }

  const inputClass =
    'mt-1 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50'

  return (
    <CCard className="p-4 sm:p-5">
      <p className="text-sm font-semibold tracking-tight">{t.becomeTitle}</p>
      <div className="mt-3 space-y-3">
        <label className="block text-xs font-medium">
          {t.form.nameLabel}
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t.form.namePlaceholder}
            className={inputClass}
          />
          {nameError && <span className="mt-1 block font-normal text-destructive">{nameError}</span>}
        </label>
        <label className="block text-xs font-medium">
          {t.form.credentialsLabel}
          <input
            value={credentials}
            onChange={(e) => setCredentials(e.target.value)}
            placeholder={t.form.credentialsPlaceholder}
            className={inputClass}
          />
          {credError && <span className="mt-1 block font-normal text-destructive">{credError}</span>}
        </label>
        <label className="block text-xs font-medium">
          {t.form.licenseLabel}
          <input
            value={licenseNo}
            onChange={(e) => setLicenseNo(e.target.value)}
            placeholder={t.form.licensePlaceholder}
            className={inputClass}
          />
        </label>
        <label className="block text-xs font-medium">
          {t.form.specializationsLabel}
          <input
            value={specializations}
            onChange={(e) => setSpecializations(e.target.value)}
            placeholder={t.form.specializationsPlaceholder}
            className={inputClass}
          />
        </label>
      </div>
      {apply.isError && <p className="mt-2.5 text-xs text-destructive">{t.form.error}</p>}
      <div className="mt-3.5 flex gap-2">
        <Button size="sm" disabled={apply.isPending} onClick={submit}>
          <Send />
          {apply.isPending ? ru.common.sending : t.form.submit}
        </Button>
      </div>
    </CCard>
  )
}

// ── Очередь «Ждут проверки» ────────────────────────────────────────

export function CReviewQueueCard() {
  const { data: queue, isLoading, isError } = useReviewQueue(true)

  return (
    <div className="c-rise" style={{ '--i': 1 } as React.CSSProperties}>
      <CEyebrow title={t.queueHint}>{t.queueTitle}</CEyebrow>
      <CCard className="mt-2.5 overflow-hidden">
        {isLoading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-4/5" />
            <Skeleton className="h-5 w-5/6" />
          </div>
        ) : isError ? (
          <p className="p-4 text-sm text-muted-foreground">{t.queueError}</p>
        ) : (queue ?? []).length === 0 ? (
          <p className="p-4 text-sm leading-relaxed text-muted-foreground">{t.queueEmpty}</p>
        ) : (
          <ul className="divide-y divide-border">
            {(queue ?? []).map((item, i) => (
              <CQueueRow key={item.requirementId} item={item} number={i + 1} />
            ))}
          </ul>
        )}
      </CCard>
    </div>
  )
}

function CQueueRow({ item, number }: { item: ReviewQueueItem; number: number }) {
  const body = (
    <>
      <span className="mt-0.5 shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
        {String(number).padStart(2, '0')}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{item.title}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground">
          {item.targetName}
          {item.targetName && item.publishedAt ? ' · ' : ''}
          {item.publishedAt ? formatDate(item.publishedAt) : ''}
        </span>
      </span>
      <ArrowRight className="mt-1 size-3.5 shrink-0 text-muted-foreground transition-transform duration-300 group-hover:translate-x-0.5 group-hover:text-primary" />
    </>
  )
  if (!item.link) {
    return <li className="flex items-start gap-3 px-4 py-3">{body}</li>
  }
  return (
    <li>
      <Link
        to={item.link}
        className="group flex items-start gap-3 px-4 py-3 transition-colors hover:bg-secondary/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        {body}
      </Link>
    </li>
  )
}

// ── Мои заключения ─────────────────────────────────────────────────

const REVIEW_STATUS_TONE: Record<MyReviewItem['status'], string> = {
  pending: 'bg-secondary text-muted-foreground',
  published: 'bg-positive/10 text-positive',
  rejected: 'bg-sanction/10 text-sanction',
}

export function CMyReviewsCard() {
  const { data: reviews, isLoading } = useMyReviews(true)

  return (
    <div className="c-rise" style={{ '--i': 2 } as React.CSSProperties}>
      <CEyebrow>{t.myReviewsTitle}</CEyebrow>
      <CCard className="mt-2.5 overflow-hidden">
        {isLoading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-3/4" />
          </div>
        ) : (reviews ?? []).length === 0 ? (
          <p className="p-4 text-sm leading-relaxed text-muted-foreground">
            {t.myReviewsEmpty}
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {(reviews ?? []).map((r) => (
              <li key={r.id} className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <CVerdictChip verdict={r.verdict} />
                  <span
                    className={cn(
                      'rounded-[6px] px-1.5 py-0.5 text-[10px] font-medium',
                      REVIEW_STATUS_TONE[r.status],
                    )}
                  >
                    {t.reviewStatus[r.status]}
                  </span>
                  <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                    {formatDate(r.createdAt)}
                  </span>
                </div>
                <p className="mt-1.5 truncate text-sm font-medium">
                  {r.link ? (
                    <Link to={r.link} className="hover:text-primary hover:underline underline-offset-2">
                      {r.requirementTitle}
                    </Link>
                  ) : (
                    r.requirementTitle
                  )}
                </p>
                {r.status === 'published' && (
                  <p className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <ThumbsUp className="size-3 text-positive" />
                      <span className="font-mono tabular-nums">{r.helpful}</span>
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <ThumbsDown className="size-3" />
                      <span className="font-mono tabular-nums">{r.notHelpful}</span>
                    </span>
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </CCard>
    </div>
  )
}

// ── Рейтинг юристов ────────────────────────────────────────────────

export function CLeaderboardCard() {
  const { session } = useAuth()
  const { data: leaderboard, isLoading } = useLeaderboard()
  const me = leaderboard?.me

  return (
    <div className="c-rise min-w-0" style={{ '--i': 3 } as React.CSSProperties}>
      <CEyebrow title={t.leaderboardHint}>{t.leaderboardTitle}</CEyebrow>
      <CCard className="mt-2.5 overflow-hidden">
        <div className="border-b border-border bg-accent/30 px-4 py-3.5">
          <p className="inline-flex items-center gap-2 text-sm font-semibold tracking-tight">
            <Trophy className="size-4 text-brass" />
            {me
              ? t.yourPlace(me.rank, leaderboard?.total ?? 0)
              : t.yourPlaceNone}
          </p>
          {!me && (
            <p className="mt-0.5 text-xs text-muted-foreground">{t.noRankHint}</p>
          )}
        </div>
        {isLoading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-5/6" />
            <Skeleton className="h-5 w-4/6" />
          </div>
        ) : (leaderboard?.top ?? []).length === 0 ? (
          <p className="p-4 text-sm leading-relaxed text-muted-foreground">
            {t.leaderboardEmpty}
          </p>
        ) : (
          <ol className="divide-y divide-border">
            {(leaderboard?.top ?? []).map((entry) => {
              const mine = entry.lawyerId === session?.user.id
              return (
                <li
                  key={entry.lawyerId}
                  className={cn(
                    'flex items-center gap-3 px-4 py-2.5',
                    mine && 'bg-accent/40',
                  )}
                >
                  <span
                    className={cn(
                      'w-7 shrink-0 font-mono text-[13px] font-semibold tabular-nums',
                      entry.rank <= 3 ? 'text-brass' : 'text-muted-foreground',
                    )}
                  >
                    {entry.rank}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 text-sm font-medium">
                      <span className="truncate">{entry.displayName}</span>
                      {mine && (
                        <span className="shrink-0 rounded-[4px] bg-primary/10 px-1 text-[10px] font-semibold text-primary">
                          {t.you}
                        </span>
                      )}
                    </span>
                    {entry.credentials && (
                      <span className="block truncate text-[11px] text-muted-foreground">
                        {entry.credentials}
                      </span>
                    )}
                  </span>
                  <span
                    className="inline-flex shrink-0 items-center gap-1 font-mono text-[13px] text-positive tabular-nums"
                    title={t.leaderboardHint}
                  >
                    <ThumbsUp className="size-3" />
                    {entry.helpfulTotal}
                  </span>
                </li>
              )
            })}
          </ol>
        )}
      </CCard>
    </div>
  )
}

// ── Share-карточка статистики ──────────────────────────────────────

export function CShareStatsButton({
  profile,
  reviewed,
  helpful,
  rank,
}: {
  profile: LawyerProfile
  reviewed: number
  helpful: number
  rank?: { place: number; total: number }
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <Share2 />
        {t.share.cta}
      </Button>
      {open && (
        <CShareStatsDialog
          open={open}
          onOpenChange={setOpen}
          profile={profile}
          reviewed={reviewed}
          helpful={helpful}
          rank={rank}
        />
      )}
    </>
  )
}

function CShareStatsDialog({
  open,
  onOpenChange,
  profile,
  reviewed,
  helpful,
  rank,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  profile: LawyerProfile
  reviewed: number
  helpful: number
  rank?: { place: number; total: number }
}) {
  // Контент диалога монтируется порталом асинхронно — ловим появление
  // canvas колбэк-рефом, обычный ref в первом эффекте ещё пуст.
  const [canvasEl, setCanvasEl] = useState<HTMLCanvasElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!canvasEl) return
    let cancelled = false
    void drawShareCard(canvasEl, {
      name: profile.displayName,
      credentials: profile.credentials,
      reviewed,
      helpful,
      rank,
    }).then(() => {
      if (!cancelled) setReady(true)
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- rank сравнивается по полям
  }, [canvasEl, profile, reviewed, helpful, rank?.place, rank?.total])

  const telegramUrl = `https://t.me/share/url?url=${encodeURIComponent(
    'https://inspectorx.uz',
  )}&text=${encodeURIComponent(t.share.tgText(reviewed, helpful))}`

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t.share.dialogTitle}</DialogTitle>
          <DialogDescription>{t.share.dialogText}</DialogDescription>
        </DialogHeader>
        <div className="overflow-hidden rounded-lg border border-border">
          <canvas
            ref={(el) => {
              canvasRef.current = el
              setCanvasEl(el)
            }}
            width={SHARE_CARD_W}
            height={SHARE_CARD_H}
            className="block h-auto w-full"
            aria-label={t.share.dialogTitle}
          />
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!ready}
            onClick={() =>
              canvasRef.current &&
              downloadCanvasPng(canvasRef.current, 'inspectorx-expert.png')
            }
          >
            <Download />
            {ready ? t.share.download : t.share.preparing}
          </Button>
          <Button
            size="sm"
            nativeButton={false}
            render={<a href={telegramUrl} target="_blank" rel="noreferrer" />}
          >
            <Send />
            {t.share.telegram}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
