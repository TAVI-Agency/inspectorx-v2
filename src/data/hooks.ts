/**
 * React-Query-хуки — единственная дверь компонентов в слой данных.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { supabase } from '@/lib/supabase'
import { ru } from '@/i18n/ru'
import type {
  AppNotification,
  ComparisonMatrix,
  LawyerReview,
  RequirementRow,
  ReviewVerdict,
  SearchKind,
  UserQuestion,
} from './types'
import type { CountryCode } from './countries'
import {
  buildPortfolio,
  createCalendarToken,
  deleteCalendarToken,
  demoPortfolioIds,
  fetchCalendarToken,
  fetchCard,
  fetchChangeFeed,
  fetchComparisonMatrix,
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
  fetchMyQuestionsReal,
  fetchMyReviewsReal,
  fetchReviewQueueReal,
  fetchSubscriptionRequests,
  markLawyerNotificationReadReal,
  removeChosenReal,
  submitContentRequest,
  submitLawyerApplicationReal,
  submitLawyerReviewReal,
  submitSubscriptionRequest,
  updateProfileReal,
} from './real'
import { demoQuestions } from './mock/fixtures'
import {
  markChangeRead,
  markQuestionAnswerRead,
  readQuestionAnswerIds,
} from './mock/read-store'

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

export function useProductBundle(productId: string | undefined, country: CountryCode = 'UZ') {
  const ctx = useDataCtx()
  return useQuery({
    queryKey: [
      'product',
      productId,
      country,
      ctx.realSubscriber,
      ctx.mockSubscriber,
      ctx.verifiedLawyer,
    ],
    queryFn: () => fetchProductBundle(productId!, ctx, country),
    enabled: Boolean(productId),
    staleTime: 60_000,
    // Смена страны (табы, Задача 31) не должна мигать полным скелетоном
    placeholderData: (prev) => prev,
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

/**
 * Матрица сравнения стран (Задача 32) — лениво: смонтирована только пока
 * открыт диалог CCompareMatrixButton, чтобы не грузить её на каждый визит
 * страницы товара.
 */
export function useComparisonMatrix(productId: string): UseQueryResult<ComparisonMatrix> {
  return useQuery({
    queryKey: ['comparison', productId],
    queryFn: () => fetchComparisonMatrix(productId),
    staleTime: 5 * 60_000,
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

// ── Мои вопросы ────────────────────────────────────────────────────

export function useMyQuestions() {
  const { session } = useAuth()
  const { mockSubscriber } = useAppMode()
  return useQuery({
    queryKey: ['my-questions', session?.user.id ?? 'anon', mockSubscriber],
    queryFn: async (): Promise<UserQuestion[]> => {
      if (session) return fetchMyQuestionsReal()
      // Демо-витрина пути эскалации — без сессии в мок-режиме
      return mockSubscriber ? demoQuestions : []
    },
    staleTime: 30_000,
  })
}

export function useUpdateProfile() {
  const { session, refreshProfile } = useAuth()
  return useMutation({
    mutationFn: async (input: { fullName: string; phone?: string; company?: string }) => {
      if (!session) throw new Error('auth-required')
      await updateProfileReal(session.user.id, input)
    },
    onSuccess: () => void refreshProfile(),
  })
}

// ── Календарь дедлайнов (Блок 5, Задача 37) ──────────────────────────
// Ключ несёт id юзера (как useLeaderboard/useMyReviews) — токен персональный
// секрет, чужой строки в кэше после смены аккаунта в той же вкладке
// оставаться не должно.

export function useCalendarToken() {
  const { session, realSubscriber } = useAuth()
  return useQuery({
    queryKey: ['calendar-token', session?.user.id ?? 'anon'],
    queryFn: fetchCalendarToken,
    enabled: Boolean(session) && realSubscriber,
    staleTime: 30_000,
  })
}

export function useConnectCalendar() {
  const { session } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      if (!session) throw new Error('auth-required')
      return createCalendarToken(session.user.id)
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['calendar-token'] }),
  })
}

export function useDisconnectCalendar() {
  const { session } = useAuth()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      if (!session) throw new Error('auth-required')
      await deleteCalendarToken(session.user.id)
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['calendar-token'] }),
  })
}

// ── Центр уведомлений (колокольчик) ────────────────────────────────

/**
 * Сводит три источника в одну ленту: мок-изменения портфеля,
 * ответы на вопросы пользователя, реальные уведомления юриста.
 */
export function useNotificationCenter() {
  const qc = useQueryClient()
  const { data: portfolio } = usePortfolioIds()
  const ids = portfolio?.ids ?? []
  const { data: feed } = useChangeFeed(ids.length > 0 ? ids : undefined)
  const { data: questions } = useMyQuestions()
  const { data: lawyerProfile } = useMyLawyerProfile()
  const verified = lawyerProfile?.status === 'verified'
  const { data: lawyerNotifs } = useLawyerNotifications(verified)
  const markChange = useMarkChangeRead()
  const markLawyer = useMarkNotificationRead()

  const items: AppNotification[] = []

  for (const c of feed?.items ?? []) {
    if (c.isDraftNpa) continue
    items.push({
      id: `change-${c.id}`,
      kind: 'change',
      sourceId: c.id,
      title: c.title,
      subtitle: c.productName,
      inFavor: c.inFavor,
      link: c.requirementId
        ? `/product/${c.productId}?req=${c.requirementId}`
        : '/changes',
      isRead: !c.unread,
      createdAt: c.date,
    })
  }

  const readAnswers = readQuestionAnswerIds()
  for (const q of questions ?? []) {
    if (!q.answeredAt) continue
    items.push({
      id: `question-${q.id}`,
      kind: 'question',
      sourceId: q.id,
      title: ru.notifications.questionAnswered,
      subtitle: q.questionText,
      link: '/questions',
      isRead: readAnswers.has(q.id),
      createdAt: q.answeredAt,
    })
  }

  for (const n of lawyerNotifs ?? []) {
    items.push({
      id: `lawyer-${n.id}`,
      kind: 'lawyer',
      sourceId: n.id,
      title: ru.cabinet.lawyer.notifications[n.kind],
      subtitle: n.requirementTitle,
      link: n.link,
      isRead: n.isRead,
      createdAt: n.createdAt,
    })
  }

  items.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())

  const markRead = (n: AppNotification) => {
    if (n.isRead) return
    if (n.kind === 'change') markChange.mutate(n.sourceId)
    else if (n.kind === 'lawyer') markLawyer.mutate(n.sourceId)
    else {
      markQuestionAnswerRead(n.sourceId)
      void qc.invalidateQueries({ queryKey: ['my-questions'] })
    }
  }

  return {
    items,
    unreadCount: items.filter((n) => !n.isRead).length,
    changesUnread: items.filter((n) => n.kind === 'change' && !n.isRead).length,
    markRead,
    markAllRead: () => items.filter((n) => !n.isRead).forEach(markRead),
  }
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
  const qc = useQueryClient()
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
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['my-questions'] }),
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
