import { ru } from '@/i18n/ru'
import { CEyebrow } from './ui'
import { CLawyerGuard } from './CLawyerGuard'
import { CReviewQueueCard } from './CLawyerCabinet'

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
      </div>
    </CLawyerGuard>
  )
}
