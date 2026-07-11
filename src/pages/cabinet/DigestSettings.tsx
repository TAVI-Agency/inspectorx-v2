import { useEffect, useState } from 'react'
import { Switch } from '@/components/ui/switch'
import {
  loadDigestSettings,
  saveDigestSettings,
  type DigestSettings as Settings,
} from '@/data/mock/read-store'
import { ru } from '@/i18n/ru'

/** Настройка дайджеста (§3a.5). Пока мок: живёт в localStorage. */
export function DigestSettings() {
  const [settings, setSettings] = useState<Settings>(loadDigestSettings)
  const [savedFlash, setSavedFlash] = useState(false)

  useEffect(() => {
    if (!savedFlash) return
    const t = setTimeout(() => setSavedFlash(false), 2000)
    return () => clearTimeout(t)
  }, [savedFlash])

  function update(patch: Partial<Settings>) {
    const next = { ...settings, ...patch }
    setSettings(next)
    saveDigestSettings(next)
    setSavedFlash(true)
  }

  return (
    <section className="rounded-lg border bg-paper p-4">
      <h2 className="text-sm font-semibold">{ru.cabinet.digestTitle}</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">{ru.cabinet.digestText}</p>
      <div className="mt-3 space-y-2.5">
        <label className="flex items-center gap-2.5 text-sm">
          <Switch
            size="sm"
            checked={settings.email}
            onCheckedChange={(v) => update({ email: v })}
          />
          {ru.cabinet.digestEmail}
        </label>
        <label className="flex items-center gap-2.5 text-sm">
          <Switch
            size="sm"
            checked={settings.telegram}
            onCheckedChange={(v) => update({ telegram: v })}
          />
          {ru.cabinet.digestTelegram}
        </label>
      </div>
      <p
        aria-live="polite"
        className={`mt-2 text-xs text-positive transition-opacity duration-300 ${savedFlash ? 'opacity-100' : 'opacity-0'}`}
      >
        {ru.cabinet.digestSaved}
      </p>
    </section>
  )
}
