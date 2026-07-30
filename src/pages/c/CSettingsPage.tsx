import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Settings } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { useUpdateProfile } from '@/data/hooks'
import {
  loadDigestSettings,
  saveDigestSettings,
  type DigestSettings as Digest,
} from '@/data/mock/read-store'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CCard, CEyebrow } from './ui'
import { CLawyerApplicationCard } from './CLawyerCabinet'

type Tab = 'profile' | 'notifications' | 'subscription'

/** Настройки: вкладки профиль / уведомления / подписка, локальный state таба */
export function CSettingsPage() {
  const { session } = useAuth()
  const { mockSubscriber } = useAppMode()
  const [tab, setTab] = useState<Tab>('profile')

  if (!session && !mockSubscriber) return <CLoginCard />

  return (
    <div className="mx-auto max-w-3xl px-4 py-7 sm:px-8">
      <CEyebrow>Аккаунт</CEyebrow>
      <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight sm:text-[30px]">
        {ru.settings.title}
      </h1>
      <div className="mt-5 flex gap-1 border-b border-border">
        {(['profile', 'notifications', 'subscription'] as const).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setTab(k)}
            className={cn(
              'border-b-2 px-3.5 py-2 text-sm transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
              tab === k
                ? 'border-primary font-semibold text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {ru.settings.tabs[k]}
          </button>
        ))}
      </div>
      <div className="mt-6 max-w-xl space-y-5">
        {tab === 'profile' && <CProfileTab />}
        {tab === 'notifications' && <CNotifsTab />}
        {tab === 'subscription' && <CSubscriptionTab />}
      </div>
    </div>
  )
}

/** Полностраничная карточка входа — анон без мок-режима */
function CLoginCard() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-24 sm:px-8">
      <CCard className="mx-auto max-w-md p-8 text-center">
        <span className="mx-auto grid size-12 place-items-center rounded-full border border-primary/40 bg-accent text-accent-foreground">
          <Settings className="size-5" />
        </span>
        <h1 className="mt-4 text-xl font-semibold tracking-tight">{ru.settings.loginTitle}</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {ru.settings.loginText}
        </p>
        <Button className="mt-5" nativeButton={false} render={<Link to="/login" />}>
          {ru.common.signIn}
        </Button>
      </CCard>
    </div>
  )
}

/** Профиль: форма имя/телефон/компания + email read-only, ниже — заявка юриста */
function CProfileTab() {
  const { session, profile } = useAuth()
  const updateProfile = useUpdateProfile()
  const [name, setName] = useState(profile?.fullName ?? '')
  const [phone, setPhone] = useState(profile?.phone ?? '')
  const [company, setCompany] = useState(profile?.company ?? '')
  const [touched, setTouched] = useState(false)
  const [savedFlash, setSavedFlash] = useState(false)

  // Профиль догружается асинхронно после session — наполняем поля, когда придёт
  useEffect(() => {
    setName(profile?.fullName ?? '')
    setPhone(profile?.phone ?? '')
    setCompany(profile?.company ?? '')
  }, [profile])

  useEffect(() => {
    if (!savedFlash) return
    const t = setTimeout(() => setSavedFlash(false), 2000)
    return () => clearTimeout(t)
  }, [savedFlash])

  if (!session) {
    return (
      <CCard className="p-5 text-center">
        <h2 className="text-[15px] font-semibold tracking-tight">{ru.settings.loginTitle}</h2>
        <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
          {ru.settings.loginText}
        </p>
        <Button className="mt-4" nativeButton={false} render={<Link to="/login" />}>
          {ru.common.signIn}
        </Button>
      </CCard>
    )
  }

  const nameError = touched && !name.trim() ? ru.settings.profile.nameRequired : null
  const inputClass =
    'mt-1 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50'

  function submit() {
    setTouched(true)
    if (!name.trim()) return
    updateProfile.mutate(
      {
        fullName: name.trim(),
        phone: phone.trim() || undefined,
        company: company.trim() || undefined,
      },
      { onSuccess: () => setSavedFlash(true) },
    )
  }

  return (
    <>
      <CCard className="p-4 sm:p-5">
        <div className="space-y-3">
          <label className="block text-xs font-medium">
            {ru.settings.profile.nameLabel}
            <input value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
            {nameError && <span className="mt-1 block font-normal text-destructive">{nameError}</span>}
          </label>
          <label className="block text-xs font-medium">
            {ru.settings.profile.phoneLabel}
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder={ru.settings.profile.phonePlaceholder}
              className={inputClass}
            />
          </label>
          <label className="block text-xs font-medium">
            {ru.settings.profile.companyLabel}
            <input
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder={ru.settings.profile.companyPlaceholder}
              className={inputClass}
            />
          </label>
          <label className="block text-xs font-medium">
            {ru.settings.profile.emailLabel}
            <input
              value={session.user.email ?? ''}
              disabled
              className={cn(inputClass, 'opacity-60')}
            />
          </label>
        </div>
        {updateProfile.isError && (
          <p className="mt-2.5 text-xs text-destructive">{ru.settings.profile.error}</p>
        )}
        <div className="mt-3.5 flex items-center gap-3">
          <Button size="sm" disabled={updateProfile.isPending} onClick={submit}>
            {updateProfile.isPending ? ru.common.sending : ru.settings.profile.save}
          </Button>
          <p
            aria-live="polite"
            className={cn(
              'text-xs text-positive transition-opacity duration-300',
              savedFlash ? 'opacity-100' : 'opacity-0',
            )}
          >
            {ru.settings.profile.saved}
          </p>
        </div>
      </CCard>
      <CLawyerApplicationCard />
    </>
  )
}

/** Уведомления: перенос CDigestSettings — тумблеры email/Telegram, localStorage */
function CNotifsTab() {
  const [settings, setSettings] = useState<Digest>(loadDigestSettings)
  const [savedFlash, setSavedFlash] = useState(false)

  useEffect(() => {
    if (!savedFlash) return
    const t = setTimeout(() => setSavedFlash(false), 2000)
    return () => clearTimeout(t)
  }, [savedFlash])

  function update(patch: Partial<Digest>) {
    const next = { ...settings, ...patch }
    setSettings(next)
    saveDigestSettings(next)
    setSavedFlash(true)
  }

  return (
    <CCard className="p-4 sm:p-5">
      <div className="space-y-4">
        <label className="flex items-center justify-between gap-3 text-sm">
          <span>
            <span className="block font-medium">{ru.settings.notifs.emailTitle}</span>
            <span className="mt-0.5 block text-xs text-muted-foreground">
              {ru.settings.notifs.emailHint}
            </span>
          </span>
          <Switch size="sm" checked={settings.email} onCheckedChange={(v) => update({ email: v })} />
        </label>
        <label className="flex items-center justify-between gap-3 text-sm">
          <span>
            <span className="block font-medium">{ru.settings.notifs.telegramTitle}</span>
            <span className="mt-0.5 block text-xs text-muted-foreground">
              {ru.settings.notifs.telegramHint}
            </span>
          </span>
          <Switch
            size="sm"
            checked={settings.telegram}
            onCheckedChange={(v) => update({ telegram: v })}
          />
        </label>
      </div>
      <p
        aria-live="polite"
        className={cn(
          'mt-3.5 text-xs text-positive transition-opacity duration-300',
          savedFlash ? 'opacity-100' : 'opacity-0',
        )}
      >
        {ru.cabinet.digestSaved}
      </p>
    </CCard>
  )
}

/** Подписка: текущий план, апгрейд-CTA на /pricing, примечание демо-режима */
function CSubscriptionTab() {
  const { realSubscriber } = useAuth()
  const { mockSubscriber } = useAppMode()
  const paid = realSubscriber
  const t = ru.settings.subscription
  return (
    <CCard className="p-5">
      <CEyebrow>{ru.settings.tabs.subscription}</CEyebrow>
      <p className="mt-2 text-[17px] font-semibold tracking-tight">
        {paid ? t.paidTitle : t.freeTitle}
      </p>
      <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
        {paid ? t.paidText : t.freeText}
      </p>
      {!paid && mockSubscriber && (
        <p className="mt-2 text-xs text-brass">{t.demoNote}</p>
      )}
      {!paid && (
        <Button className="mt-4" nativeButton={false} render={<Link to="/pricing" />}>
          {t.upgradeCta}
        </Button>
      )}
      <p className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">{t.contactHint}</p>
    </CCard>
  )
}
