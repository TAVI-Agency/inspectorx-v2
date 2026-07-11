import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { FadeIn } from '@/components/FadeIn'
import { useSubscriptionRequest } from '@/data/hooks'
import { useAuth } from '@/app/auth'
import { PRICE } from '@/config'
import { ru } from '@/i18n/ru'

export function PricingPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
      <div className="mx-auto grid max-w-4xl gap-10 lg:grid-cols-[1.2fr_1fr]">
        <FadeIn>
          <TariffCard />
        </FadeIn>
        <FadeIn delayMs={90}>
          <RequestForm />
        </FadeIn>
      </div>
    </div>
  )
}

function TariffCard() {
  return (
    <div>
      <p className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
        Тариф
      </p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">
        {ru.pricing.title}
      </h1>
      <p className="mt-3 max-w-md text-muted-foreground">{ru.pricing.subtitle}</p>

      <p className="mt-6 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <span className="text-4xl font-semibold tracking-tight whitespace-nowrap">
          {PRICE.formatted}
        </span>
        <span className="text-sm text-muted-foreground">{ru.pricing.per}</span>
      </p>

      <ul className="mt-8 space-y-3">
        {ru.pricing.benefits.map((benefit) => (
          <li key={benefit} className="flex items-start gap-2.5 text-sm leading-relaxed">
            <Check className="mt-0.5 size-4 shrink-0 text-positive" />
            {benefit}
          </li>
        ))}
      </ul>
    </div>
  )
}

function RequestForm() {
  const { session, profile } = useAuth()
  const request = useSubscriptionRequest()
  const [name, setName] = useState(profile?.fullName ?? '')
  const [contact, setContact] = useState('')
  const [company, setCompany] = useState(profile?.company ?? '')
  const [touched, setTouched] = useState(false)

  const nameError = touched && !name.trim() ? ru.pricing.validation.nameRequired : null
  const contactError =
    touched && !contact.trim() ? ru.pricing.validation.contactRequired : null

  if (request.isSuccess) {
    return (
      <div className="flex flex-col justify-center rounded-lg border bg-paper p-6 text-center">
        <p className="stamp mx-auto text-positive">заявка принята</p>
        <h2 className="mt-4 text-xl font-semibold tracking-tight">
          {ru.pricing.thanksTitle}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {ru.pricing.thanksText}
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mx-auto mt-5"
          nativeButton={false}
          render={<Link to="/" />}
        >
          {ru.pricing.thanksCta}
        </Button>
      </div>
    )
  }

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (!name.trim() || !contact.trim()) return
    request.mutate({
      fullName: name.trim(),
      contact: contact.trim(),
      company: company.trim() || undefined,
    })
  }

  return (
    <form onSubmit={submit} className="rounded-lg border bg-paper p-6" noValidate>
      <h2 className="text-lg font-semibold tracking-tight">{ru.pricing.formTitle}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{ru.pricing.formSubtitle}</p>

      <div className="mt-5 space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="req-name">{ru.pricing.nameLabel}</Label>
          <Input
            id="req-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={ru.pricing.namePlaceholder}
            aria-invalid={Boolean(nameError)}
            autoComplete="name"
          />
          {nameError && <p className="text-xs text-destructive">{nameError}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="req-contact">{ru.pricing.contactLabel}</Label>
          <Input
            id="req-contact"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder={ru.pricing.contactPlaceholder}
            aria-invalid={Boolean(contactError)}
            autoComplete="tel"
          />
          {contactError && <p className="text-xs text-destructive">{contactError}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="req-company">{ru.pricing.companyLabel}</Label>
          <Input
            id="req-company"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder={ru.pricing.companyPlaceholder}
            autoComplete="organization"
          />
        </div>
      </div>

      {request.isError && (
        <p className="mt-3 text-sm text-destructive">{ru.common.error}</p>
      )}

      <Button type="submit" className="mt-5 w-full" disabled={request.isPending}>
        {request.isPending ? ru.common.sending : ru.pricing.submit}
      </Button>
      {!session && (
        <p className="mt-3 text-center text-xs text-muted-foreground">
          Вход не нужен — просто оставьте контакт.
        </p>
      )}
    </form>
  )
}
