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
import type { RequirementRow, SearchKind } from './types'
import {
  buildPortfolio,
  demoPortfolioIds,
  fetchCard,
  fetchChangeFeed,
  fetchProductBundle,
  fetchServiceBundle,
  fetchTelemetry,
  search,
  type DataCtx,
} from './index'
import {
  addChosenReal,
  fetchChosenReal,
  fetchContentRequests,
  fetchSubscriptionRequests,
  removeChosenReal,
  submitContentRequest,
  submitSubscriptionRequest,
} from './real'
import { markChangeRead } from './mock/read-store'

export function useDataCtx(): DataCtx {
  const { realSubscriber } = useAuth()
  const { mockSubscriber } = useAppMode()
  return { realSubscriber, mockSubscriber }
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
    queryKey: ['product', productId, ctx.realSubscriber, ctx.mockSubscriber],
    queryFn: () => fetchProductBundle(productId!, ctx),
    enabled: Boolean(productId),
    staleTime: 60_000,
  })
}

export function useServiceBundle(serviceId: string | undefined) {
  // realSubscriber в ключе: метрика документов приходит из закрытых RLS-ом details
  const { realSubscriber } = useAuth()
  return useQuery({
    queryKey: ['service', serviceId, realSubscriber],
    queryFn: () => fetchServiceBundle(serviceId!),
    enabled: Boolean(serviceId),
    staleTime: 60_000,
  })
}

export function useRequirementCard(row: RequirementRow | null) {
  const ctx = useDataCtx()
  return useQuery({
    queryKey: ['card', row?.id, ctx.realSubscriber, ctx.mockSubscriber],
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
