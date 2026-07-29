/**
 * Прочитанность мок-изменений. Живёт в localStorage,
 * чтобы «отметить прочитанным» переживало перезагрузку.
 */
const KEY = 'ix-read-changes'

function load(): Set<string> {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return new Set()
    const arr = JSON.parse(raw)
    return new Set(Array.isArray(arr) ? arr.filter((x) => typeof x === 'string') : [])
  } catch {
    return new Set()
  }
}

export function isChangeRead(changeId: string): boolean {
  return load().has(changeId)
}

export function markChangeRead(changeId: string): void {
  const set = load()
  set.add(changeId)
  localStorage.setItem(KEY, JSON.stringify([...set]))
}

export function readChangeIds(): Set<string> {
  return load()
}

// ── Голоса за демо-заключения юристов (мок) ────────────────────────
// Реальные голоса живут в review_votes; для витринных фикстур
// (молоко/парацетамол) держим голос локально, чтобы демо было живым.

const MOCK_VOTES_KEY = 'ix-mock-review-votes'

export function loadMockReviewVotes(): Record<string, 1 | -1> {
  try {
    const raw = localStorage.getItem(MOCK_VOTES_KEY)
    if (!raw) return {}
    const o = JSON.parse(raw)
    const out: Record<string, 1 | -1> = {}
    for (const [k, v] of Object.entries(o)) {
      if (v === 1 || v === -1) out[k] = v
    }
    return out
  } catch {
    return {}
  }
}

export function saveMockReviewVote(reviewId: string, vote: 1 | -1 | null): void {
  const votes = loadMockReviewVotes()
  if (vote === null) delete votes[reviewId]
  else votes[reviewId] = vote
  localStorage.setItem(MOCK_VOTES_KEY, JSON.stringify(votes))
}

// ── Настройки дайджеста (мок) ──────────────────────────────────────

const DIGEST_KEY = 'ix-digest-settings'

export interface DigestSettings {
  email: boolean
  telegram: boolean
}

export function loadDigestSettings(): DigestSettings {
  try {
    const raw = localStorage.getItem(DIGEST_KEY)
    if (!raw) return { email: true, telegram: false }
    const o = JSON.parse(raw)
    return { email: Boolean(o.email), telegram: Boolean(o.telegram) }
  } catch {
    return { email: true, telegram: false }
  }
}

export function saveDigestSettings(s: DigestSettings): void {
  localStorage.setItem(DIGEST_KEY, JSON.stringify(s))
}
