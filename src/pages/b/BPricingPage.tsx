import { useState } from 'react'
import { Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useSubscriptionRequest } from '@/data/hooks'
import { useAuth } from '@/app/auth'
import { PRICE } from '@/config'
import { ru } from '@/i18n/ru'
import { BCard } from './ui'

export function BPricingPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-14 sm:px-6 sm:py-20">
      <div className="mx-auto max-w-2xl text-center">
        <span className="inline-flex items-center rounded-full bg-accent px-3 py-1 text-xs font-semibold tracking-wide text-accent-foreground uppercase">
          {ru.pricing.title}
        </span>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">
          {ru.pricing.subtitle}
        </h1>
      </div>

      <div className="mt-10 grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <BCard className="overflow-hidden">
          <div className="bg-primary p-6 text-primary-foreground">
            <p className="text-sm/relaxed opacity-90">Полный доступ · за компанию</p>
            <p className="mt-2 flex items-baseline gap-2">
              <span className="text-4xl font-bold tracking-tight">{PRICE.formatted}</span>
              <span className="text-sm opacity-80">{ru.pricing.per}</span>
            </p>
          </div>
          <ul className="space-y-3 p-6">
            {ru.pricing.benefits.map((b) => (
              <li key={b} className="flex items-start gap-3 text-sm leading-relaxed">
                <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-positive/15 text-positive">
                  <Check className="size-3" />
                </span>
                {b}
              </li>
            ))}
          </ul>
        </BCard>

        <BCard className="p-6 sm:p-7">
          <RequestForm />
        </BCard>
      </div>
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
  const contactError = touched && !contact.trim() ? ru.pricing.validation.contactRequired : null

  if (request.isSuccess) {
    return (
      <div className="flex h-full flex-col justify-center py-6 text-center">
        <span className="mx-auto grid size-12 place-items-center rounded-full bg-positive/15 text-positive">
          <Check className="size-6" />
        </span>
        <h2 className="mt-4 text-xl font-semibold tracking-tight">{ru.pricing.thanksTitle}</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{ru.pricing.thanksText}</p>
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
    <form onSubmit={submit} noValidate>
      <h2 className="text-lg font-semibold tracking-tight">{ru.pricing.formTitle}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{ru.pricing.formSubtitle}</p>
      <div className="mt-5 space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="bp-name">{ru.pricing.nameLabel}</Label>
          <Input
            id="bp-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={ru.pricing.namePlaceholder}
            aria-invalid={Boolean(nameError)}
            autoComplete="name"
          />
          {nameError && <p className="text-xs text-destructive">{nameError}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="bp-contact">{ru.pricing.contactLabel}</Label>
          <Input
            id="bp-contact"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder={ru.pricing.contactPlaceholder}
            aria-invalid={Boolean(contactError)}
            autoComplete="tel"
          />
          {contactError && <p className="text-xs text-destructive">{contactError}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="bp-company">{ru.pricing.companyLabel}</Label>
          <Input
            id="bp-company"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder={ru.pricing.companyPlaceholder}
            autoComplete="organization"
          />
        </div>
      </div>
      {request.isError && <p className="mt-3 text-sm text-destructive">{ru.common.error}</p>}
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
