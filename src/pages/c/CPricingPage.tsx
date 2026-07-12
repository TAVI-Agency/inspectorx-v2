import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Bell,
  Check,
  FileSearch,
  ListChecks,
  MessageCircleQuestion,
  Quote,
  Sparkles,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useSubscriptionRequest } from '@/data/hooks'
import { PRICE } from '@/config'
import { ru } from '@/i18n/ru'
import { CCard, CEyebrow, CSeal } from './ui'

const BENEFIT_ICONS = [ListChecks, Quote, Bell, Sparkles, MessageCircleQuestion, FileSearch]

/**
 * Тариф «Ранний доступ»: латунная гербовая печать — граница премиума,
 * одна цена, заявка вместо самообслуживания (ранний доступ включаем вручную).
 */
export function CPricingPage() {
  return (
    <div className="relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="c-aurora absolute -top-32 left-[12%] h-[22rem] w-[30rem] rounded-full bg-brass/12 blur-3xl" />
        <div className="c-aurora c-aurora-slow absolute -top-20 right-[8%] h-[18rem] w-[24rem] rounded-full bg-primary/10 blur-3xl" />
      </div>

      <div className="relative mx-auto max-w-5xl px-4 py-12 sm:px-8 sm:py-16">
        <div className="mx-auto max-w-2xl text-center">
          <CSeal className="mx-auto" />
          <CEyebrow className="mt-4 text-brass">{ru.pricing.title}</CEyebrow>
          <h1 className="font-display mt-3 text-[24px] leading-[1.25] font-medium tracking-tight text-balance sm:text-[32px]">
            {ru.pricing.subtitle}
          </h1>
          <p className="mt-5">
            <span className="font-display text-[30px] font-medium tracking-tight sm:text-[38px]">
              {PRICE.formatted}
            </span>
            <span className="ml-2 text-sm text-muted-foreground">{ru.pricing.per}</span>
          </p>
        </div>

        <div className="mt-10 grid gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          {/* Что входит */}
          <CCard className="p-6 sm:p-7">
            <CEyebrow>Что входит</CEyebrow>
            <ul className="mt-4 space-y-4">
              {ru.pricing.benefits.map((benefit, i) => {
                const Icon = BENEFIT_ICONS[i % BENEFIT_ICONS.length]
                return (
                  <li
                    key={i}
                    className="c-rise flex items-start gap-3.5"
                    style={{ '--i': i } as React.CSSProperties}
                  >
                    <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
                      <Icon className="size-4" />
                    </span>
                    <p className="text-sm leading-relaxed">{benefit}</p>
                  </li>
                )
              })}
            </ul>
            <p className="mt-6 border-t border-border pt-4 text-xs leading-relaxed text-muted-foreground">
              {ru.paywall.teaserNote}
            </p>
          </CCard>

          <RequestForm />
        </div>
      </div>
    </div>
  )
}

function RequestForm() {
  const request = useSubscriptionRequest()
  const [fullName, setFullName] = useState('')
  const [contact, setContact] = useState('')
  const [company, setCompany] = useState('')
  const [errors, setErrors] = useState<{ name?: string; contact?: string }>({})

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const next: typeof errors = {}
    if (!fullName.trim()) next.name = ru.pricing.validation.nameRequired
    if (!contact.trim()) next.contact = ru.pricing.validation.contactRequired
    setErrors(next)
    if (Object.keys(next).length > 0) return
    request.mutate({
      fullName: fullName.trim(),
      contact: contact.trim(),
      company: company.trim() || undefined,
    })
  }

  if (request.isSuccess) {
    return (
      <CCard className="flex flex-col items-center justify-center p-8 text-center">
        <span className="grid size-12 place-items-center rounded-full border border-positive/40 bg-positive/10 text-positive">
          <Check className="size-6" />
        </span>
        <h2 className="mt-4 text-lg font-semibold tracking-tight">{ru.pricing.thanksTitle}</h2>
        <p className="mt-2 max-w-xs text-sm leading-relaxed text-muted-foreground">
          {ru.pricing.thanksText}
        </p>
        <Button
          variant="outline"
          className="mt-5"
          nativeButton={false}
          render={<Link to="/catalog" />}
        >
          {ru.pricing.thanksCta}
          <ArrowRight />
        </Button>
      </CCard>
    )
  }

  return (
    <CCard className="self-start p-6 sm:p-7">
      <h2 className="text-lg font-semibold tracking-tight">{ru.pricing.formTitle}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{ru.pricing.formSubtitle}</p>
      <form onSubmit={submit} noValidate className="mt-5 space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="cpr-name">{ru.pricing.nameLabel}</Label>
          <Input
            id="cpr-name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder={ru.pricing.namePlaceholder}
            autoComplete="name"
            aria-invalid={Boolean(errors.name)}
          />
          {errors.name && <p className="text-xs text-destructive">{errors.name}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cpr-contact">{ru.pricing.contactLabel}</Label>
          <Input
            id="cpr-contact"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder={ru.pricing.contactPlaceholder}
            autoComplete="tel"
            aria-invalid={Boolean(errors.contact)}
          />
          {errors.contact && <p className="text-xs text-destructive">{errors.contact}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cpr-company">{ru.pricing.companyLabel}</Label>
          <Input
            id="cpr-company"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder={ru.pricing.companyPlaceholder}
            autoComplete="organization"
          />
        </div>
        {request.isError && (
          <p className="text-sm text-destructive">{ru.auth.errors.generic}</p>
        )}
        <Button type="submit" className="w-full" disabled={request.isPending}>
          {request.isPending ? ru.common.sending : ru.pricing.submit}
        </Button>
        <p className="text-center text-xs text-muted-foreground">
          {ru.marketing.cta.reassurance}
        </p>
      </form>
    </CCard>
  )
}
