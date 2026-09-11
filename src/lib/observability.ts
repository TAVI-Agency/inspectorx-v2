// Sentry и аналитика (Plausible / Яндекс.Метрика) за env-флагами.
// Всё включается только при заданных переменных окружения — без них ни одного лишнего запроса в сеть.

export type ObservabilityEnv = {
  VITE_SENTRY_DSN?: string
  VITE_PLAUSIBLE_DOMAIN?: string
  VITE_YM_ID?: string
  MODE?: string
}

export type ScriptDescriptor = {
  src?: string
  inline?: string
  attrs?: Record<string, string>
}

/** Чистая функция: список скриптов аналитики для заданного env. Без переменных — пустой массив. */
export function analyticsScripts(env: ObservabilityEnv): ScriptDescriptor[] {
  const scripts: ScriptDescriptor[] = []

  if (env.VITE_PLAUSIBLE_DOMAIN) {
    scripts.push({
      src: 'https://plausible.io/js/script.js',
      attrs: { defer: '', 'data-domain': env.VITE_PLAUSIBLE_DOMAIN },
    })
  }

  if (env.VITE_YM_ID) {
    const id = Number(env.VITE_YM_ID)
    if (Number.isFinite(id)) {
      scripts.push({
        inline: `(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
   m[i].l=1*new Date();for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
   k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
   (window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");

   ym(${id}, 'init', {
        clickmap: true,
        trackLinks: true,
        accurateTrackBounce: true
   });`,
      })
    }
  }

  return scripts
}

function injectScript(descriptor: ScriptDescriptor): void {
  if (typeof document === 'undefined') return

  const el = document.createElement('script')
  if (descriptor.src) {
    el.setAttribute('src', descriptor.src)
  }
  if (descriptor.attrs) {
    for (const [key, value] of Object.entries(descriptor.attrs)) {
      el.setAttribute(key, value)
    }
  }
  if (descriptor.inline) {
    el.textContent = descriptor.inline
  }
  document.head.appendChild(el)
}

/**
 * Включается только при заданных VITE_SENTRY_DSN / VITE_PLAUSIBLE_DOMAIN / VITE_YM_ID;
 * без них — no-op.
 */
export function initObservability(env: ObservabilityEnv = {}): void {
  if (env.VITE_SENTRY_DSN) {
    // Динамический импорт — чтобы @sentry/react не попадал в общий бандл, когда DSN не задан.
    void import('@sentry/react').then((Sentry) => {
      Sentry.init({
        dsn: env.VITE_SENTRY_DSN,
        environment: env.MODE,
        tracesSampleRate: 0.1,
      })
    })
  }

  for (const script of analyticsScripts(env)) {
    injectScript(script)
  }
}
