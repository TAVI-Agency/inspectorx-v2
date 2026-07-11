import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { FadeIn } from '@/components/FadeIn'
import { useSubscriptionRequest } from '@/data/hooks'
import { useAuth } from '@/app/auth'
import { ru } from '@/i18n/ru'

/**
 * Финальный экран лендинга: уверенный заголовок + реассуранс + СВОЯ форма
 * заявки (пишет в subscription_requests) + прямой контакт. Паттерн — секция
 * контактов radicalloop, но в тёплом «досье»-языке InspectorX.
 */
export function ContactSection() {
  const m = ru.marketing.cta
  return (
    <section id="early-access" className="border-t border-border/70 bg-secondary/40">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-20 sm:px-6 sm:py-28 lg:grid-cols-[1.05fr_1fr] lg:gap-16">
        <FadeIn>
          <p className="stamp text-primary">{m.eyebrow}</p>
          <h2 className="mt-5 max-w-md font-serif text-4xl leading-[1.05] font-medium tracking-tight text-balance sm:text-5xl">
            {m.title}
          </h2>
          <p className="mt-5 max-w-md text-lg text-muted-foreground">{m.lead}</p>

          <div className="mt-8">
            <p className="font-mono text-[11px] tracking-[0.12em] text-muted-foreground uppercase">
              {m.altLabel}
            </p>
            <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm">
              <a href="mailto:hello@inspectorx.uz" className="hover:text-primary hover:underline">
                {ru.footer.email}
              </a>
              <a
                href="https://t.me/inspectorx_uz"
                target="_blank"
                rel="noreferrer"
                className="hover:text-primary hover:underline"
              >
                {ru.footer.telegram}
              </a>
            </div>
          </div>
        </FadeIn>

        <FadeIn delayMs={90}>
          <RequestForm />
        </FadeIn>
      </div>
    </section>
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
      <div className="flex h-full flex-col justify-center rounded-xl border bg-paper p-8 text-center shadow-sm">
        <p className="stamp mx-auto text-positive">заявка принята</p>
        <h3 className="mt-4 font-serif text-2xl font-medium tracking-tight">
          {ru.pricing.thanksTitle}
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {ru.pricing.thanksText}
        </p>
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
    <form
      onSubmit={submit}
      className="rounded-xl border bg-paper p-6 shadow-[0_20px_50px_-30px_rgba(28,27,25,0.35)] sm:p-7"
      noValidate
    >
      <h3 className="font-serif text-xl font-medium tracking-tight">{ru.pricing.formTitle}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{ru.pricing.formSubtitle}</p>

      <div className="mt-6 space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="cta-name">{ru.pricing.nameLabel}</Label>
          <Input
            id="cta-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={ru.pricing.namePlaceholder}
            aria-invalid={Boolean(nameError)}
            autoComplete="name"
          />
          {nameError && <p className="text-xs text-destructive">{nameError}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cta-contact">{ru.pricing.contactLabel}</Label>
          <Input
            id="cta-contact"
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder={ru.pricing.contactPlaceholder}
            aria-invalid={Boolean(contactError)}
            autoComplete="tel"
          />
          {contactError && <p className="text-xs text-destructive">{contactError}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cta-company">{ru.pricing.companyLabel}</Label>
          <Input
            id="cta-company"
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

      <Button type="submit" className="mt-6 h-12 w-full text-[15px]" disabled={request.isPending}>
        {request.isPending ? ru.common.sending : ru.pricing.submit}
      </Button>
      {!session && (
        <p className="mt-3 text-center text-xs text-muted-foreground">
          {ru.marketing.cta.reassurance}
        </p>
      )}
    </form>
  )
}
