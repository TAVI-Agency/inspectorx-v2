import { Link } from 'react-router-dom'
import { ArrowRight, ArrowUpRight, Check } from 'lucide-react'
import { FadeIn } from '@/components/FadeIn'
import { TelemetryLine } from '@/app/layout/TelemetryLine'
import { Button } from '@/components/ui/button'
import { exampleHits } from '@/data'
import { ru } from '@/i18n/ru'
import { formatHsCode, pluralize } from '@/lib/format'
import { CIGARETTES_PRODUCT_ID } from '@/data/mock/fixtures'
import { HeroDossier } from './HeroDossier'
import { ContactSection } from './ContactSection'

/** Маркетинговый лендинг — точка входа. Расширяет «досье»-бренд витрины. */
export function LandingPage() {
  return (
    <div className="overflow-x-clip">
      <Hero />
      <StatsStrip />
      <Problem />
      <HowItWorks />
      <Anatomy />
      <Taxonomy />
      <Monitoring />
      <ContactSection />
    </div>
  )
}

// ── Эйбрау секции ────────────────────────────────────────────────────
function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-mono text-[11px] tracking-[0.16em] text-primary uppercase">
      {children}
    </p>
  )
}

// ── Hero ─────────────────────────────────────────────────────────────
function Hero() {
  const m = ru.marketing
  return (
    <section className="relative border-b border-border/70">
      <div className="paper-grain pointer-events-none absolute inset-0" aria-hidden />
      <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 pt-16 pb-20 sm:px-6 sm:pt-24 sm:pb-28 lg:grid-cols-[1.05fr_0.95fr] lg:gap-10">
        <div>
          <FadeIn>
            <p className="font-mono text-[11px] tracking-[0.16em] text-muted-foreground uppercase">
              {m.eyebrow}
            </p>
            <h1 className="mt-5 font-serif text-[2.6rem] leading-[1.02] font-medium tracking-[-0.01em] text-balance sm:text-6xl">
              {m.heroTitle}
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
              {m.heroLead}
            </p>
          </FadeIn>
          <FadeIn delayMs={90}>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button
                className="h-12 gap-2 px-6 text-[15px]"
                nativeButton={false}
                render={<Link to="/catalog" />}
              >
                {m.ctaOpen}
                <ArrowRight className="size-4" />
              </Button>
              <Button
                variant="ghost"
                className="h-12 px-5 text-[15px]"
                nativeButton={false}
                render={<Link to={`/product/${CIGARETTES_PRODUCT_ID}`} />}
              >
                {m.ctaExample}
              </Button>
            </div>
            <TelemetryLine className="mt-6" />
          </FadeIn>
        </div>

        <FadeIn delayMs={140} className="flex justify-center lg:justify-end">
          <HeroDossier />
        </FadeIn>
      </div>
    </section>
  )
}

// ── Честная строка статистики ────────────────────────────────────────
function StatsStrip() {
  const s = ru.marketing.stats
  return (
    <section className="border-b border-border/70">
      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
        <FadeIn>
          <p className="font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
            {s.title}
          </p>
        </FadeIn>
        <div className="mt-5 grid gap-8 sm:grid-cols-3">
          {s.items.map((it, i) => (
            <FadeIn key={it.label} delayMs={i * 70}>
              <div className="flex items-baseline gap-3">
                <span className="font-serif text-4xl font-medium tracking-tight tabular-nums">
                  {it.value}
                </span>
                <span className="text-sm leading-snug text-muted-foreground">
                  {it.label}
                </span>
              </div>
            </FadeIn>
          ))}
        </div>
      </div>
    </section>
  )
}

// ── Проблема ─────────────────────────────────────────────────────────
function Problem() {
  const p = ru.marketing.problem
  return (
    <section className="mx-auto max-w-6xl px-4 py-24 sm:px-6 sm:py-32">
      <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
        <FadeIn>
          <Eyebrow>{p.eyebrow}</Eyebrow>
          <h2 className="mt-5 font-serif text-4xl leading-[1.06] font-medium tracking-tight text-balance sm:text-5xl">
            {p.titleA}
            <br />
            <span className="text-primary">{p.titleB}</span>
          </h2>
        </FadeIn>
        <FadeIn delayMs={90} className="flex items-end">
          <p className="text-lg leading-relaxed text-muted-foreground">{p.body}</p>
        </FadeIn>
      </div>
    </section>
  )
}

// ── Как это работает ─────────────────────────────────────────────────
function HowItWorks() {
  const m = ru.marketing.how
  return (
    <section className="border-y border-border/70 bg-secondary/30">
      <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
        <FadeIn>
          <Eyebrow>{m.eyebrow}</Eyebrow>
          <h2 className="mt-4 font-serif text-3xl font-medium tracking-tight sm:text-4xl">
            {m.title}
          </h2>
        </FadeIn>
        <ol className="mt-14 grid gap-x-8 gap-y-12 sm:grid-cols-3">
          {ru.landing.howSteps.map((step, i) => (
            <FadeIn key={step.title} delayMs={i * 90}>
              <li className="border-t border-foreground/15 pt-5">
                <span className="font-mono text-sm text-primary">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <h3 className="mt-3 text-lg font-medium">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {step.text}
                </p>
              </li>
            </FadeIn>
          ))}
        </ol>
      </div>
    </section>
  )
}

// ── Анатомия требования (0 → 1 → 2) ─────────────────────────────────
function Anatomy() {
  const a = ru.marketing.anatomy
  return (
    <section className="mx-auto max-w-6xl px-4 py-24 sm:px-6 sm:py-32">
      <div className="max-w-2xl">
        <FadeIn>
          <Eyebrow>{a.eyebrow}</Eyebrow>
          <h2 className="mt-4 font-serif text-3xl font-medium tracking-tight text-balance sm:text-4xl">
            {a.title}
          </h2>
          <p className="mt-5 text-lg leading-relaxed text-muted-foreground">{a.lead}</p>
        </FadeIn>
      </div>
      <div className="mt-14 grid gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-3">
        {a.levels.map((lvl, i) => (
          <FadeIn key={lvl.tag} delayMs={i * 90} className="bg-paper">
            <div className="flex h-full flex-col p-6">
              <span className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
                {lvl.tag}
              </span>
              <h3 className="mt-3 text-lg font-medium">{lvl.title}</h3>
              <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
                {lvl.text}
              </p>
              <span
                aria-hidden
                className="mt-4 font-mono text-xs text-primary/70"
              >
                {'0→1→2'.slice(0, i * 2 + 1)}
              </span>
            </div>
          </FadeIn>
        ))}
      </div>
    </section>
  )
}

// ── Таксономия операций (маркетинг блока 2) ─────────────────────────
function Taxonomy() {
  const t = ru.marketing.taxonomy
  return (
    <section className="border-y border-border/70 bg-secondary/30">
      <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6 sm:py-32">
        <div className="max-w-2xl">
          <FadeIn>
            <Eyebrow>{t.eyebrow}</Eyebrow>
            <h2 className="mt-4 font-serif text-3xl font-medium tracking-tight text-balance sm:text-4xl">
              {t.title}
            </h2>
            <p className="mt-5 text-lg leading-relaxed text-muted-foreground">{t.lead}</p>
          </FadeIn>
        </div>

        <FadeIn delayMs={80}>
          <p className="mt-12 font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
            {t.operationsLabel}
          </p>
          <div className="mt-4 flex flex-wrap gap-2.5">
            {t.operations.map((op) => (
              <span
                key={op.key}
                className="inline-flex items-center gap-2 rounded-full border bg-paper py-1.5 pr-3 pl-3.5 text-sm"
              >
                {op.name}
                <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
                  {op.count}
                </span>
              </span>
            ))}
          </div>
        </FadeIn>

        <FadeIn delayMs={140}>
          <p className="mt-10 font-mono text-[11px] tracking-[0.14em] text-muted-foreground uppercase">
            {t.transportLabel}
          </p>
          <div className="mt-4 flex flex-wrap gap-2.5">
            {t.transport.map((tr) => (
              <span
                key={tr}
                className="rounded-full border border-dashed bg-paper px-4 py-1.5 text-sm text-muted-foreground"
              >
                {tr}
              </span>
            ))}
          </div>
        </FadeIn>
      </div>
    </section>
  )
}

// ── Мониторинг изменений ─────────────────────────────────────────────
function Monitoring() {
  const m = ru.marketing.monitoring
  return (
    <section className="mx-auto max-w-6xl px-4 py-24 sm:px-6 sm:py-32">
      <div className="grid items-center gap-12 lg:grid-cols-[1fr_1fr] lg:gap-16">
        <FadeIn>
          <Eyebrow>{m.eyebrow}</Eyebrow>
          <h2 className="mt-4 font-serif text-3xl font-medium tracking-tight text-balance sm:text-4xl">
            {m.title}
          </h2>
          <p className="mt-5 text-lg leading-relaxed text-muted-foreground">{m.lead}</p>
          <p className="mt-6 flex items-start gap-2.5 text-sm text-muted-foreground">
            <Check className="mt-0.5 size-4 shrink-0 text-positive" />
            {m.digest}
          </p>
        </FadeIn>

        <FadeIn delayMs={90}>
          <figure className="rounded-xl border bg-paper p-6 shadow-[0_20px_50px_-30px_rgba(28,27,25,0.35)]">
            <figcaption className="flex items-center justify-between">
              <span className="text-sm font-medium">{m.sample.title}</span>
              <span className="stamp text-primary">изменение</span>
            </figcaption>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-border/70 bg-secondary/40 p-3">
                <p className="font-mono text-[10px] tracking-[0.1em] text-muted-foreground uppercase">
                  {m.wasLabel}
                </p>
                <p className="mt-1.5 text-sm line-through decoration-sanction/50">
                  {m.sample.was}
                </p>
              </div>
              <div className="rounded-lg border border-primary/30 bg-primary/[0.06] p-3">
                <p className="font-mono text-[10px] tracking-[0.1em] text-primary uppercase">
                  {m.nowLabel}
                </p>
                <p className="mt-1.5 text-sm font-medium">{m.sample.now}</p>
              </div>
            </div>
            <p className="mt-4 font-mono text-[11px] text-muted-foreground">
              {m.sample.effective}
            </p>
          </figure>
        </FadeIn>
      </div>

      {/* Примеры-товары как мостик в реестр */}
      <FadeIn>
        <div className="mt-16 border-t border-border/70 pt-10">
          <p className="text-sm text-muted-foreground">{ru.landing.examplesLabel}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {exampleHits.map((hit) => (
              <Link
                key={hit.id}
                to={`/product/${hit.id}`}
                className="group rounded-lg border bg-paper p-4 transition-colors hover:border-foreground/25 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{hit.displayName}</span>
                  <ArrowUpRight className="size-4 shrink-0 text-muted-foreground transition-transform duration-300 ease-[var(--ease-brand)] group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                </div>
                <p className="mt-2 font-mono text-xs text-muted-foreground">
                  {formatHsCode(hit.code)}
                </p>
                <p className="mt-3 text-xs font-medium text-primary">
                  {pluralize(hit.requirementsCount, 'требование', 'требования', 'требований')}
                </p>
              </Link>
            ))}
          </div>
        </div>
      </FadeIn>
    </section>
  )
}
