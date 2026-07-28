/**
 * React-Query-хуки — единственная дверь компонентов в слой данных.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { supabase } from '@/lib/supabase'
import type { LawyerReview, RequirementRow, ReviewVerdict, SearchKind } from './types'
import {
  buildPortfolio,
  demoPortfolioIds,
  fetchCard,
  fetchChangeFeed,
  fetchLawyerReviews,
  fetchProductBundle,
  fetchReviewStats,
  fetchServiceBundle,
  fetchTelemetry,
  search,
  setReviewVote,
  type DataCtx,
} from './index'
import {
  addChosenReal,
  fetchChosenReal,
  fetchContentRequests,
  fetchLawyerNotificationsReal,
  fetchLawyerStatsReal,
  fetchLeaderboardReal,
  fetchMyLawyerProfileReal,
  fetchMyReviewsReal,
  fetchReviewQueueReal,
  fetchSubscriptionRequests,
  markLawyerNotificationReadReal,
  removeChosenReal,
  submitContentRequest,
  submitLawyerApplicationReal,
  submitLawyerReviewReal,
  submitSubscriptionRequest,
} from './real'
import { markChangeRead } from './mock/read-store'

export function useDataCtx(): DataCtx {
  const { realSubscriber } = useAuth()
  const { mockSubscriber } = useAppMode()
  const { data: lawyerProfile } = useMyLawyerProfile()
  return {
    realSubscriber,
    mockSubscriber,
    verifiedLawyer: lawyerProfile?.status === 'verified',
  }
}

export function useTelemetry() {
  return useQuery({
    queryKey: ['telemetry'],
    queryFn: fetchTelemetry,
    staleTime: 5 * 60_000,
  })
}

export function useSearchQuery(query: string, kind: SearchKind) {
  return useQuery({
    queryKey: ['search', kind, query],
    queryFn: () => search(query, kind),
    enabled: query.trim().length >= 2,
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  })
}

export function useProductBundle(productId: string | undefined) {
  const ctx = useDataCtx()
  return useQuery({
    queryKey: ['product', productId, ctx.realSubscriber, ctx.mockSubscriber, ctx.verifiedLawyer],
    queryFn: () => fetchProductBundle(productId!, ctx),
    enabled: Boolean(productId),
    staleTime: 60_000,
  })
}

export function useServiceBundle(serviceId: string | undefined) {
  // Флаги доступа в ключе: метрика документов приходит из закрытых RLS-ом details
  const ctx = useDataCtx()
  return useQuery({
    queryKey: ['service', serviceId, ctx.realSubscriber, ctx.verifiedLawyer],
    queryFn: () => fetchServiceBundle(serviceId!),
    enabled: Boolean(serviceId),
    staleTime: 60_000,
  })
}

export function useRequirementCard(row: RequirementRow | null) {
  const ctx = useDataCtx()
  return useQuery({
    queryKey: ['card', row?.id, ctx.realSubscriber, ctx.mockSubscriber, ctx.verifiedLawyer],
    queryFn: () => fetchCard(row!.id, ctx, row!),
    enabled: Boolean(row),
    staleTime: 60_000,
  })
}

// ── Кабинет ────────────────────────────────────────────────────────

export function usePortfolioIds() {
  const { session } = useAuth()
  const { mockSubscriber } = useAppMode()
  return useQuery({
    queryKey: ['portfolio-ids', session?.user.id ?? 'anon', mockSubscriber],
    queryFn: async () => {
      if (session) {
        const chosen = await fetchChosenReal()
        return {
          chosen,
          ids: chosen.map((c) => c.productId),
        }
      }
      // Демо-портфель: кабинет показываем и без входа в мок-режиме
      return {
        chosen: [] as { id: string; productId: string }[],
        ids: mockSubscriber ? demoPortfolioIds : [],
      }
    },
  })
}

export function useChangeFeed(productIds: string[] | undefined) {
  return useQuery({
    queryKey: ['feed', productIds],
    queryFn: async () => {
      const feed = await fetchChangeFeed(productIds!)
      return { ...feed, portfolio: buildPortfolio(productIds!, feed.items) }
    },
    enabled: Boolean(productIds),
  })
}

export function useMarkChangeRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (changeId: string) => {
      markChangeRead(changeId)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['feed'] })
      void qc.invalidateQueries({ queryKey: ['product'] })
    },
  })
}

export function useFollowProduct() {
  const qc = useQueryClient()
  const { session } = useAuth()
  return useMutation({
    mutationFn: async (productId: string) => {
      if (!session) throw new Error('auth-required')
      await addChosenReal(session.user.id, productId)
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['portfolio-ids'] }),
  })
}

export function useUnfollowProduct() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (chosenId: string) => removeChosenReal(chosenId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['portfolio-ids'] }),
  })
}

// ── Формы ──────────────────────────────────────────────────────────

export function useSubscriptionRequest() {
  const { session } = useAuth()
  return useMutation({
    mutationFn: (input: { fullName: string; contact: string; company?: string }) =>
      submitSubscriptionRequest({ ...input, userId: session?.user.id }),
  })
}

export function useAskQuestion() {
  const { session } = useAuth()
  return useMutation({
    mutationFn: async (input: {
      questionText: string
      requirementId?: string
      productId?: string
      legalReviewOnly: boolean
      allowOfficialRequest: boolean
      isUrgent: boolean
    }) => {
      if (!session) throw new Error('auth-required')
      const { error } = await supabase.from('user_questions').insert({
        user_id: session.user.id,
        question_text: input.questionText,
        requirement_id:
          input.requirementId && !input.requirementId.startsWith('mock-')
            ? input.requirementId
            : null,
        product_id:
          input.productId && !input.productId.startsWith('mock-')
            ? input.productId
            : null,
        legal_review_only: input.legalReviewOnly,
        allow_official_request: input.allowOfficialRequest,
        is_urgent: input.isUrgent,
      })
      if (error) throw error
    },
  })
}

// ── Проверка юристом ───────────────────────────────────────────────

export function useMyLawyerProfile() {
  const { session } = useAuth()
  return useQuery({
    queryKey: ['lawyer-profile', session?.user.id ?? 'anon'],
    queryFn: () => fetchMyLawyerProfileReal(session!.user.id),
    enabled: Boolean(session),
    staleTime: 60_000,
  })
}

export function useLawyerApplication() {
  const qc = useQueryClient()
  const { session } = useAuth()
  const { data: profile } = useMyLawyerProfile()
  return useMutation({
    mutationFn: (input: {
      displayName: string
      credentials: string
      licenseNo?: string
      specializations?: string
    }) => {
      if (!session) throw new Error('auth-required')
      return submitLawyerApplicationReal({
        ...input,
        userId: session.user.id,
        hasProfile: Boolean(profile),
      })
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['lawyer-profile'] }),
  })
}

export function useLawyerReviews(requirementId: string | undefined) {
  const { session } = useAuth()
  return useQuery({
    queryKey: ['lawyer-reviews', requirementId, session?.user.id ?? 'anon'],
    queryFn: () => fetchLawyerReviews(requirementId!, session?.user.id),
    enabled: Boolean(requirementId),
    staleTime: 30_000,
  })
}

export function useSubmitLawyerReview() {
  const qc = useQueryClient()
  const { session } = useAuth()
  return useMutation({
    mutationFn: (input: {
      requirementId: string
      verdict: ReviewVerdict
      commentText: string
    }) => {
      if (!session) throw new Error('auth-required')
      return submitLawyerReviewReal({ ...input, userId: session.user.id })
    },
    onSuccess: (_data, input) => {
      void qc.invalidateQueries({ queryKey: ['lawyer-reviews', input.requirementId] })
      void qc.invalidateQueries({ queryKey: ['review-queue'] })
      void qc.invalidateQueries({ queryKey: ['my-reviews'] })
    },
  })
}

/** Голос с оптимистичным обновлением: клик не ждёт сервер */
export function useSetReviewVote(requirementId: string) {
  const qc = useQueryClient()
  const { session } = useAuth()
  const key = ['lawyer-reviews', requirementId, session?.user.id ?? 'anon']
  return useMutation({
    // hadVote приходит из компонента: onMutate уже перепишет кеш оптимистично,
    // читать «прежний голос» из него внутри mutationFn поздно
    mutationFn: (input: { reviewId: string; vote: 1 | -1 | null; hadVote: boolean }) => {
      if (!session) throw new Error('auth-required')
      return setReviewVote(input.reviewId, input.vote, session.user.id, input.hadVote)
    },
    onMutate: async (input) => {
      await qc.cancelQueries({ queryKey: key })
      const prev = qc.getQueryData<LawyerReview[]>(key)
      qc.setQueryData<LawyerReview[]>(key, (list) =>
        (list ?? []).map((r) => {
          if (r.id !== input.reviewId) return r
          let { helpful, notHelpful } = r
          if (r.myVote === 1) helpful -= 1
          if (r.myVote === -1) notHelpful -= 1
          if (input.vote === 1) helpful += 1
          if (input.vote === -1) notHelpful += 1
          return { ...r, myVote: input.vote, helpful, notHelpful }
        }),
      )
      return { prev }
    },
    onError: (_err, _input, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev)
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: key })
      void qc.invalidateQueries({ queryKey: ['lawyer-stats'] })
      void qc.invalidateQueries({ queryKey: ['leaderboard'] })
    },
  })
}

/** Счётчики бейджей: один агрегирующий запрос по строкам страницы */
export function useReviewStats(requirementIds: string[]) {
  const sorted = [...requirementIds].sort()
  return useQuery({
    queryKey: ['review-stats', sorted],
    queryFn: () => fetchReviewStats(sorted),
    enabled: sorted.length > 0,
    staleTime: 60_000,
  })
}

export function useLawyerStats() {
  const { session } = useAuth()
  return useQuery({
    queryKey: ['lawyer-stats', session?.user.id ?? 'anon'],
    queryFn: () => fetchLawyerStatsReal(session!.user.id),
    enabled: Boolean(session),
    staleTime: 30_000,
  })
}

export function useLeaderboard() {
  const { session } = useAuth()
  return useQuery({
    queryKey: ['leaderboard', session?.user.id ?? 'anon'],
    queryFn: () => fetchLeaderboardReal(session?.user.id),
    staleTime: 60_000,
  })
}

export function useReviewQueue(enabled: boolean) {
  return useQuery({
    queryKey: ['review-queue'],
    queryFn: fetchReviewQueueReal,
    enabled,
    staleTime: 60_000,
  })
}

export function useMyReviews(enabled: boolean) {
  const { session } = useAuth()
  return useQuery({
    queryKey: ['my-reviews', session?.user.id ?? 'anon'],
    queryFn: () => fetchMyReviewsReal(session!.user.id),
    enabled: enabled && Boolean(session),
    staleTime: 30_000,
  })
}

export function useLawyerNotifications(enabled: boolean) {
  const { session } = useAuth()
  return useQuery({
    queryKey: ['lawyer-notifications', session?.user.id ?? 'anon'],
    queryFn: fetchLawyerNotificationsReal,
    enabled: enabled && Boolean(session),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useMarkNotificationRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => markLawyerNotificationReadReal(id),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ['lawyer-notifications'] }),
  })
}

// ── Админка ────────────────────────────────────────────────────────

export function useSubscriptionRequests() {
  return useQuery({
    queryKey: ['admin-subscription-requests'],
    queryFn: fetchSubscriptionRequests,
    staleTime: 30_000,
  })
}

export function useContentRequests() {
  return useQuery({
    queryKey: ['admin-content-requests'],
    queryFn: fetchContentRequests,
    staleTime: 30_000,
  })
}

export function useContentRequest() {
  const { session } = useAuth()
  return useMutation({
    mutationFn: (input: {
      kind: 'fill_product' | 'missing_product' | 'missing_section'
      queryText?: string
      productId?: string
      comment?: string
    }) => submitContentRequest({ ...input, userId: session?.user.id }),
  })
}
