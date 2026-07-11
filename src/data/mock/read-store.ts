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
