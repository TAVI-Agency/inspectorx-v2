import { useState, type ReactElement, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  BadgeCheck,
  Camera,
  FileCheck,
  FileText,
  HelpCircle,
  Languages,
  LogIn,
  LogOut,
  Megaphone,
  MessageSquareText,
  Scale,
  Settings,
  ShieldCheck,
  Wrench,
} from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Switch } from '@/components/ui/switch'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { useTheme, type ThemeSetting } from '@/app/theme'
import { useIsModerator, useMyLawyerProfile } from '@/data/hooks'
import { FeedbackDialog } from '@/components/FeedbackDialog'
import { WhatsNewDialog } from '@/components/WhatsNewDialog'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'

const t = ru.profileMenu

/** Инициалы для аватарки: «Абдурахмон Турдиев» → «АТ» */
export function initialsOf(name?: string): string {
  if (!name?.trim()) return '·'
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join('')
}

/**
 * Компактное меню профиля (вверх): всё редкое живёт только здесь —
 * план, настройки, помощь, фидбэк, язык, тема, «что нового», демо-режим, выход.
 */
export function CProfileMenu({
  trigger,
  side = 'top',
  align = 'start',
  includeNavSections = false,
}: {
  trigger: ReactElement<Record<string, unknown>>
  side?: 'top' | 'bottom'
  align?: 'start' | 'center' | 'end'
  /** мобайл: секции «Проверки» и «Кабинет юриста» тоже живут в этом меню */
  includeNavSections?: boolean
}) {
  const { session, realSubscriber, signOut } = useAuth()
  const { mockSubscriber, setMockSubscriber } = useAppMode()
  const { setting, setSetting } = useTheme()
  const { data: lawyerProfile } = useMyLawyerProfile()
  const verified = lawyerProfile?.status === 'verified'
  const { data: moderator } = useIsModerator()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [whatsNewOpen, setWhatsNewOpen] = useState(false)

  const itemClass =
    'flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] text-left transition-colors hover:bg-secondary/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none'

  function close() {
    setOpen(false)
  }

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger render={trigger} />
        <PopoverContent side={side} align={align} sideOffset={8} className="w-[264px] gap-0 p-0">
          {/* Шапка: кто вы */}
          <p className="border-b border-border px-3.5 py-2.5 text-xs text-muted-foreground">
            {session
              ? `${session.user.email} · ${verified ? t.roleLawyer : t.roleClient}`
              : `${t.guestName} · ${t.guestHint}`}
          </p>

          {includeNavSections && (
            <div className="border-b border-border p-1.5">
              <MenuNavLink to="/checks/packaging" icon={Camera} onGo={close}>
                {ru.nav.packaging}
              </MenuNavLink>
              <MenuNavLink to="/checks/documents" icon={FileCheck} onGo={close} soon>
                {ru.nav.documents}
              </MenuNavLink>
              {verified && (
                <>
                  <MenuNavLink to="/lawyer/queue" icon={Scale} onGo={close}>
                    {ru.nav.lawyerQueue}
                  </MenuNavLink>
                  <MenuNavLink to="/lawyer/reviews" icon={FileText} onGo={close}>
                    {ru.nav.lawyerReviews}
                  </MenuNavLink>
                </>
              )}
              {moderator && (
                <MenuNavLink to="/moderation" icon={ShieldCheck} onGo={close}>
                  {ru.nav.moderation}
                </MenuNavLink>
              )}
            </div>
          )}

          {/* План — с переходом на тариф */}
          <Link
            to="/pricing"
            onClick={close}
            className="m-1.5 block rounded-lg bg-accent/70 px-3 py-2.5 transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <span className="flex items-center gap-1.5 text-[13px] font-semibold text-accent-foreground">
              {realSubscriber ? <BadgeCheck className="size-3.5" /> : null}
              {realSubscriber ? t.planPaid : t.planFree}
            </span>
            <span className="mt-0.5 block text-xs text-muted-foreground">
              {realSubscriber ? t.planPaidCta : mockSubscriber ? t.planDemo : t.planFreeCta}
            </span>
          </Link>

          <div className="p-1.5">
            <button
              type="button"
              className={itemClass}
              onClick={() => {
                close()
                navigate('/settings')
              }}
            >
              <Settings className="size-4 text-muted-foreground" />
              {t.settings}
            </button>
            <button
              type="button"
              className={itemClass}
              onClick={() => {
                close()
                navigate('/help')
              }}
            >
              <HelpCircle className="size-4 text-muted-foreground" />
              {t.help}
            </button>
            <button
              type="button"
              className={itemClass}
              onClick={() => {
                close()
                setFeedbackOpen(true)
              }}
            >
              <MessageSquareText className="size-4 text-muted-foreground" />
              {t.feedback}
            </button>
            <button
              type="button"
              className={itemClass}
              onClick={() => {
                close()
                setWhatsNewOpen(true)
              }}
            >
              <Megaphone className="size-4 text-muted-foreground" />
              {t.whatsNew}
            </button>
          </div>

          <div className="border-t border-border p-1.5">
            {/* Язык: русский сейчас, uz/en скоро */}
            <div className="flex items-center gap-2.5 px-2.5 py-2 text-[13px]" title={t.languageSoon}>
              <Languages className="size-4 text-muted-foreground" />
              {t.language}
              <span className="ml-auto text-xs text-muted-foreground">{t.languageValue}</span>
            </div>
            {/* Тема: три положения */}
            <div className="flex items-center gap-2.5 px-2.5 py-1.5 text-[13px]">
              <span className="w-4" />
              {t.theme}
              <span className="ml-auto flex rounded-md border border-border p-0.5">
                {(['light', 'system', 'dark'] as ThemeSetting[]).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setSetting(m)}
                    className={cn(
                      'rounded-[5px] px-1.5 py-0.5 text-[11px] transition-colors',
                      setting === m
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {m === 'light' ? t.themeLight : m === 'dark' ? t.themeDark : t.themeSystem}
                  </button>
                ))}
              </span>
            </div>
            {/* Демо-режим (бывшее dev-меню) */}
            <label
              className="flex cursor-pointer items-center gap-2.5 px-2.5 py-2 text-[13px]"
              title={ru.dev.mockSubscriberHint}
            >
              <Wrench className="size-4 text-muted-foreground" />
              {t.demoMode}
              <span className="ml-auto">
                <Switch size="sm" checked={mockSubscriber} onCheckedChange={setMockSubscriber} />
              </span>
            </label>
          </div>

          <div className="border-t border-border p-1.5">
            {session ? (
              <button
                type="button"
                className={cn(itemClass, 'text-sanction')}
                onClick={() => {
                  close()
                  void signOut()
                }}
              >
                <LogOut className="size-4" />
                {t.signOut}
              </button>
            ) : (
              <button
                type="button"
                className={itemClass}
                onClick={() => {
                  close()
                  navigate('/login')
                }}
              >
                <LogIn className="size-4 text-muted-foreground" />
                {ru.common.signIn}
              </button>
            )}
          </div>
        </PopoverContent>
      </Popover>
      <FeedbackDialog open={feedbackOpen} onOpenChange={setFeedbackOpen} />
      <WhatsNewDialog open={whatsNewOpen} onOpenChange={setWhatsNewOpen} />
    </>
  )
}

function MenuNavLink({
  to,
  icon: Icon,
  children,
  onGo,
  soon,
}: {
  to: string
  icon: typeof Camera
  children: ReactNode
  onGo: () => void
  soon?: boolean
}) {
  return (
    <Link
      to={to}
      onClick={onGo}
      className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] transition-colors hover:bg-secondary/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <Icon className="size-4 text-muted-foreground" />
      {children}
      {soon && (
        <span className="ml-auto font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
          {ru.nav.soon}
        </span>
      )}
    </Link>
  )
}
