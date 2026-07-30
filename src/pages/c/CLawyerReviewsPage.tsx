import { BadgeCheck } from 'lucide-react'
import { useLawyerStats, useLeaderboard, useMyLawyerProfile } from '@/data/hooks'
import { ru } from '@/i18n/ru'
import { CEyebrow, CStatTile, CountUp } from './ui'
import { CLawyerGuard } from './CLawyerGuard'
import { CLeaderboardCard, CMyReviewsCard, CShareStatsButton } from './CLawyerCabinet'

const t = ru.cabinet.lawyer

function CLawyerReviewsContent() {
  const { data: profile } = useMyLawyerProfile()
  const verified = profile?.status === 'verified'
  const { data: stats } = useLawyerStats()
  const { data: leaderboard } = useLeaderboard()

  if (!verified || !profile) return null

  const rank = leaderboard?.me

  return (
    <div className="mx-auto max-w-6xl px-4 py-7 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <CEyebrow>{t.dashboardEyebrow}</CEyebrow>
          <h1 className="font-display mt-1.5 flex flex-wrap items-center gap-2 text-[22px] leading-tight font-medium tracking-tight sm:text-[30px]">
            {profile.displayName}
            <span className="inline-flex items-center gap-1 rounded-[4px] border border-positive/40 px-2 py-0.5 font-mono text-[10px] font-medium tracking-[0.08em] text-positive uppercase">
              <BadgeCheck className="size-3.5" />
              {t.verifiedStamp}
            </span>
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">{profile.credentials}</p>
        </div>
        <div className="flex items-center gap-2">
          <CShareStatsButton
            profile={profile}
            reviewed={stats?.requirementsReviewed ?? 0}
            helpful={stats?.helpfulTotal ?? 0}
            rank={rank ? { place: rank.rank, total: leaderboard?.total ?? 0 } : undefined}
          />
        </div>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <CStatTile
          index={0}
          label={t.statReviewed}
          value={<CountUp value={stats?.requirementsReviewed ?? 0} />}
          tone="primary"
        />
        <CStatTile
          index={1}
          label={t.statPublished}
          value={<CountUp value={stats?.reviewsPublished ?? 0} />}
        />
        <CStatTile
          index={2}
          label={t.statHelpful}
          value={<CountUp value={stats?.helpfulTotal ?? 0} />}
          tone="positive"
          hint={t.statHelpfulHint(stats?.notHelpfulTotal ?? 0)}
        />
        <CStatTile
          index={3}
          label={t.statRank}
          value={rank ? t.rankOf(rank.rank, leaderboard?.total ?? 0) : t.noRankYet}
          tone={rank ? 'primary' : 'default'}
          hint={rank ? undefined : t.noRankHint}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <CMyReviewsCard />
        <CLeaderboardCard />
      </div>
    </div>
  )
}

export function CLawyerReviewsPage() {
  return (
    <CLawyerGuard>
      <CLawyerReviewsContent />
    </CLawyerGuard>
  )
}
