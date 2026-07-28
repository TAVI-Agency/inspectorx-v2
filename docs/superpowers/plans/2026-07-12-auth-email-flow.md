# Auth Email Flow — Implementation Plan

> **Статус на 29.07.2026:** реализован — PR #6 смержен 12.07.2026
> (merge-коммит `553e699`), флоу в проде. Чекбоксы ниже по ходу работы
> не проставлялись: источник истины о состоянии — эта строка, а не `- [ ]`.
> Закрыто после плана: тестовые пользователи `ix.regtest*.20260712` удалены
> (на 29.07.2026 в `auth.users` 1 демо-пользователь); прод-домен сменился на
> канонический `https://inspectorx.uz` (PR #9, 19.07.2026) — везде ниже, где
> в плане указан `https://inspectorx-v2.vercel.app`, читать новый домен.
> Открытый остаток — русские шаблоны писем в панели Supabase (**Шаг 3** инструкции
> `docs/SUPABASE_AUTH_SETUP.md`); шаги 1 и 2 выполнены 12.07.2026.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Довести до прода корректный флоу регистрации/входа с подтверждением e-mail и восстановлением пароля по спеке `docs/superpowers/specs/2026-07-12-auth-email-flow-design.md`.

**Architecture:** SPA (Vite + React Router) поверх Supabase Auth (implicit flow, `detectSessionInUrl`). Письма ведут на страницы-обработчики `/auth/confirm` и `/auth/reset`; состояние сессии — через существующий `AuthProvider`. Прототип всего кода УЖЕ лежит в рабочем дереве ветки `worktree-auth-email-flow` (не закоммичен) — задачи 1–3 сверяют его со спекой и коммитят, задачи 4–6 проверяют и выкатывают.

**Tech Stack:** React 19 + TypeScript, react-router-dom, @supabase/supabase-js v2, Tailwind, lucide-react, дизайн-система C (`src/pages/c/ui.tsx`).

## Global Constraints

- В проекте НЕТ тестового фреймворка (scripts: `dev`, `build`, `lint`, `preview`). Верификация по спеке §10: `npm run build` + `npm run lint` + живой прогон в браузере через `npm run preview`. Тестовый фреймворк НЕ добавлять (YAGNI).
- Коммиты подписывать от `TAVI-Agency` (git user уже настроен), сообщения — conventional commits на русском (стиль репо: `feat(auth): …`).
- Все тексты UI — только через `src/i18n/ru.ts` (в компонентах строковых литералов с русским текстом быть не должно, кроме уже существующих подзаголовков CAuthPage).
- Рабочая директория: `/Users/abduraxmonturdiyev/inspector-x-final/.claude/worktrees/auth-email-flow` (git worktree, ветка `worktree-auth-email-flow`). НЕ переходить в основной чекаут.
- Прод-домен: `https://inspectorx-v2.vercel.app`. Никогда не пушить в `main` напрямую — только draft PR.
- Supabase-проект: `kcjlrvgjtoefqgzxuizz`. Доступа к панели у агента НЕТ — настройки панели делает владелец по инструкции (Task 5).
- В прод-базе остались 2 тестовых неподтверждённых пользователя: `ix.regtest.20260712@gmail.com`, `ix.regtest2.20260712@gmail.com` — упомянуть в PR, удалит владелец через панель.

---

### Task 1: Ядро auth — методы, redirectTo, строки

**Files:**
- Modify: `src/app/auth.tsx` (прототип уже в рабочем дереве)
- Create: `src/lib/auth-url.ts` (прототип уже в рабочем дереве)
- Modify: `src/i18n/ru.ts` (прототип уже в рабочем дереве)

**Interfaces:**
- Consumes: существующий `supabase` клиент из `src/lib/supabase.ts` (создан без опций → implicit flow, `detectSessionInUrl: true` по умолчанию — менять нельзя).
- Produces (на это опираются Task 2):
  - `useAuth()` дополнительно возвращает:
    - `signUp(email, password, fullName): Promise<{ error?: string; needsConfirmation?: boolean }>`
    - `resendConfirmation(email: string): Promise<{ error?: string }>`
    - `requestPasswordReset(email: string): Promise<{ error?: string }>`
    - `updatePassword(password: string): Promise<{ error?: string }>`
  - `parseAuthHashError(hash: string): string | null` из `@/lib/auth-url`
  - Строки `ru.auth.*`: `forgotPassword`, `confirmSentTitle`, `confirmSentText(email)`, `confirmSentSpamHint`, `resend`, `resendDone`, `resendCooldown`, `confirmingTitle`, `confirmedTitle`, `confirmedText`, `confirmedCta`, `confirmErrorTitle`, `confirmErrorText`, `forgotTitle`, `forgotText`, `forgotCta`, `forgotSentTitle`, `forgotSentText(email)`, `resetTitle`, `resetText`, `newPassword`, `resetCta`, `resetDoneTitle`, `resetDoneText`, `resetLinkInvalidTitle`, `resetLinkInvalidText`, `backToLogin`, `errors.samePassword`.

- [ ] **Step 1: Сверить `src/app/auth.tsx` с эталоном**

Файл уже изменён в рабочем дереве. Проверить `git diff src/app/auth.tsx` — критичные места должны быть ровно такими:

```tsx
/** Ссылки в письмах должны вести на текущий домен, а не на Site URL проекта */
const emailRedirect = (path: string) => `${window.location.origin}${path}`
```

```tsx
const signUp = useCallback(
  async (email: string, password: string, fullName: string) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName },
        emailRedirectTo: emailRedirect('/auth/confirm'),
      },
    })
    if (error) return { error: error.message }
    // При включённом подтверждении почты Supabase не выдаёт ошибку на занятый
    // email (анти-перечисление), а возвращает пользователя без identities.
    if (data.user && data.user.identities?.length === 0)
      return { error: 'already registered' }
    return { needsConfirmation: !data.session }
  },
  [],
)

const resendConfirmation = useCallback(async (email: string) => {
  const { error } = await supabase.auth.resend({
    type: 'signup',
    email,
    options: { emailRedirectTo: emailRedirect('/auth/confirm') },
  })
  return error ? { error: error.message } : {}
}, [])

const requestPasswordReset = useCallback(async (email: string) => {
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: emailRedirect('/auth/reset'),
  })
  return error ? { error: error.message } : {}
}, [])

const updatePassword = useCallback(async (password: string) => {
  const { error } = await supabase.auth.updateUser({ password })
  return error ? { error: error.message } : {}
}, [])
```

Все четыре метода прокинуты в `<Ctx.Provider value={{ … signIn, signUp, resendConfirmation, requestPasswordReset, updatePassword, signOut }}>`, интерфейс `AuthCtx` дополнен теми же сигнатурами (см. Interfaces выше).

- [ ] **Step 2: Сверить `src/lib/auth-url.ts`**

Полное содержимое файла:

```ts
/**
 * Ошибки из ссылок в письмах Supabase приходят в hash-фрагменте:
 * /auth/confirm#error=access_denied&error_code=otp_expired&error_description=...
 * Успешные токены из hash забирает сам supabase-js (detectSessionInUrl).
 */
export function parseAuthHashError(hash: string): string | null {
  const params = new URLSearchParams(hash.replace(/^#/, ''))
  return params.get('error_code') ?? params.get('error')
}
```

- [ ] **Step 3: Сверить строки в `src/i18n/ru.ts`**

В блоке `auth:` после `loginRequired` должны стоять все строки из Interfaces (уже добавлены; `git diff src/i18n/ru.ts`). Функциональные строки — стрелочные функции: `confirmSentText: (email: string) => …`, `forgotSentText: (email: string) => …`. В `errors` добавлена `samePassword: 'Новый пароль совпадает со старым — придумайте другой'`.

- [ ] **Step 4: Проверить компиляцию**

Run: `npm run build`
Expected: `✓ built in …` без ошибок tsc (предупреждение про chunk > 500 kB — известное, игнорировать).

- [ ] **Step 5: Commit**

```bash
git add src/app/auth.tsx src/lib/auth-url.ts src/i18n/ru.ts
git commit -m "feat(auth): методы подтверждения почты и сброса пароля в AuthProvider

emailRedirectTo на текущий домен, needsConfirmation из ответа signUp,
распознавание занятого email по identities, resend/reset/updatePassword,
русские строки для всех новых экранов."
```

---

### Task 2: Страницы и маршруты

**Files:**
- Modify: `src/pages/c/CAuthPage.tsx` (прототип уже в рабочем дереве)
- Create: `src/pages/c/CConfirmEmailPage.tsx` (прототип уже в рабочем дереве)
- Create: `src/pages/c/CForgotPasswordPage.tsx` (прототип уже в рабочем дереве)
- Create: `src/pages/c/CResetPasswordPage.tsx` (прототип уже в рабочем дереве)
- Modify: `src/App.tsx` (прототип уже в рабочем дереве)

**Interfaces:**
- Consumes: `useAuth()` из Task 1 (все 4 новых метода + `session`, `loading`), `parseAuthHashError` из `@/lib/auth-url`, строки `ru.auth.*` из Task 1, `CCard` из `./ui`, `Button`/`Input`/`Label` из `@/components/ui/*`.
- Produces: маршруты `/auth/confirm`, `/auth/reset`, `/forgot-password` (внутри `CLayout`); экспорт `ResendButton({ email })` из `CAuthPage.tsx` (используется также на `/auth/confirm`? — НЕТ: `CConfirmEmailPage` имеет собственную форму с полем email; `ResendButton` используется в `ConfirmSentCard` и при ошибке «не подтверждён» на логине).

- [ ] **Step 1: Сверить `src/pages/c/CAuthPage.tsx`**

Ключевые требования к файлу (уже реализован, `git diff` для сверки):

1. `ResendButton` — экспортируемая кнопка повторной отправки с состояниями `idle | pending | sent | cooldown`; при ошибке с текстом `rate limit` показывает `ru.auth.resendCooldown`, иначе после отправки `ru.auth.resendDone`; через 60 с (`window.setTimeout(…, 60_000)`) возвращается в `idle`.
2. `ConfirmSentCard({ email })` — карточка «Проверьте почту»: иконка `MailCheck`, `confirmSentTitle`, `confirmSentText(email)`, `confirmSentSpamHint`, внизу `ResendButton`.
3. В `submit` для регистрации:

```tsx
if (isRegister) {
  const result = await signUp(email.trim(), password, fullName.trim())
  setPending(false)
  if (result.error) setError(mapAuthError(result.error))
  else if (result.needsConfirmation) setConfirmSentTo(email.trim())
  else navigate('/cabinet', { replace: true })
}
```

4. При `error === ru.auth.errors.notConfirmed` и непустом email под текстом ошибки рендерится `<ResendButton email={email.trim()} />`.
5. На форме входа рядом с лейблом «Пароль» — ссылка `to="/forgot-password"` с текстом `ru.auth.forgotPassword`.
6. Если `confirmSentTo` установлен — вместо формы рендерится `<ConfirmSentCard email={confirmSentTo} />`.

- [ ] **Step 2: Сверить три новые страницы**

`CConfirmEmailPage.tsx` — обработчик ссылки подтверждения:
- Начальное состояние `failed = parseAuthHashError(window.location.hash) !== null`.
- Если нет ни `session`, ни `failed` через `CONFIRM_TIMEOUT_MS = 8000` → `failed = true`.
- При появлении `session` → карточка «Адрес подтверждён» + авторедирект в `/cabinet` через 1800 мс + кнопка `confirmedCta`.
- При `failed` → карточка `confirmErrorTitle`/`confirmErrorText` с формой: поле email + submit `resend` → `resendConfirmation(email)` → `resendDone`.
- Пока ждём — спиннер `LoaderCircle` + `confirmingTitle`.

`CForgotPasswordPage.tsx` — запрос сброса:
- Форма: email + кнопка `forgotCta` → `requestPasswordReset(email)` → ВСЕГДА (не глядя на ошибку) карточка `forgotSentTitle` + `forgotSentText(email)` + `confirmSentSpamHint` (анти-перебор, спека §8).
- Внизу всегда ссылка `to="/login"` с `backToLogin`.

`CResetPasswordPage.tsx` — установка нового пароля:
- Начальное `invalid = parseAuthHashError(window.location.hash) !== null`; таймаут `RECOVERY_TIMEOUT_MS = 8000` до `invalid`, если сессия не появилась.
- При `session` → форма: поле `newPassword` (`minLength={6}`, `autoComplete="new-password"`) + кнопка `resetCta` → `updatePassword(password)`.
- Ошибка `different from the old` → `ru.auth.errors.samePassword`, иначе `weakPassword`.
- Успех → карточка `resetDoneTitle`/`resetDoneText` + авторедирект в `/cabinet` через 1800 мс.
- При `invalid` → карточка `resetLinkInvalidTitle`/`resetLinkInvalidText` + ссылка на `/forgot-password`.

- [ ] **Step 3: Сверить маршруты в `src/App.tsx`**

```tsx
{ path: '/login', element: <CAuthPage mode="login" /> },
{ path: '/register', element: <CAuthPage mode="register" /> },
{ path: '/auth/confirm', element: <CConfirmEmailPage /> },
{ path: '/auth/reset', element: <CResetPasswordPage /> },
{ path: '/forgot-password', element: <CForgotPasswordPage /> },
```

(внутри детей `CLayout`, до catch-all `*`). Импорты трёх страниц добавлены.

- [ ] **Step 4: Проверить сборку и линт**

Run: `npm run build && npm run lint`
Expected: build `✓`, lint — только уже существовавшие предупреждения `only-export-components` (новых ошибок нет).

- [ ] **Step 5: Commit**

```bash
git add src/pages/c/CAuthPage.tsx src/pages/c/CConfirmEmailPage.tsx \
  src/pages/c/CForgotPasswordPage.tsx src/pages/c/CResetPasswordPage.tsx src/App.tsx
git commit -m "feat(auth): экраны подтверждения почты и восстановления пароля

«Проверьте почту» после регистрации, /auth/confirm с обработкой протухших
ссылок, /forgot-password с анти-перебором, /auth/reset с recovery-сессией,
повторная отправка письма с кулдауном 60с."
```

---

### Task 3: config.toml — source of truth для настроек Auth

**Files:**
- Modify: `supabase/config.toml` (прототип уже в рабочем дереве)

**Interfaces:**
- Produces: документированные значения для панели (Task 5 копирует их отсюда). На прод сами по себе НЕ применяются (CLI не залинкован) — это фиксация намерения в репо.

- [ ] **Step 1: Сверить diff `supabase/config.toml`**

```toml
site_url = "https://inspectorx-v2.vercel.app"
additional_redirect_urls = [
  "https://inspectorx-v2.vercel.app/**",
  "https://inspector-x.uz/**",
  "https://www.inspector-x.uz/**",
  "http://localhost:5173/**",
  "http://127.0.0.1:5173/**",
]
```

и в `[auth.email]`: `enable_confirmations = true`. Больше НИЧЕГО в файле не менять.

- [ ] **Step 2: Commit**

```bash
git add supabase/config.toml
git commit -m "chore(auth): прод-домены в site_url/redirect_urls, подтверждение почты включено

Файл — source of truth для настроек панели; на hosted-проект применяется
вручную (см. docs/SUPABASE_AUTH_SETUP.md)."
```

---

### Task 4: Живая проверка UI (preview + браузер)

**Files:** нет изменений кода (только проверка; при находках — фикс + отдельный коммит).

**Interfaces:**
- Consumes: собранное приложение (`npm run build` из Task 2), прод-Supabase (хардкод-фолбэки в `src/lib/supabase.ts`).

- [ ] **Step 1: Запустить preview**

```bash
npm run build && nohup npm run preview -- --port 4199 --strictPort \
  > "$CLAUDE_JOB_DIR/tmp/preview.log" 2>&1 &
sleep 2 && curl -s -o /dev/null -w "%{http_code}\n" http://localhost:4199/login
```

Expected: `200`.

- [ ] **Step 2: Прогнать 5 сценариев в браузере (Chrome MCP)**

| # | Действие | Ожидание |
|---|---|---|
| 1 | `/register` → имя «Тест Проверка», НОВЫЙ email вида `ix.regtest<N>.20260712@gmail.com`, пароль `RegTest#2026x` → «Создать аккаунт» | Карточка «Проверьте почту» с адресом, подсказкой про спам и кнопкой «Отправить письмо ещё раз» |
| 2 | `/auth/confirm#error=access_denied&error_code=otp_expired&error_description=x` | Карточка «Ссылка не сработала» с формой email + «Отправить письмо ещё раз» |
| 3 | `/forgot-password` → любой email → «Отправить ссылку» | Карточка «Письмо отправлено» с текстом «Если аккаунт … существует» |
| 4 | `/login` → email из сценария 1 + пароль → «Войти» | Ошибка «Email не подтверждён…» И ПОД НЕЙ кнопка «Отправить письмо ещё раз» |
| 5 | `/auth/reset` (без hash) | Спиннер «Загрузка…», через ~8 с — карточка «Ссылка не сработала» со ссылкой «Восстановление пароля» |

Известная особенность прогона: клики по `ref` из `read_page` могут не срабатывать — кликать по координатам из свежего скриншота.

- [ ] **Step 3: Остановить preview и зафиксировать результат**

```bash
pkill -f "vite preview" || true
```

Если находки — исправить, повторить сценарий, закоммитить фикс (`fix(auth): …`). Сценарии 1–3 уже прогонялись на прототипе успешно; 4–5 — впервые.

---

### Task 5: Инструкция владельцу по панели Supabase

**Files:**
- Create: `docs/SUPABASE_AUTH_SETUP.md`

**Interfaces:**
- Consumes: значения из `supabase/config.toml` (Task 3) и шаблоны писем из спеки §7.
- Produces: пошаговая инструкция, по которой владелец делает 3 настройки после деплоя.

- [ ] **Step 1: Создать `docs/SUPABASE_AUTH_SETUP.md`**

Содержимое — ровно три шага со значениями копипастой (Site URL + 5 redirect URL из Task 3; проверка «Confirm email» включён; два HTML-шаблона писем из спеки §7 с темами «Подтвердите адрес — ИнспекторX» и «Смена пароля — ИнспекторX»), плюс:
- предупреждение о порядке: настраивать ТОЛЬКО ПОСЛЕ деплоя PR (спека §6.4);
- финальная сквозная проверка (регистрация на реальный ящик → письмо → клик → кабинет; сброс пароля);
- напоминание удалить тестовых пользователей `ix.regtest.20260712@gmail.com` и `ix.regtest2.20260712@gmail.com` (Authentication → Users);
- раздел «Позже: Resend» со шагами из спеки §9.
- Шаблоны писем брать ДОСЛОВНО из спеки §7 (`docs/superpowers/specs/2026-07-12-auth-email-flow-design.md`).

- [ ] **Step 2: Commit**

```bash
git add docs/SUPABASE_AUTH_SETUP.md
git commit -m "docs(auth): инструкция по настройке панели Supabase (URL, шаблоны писем)"
```

---

### Task 6: Push + draft PR

**Files:** нет изменений кода.

- [ ] **Step 1: Финальный гейт**

Run: `npm run build && npm run lint && git status --short`
Expected: build `✓`, lint без новых предупреждений, рабочее дерево чистое (всё закоммичено).

- [ ] **Step 2: Push и draft PR**

```bash
git push -u origin worktree-auth-email-flow
gh pr create --draft --base main --title "feat(auth): подтверждение e-mail и восстановление пароля" --body "$(cat <<'EOF'
## Что сделано
Полный флоу регистрации по спеке docs/superpowers/specs/2026-07-12-auth-email-flow-design.md:
- экран «Проверьте почту» после регистрации, повторная отправка письма (кулдаун 60с)
- /auth/confirm — обработчик ссылки из письма (успех / протухшая ссылка)
- /forgot-password + /auth/reset — восстановление пароля (анти-перебор)
- emailRedirectTo на текущий домен; распознавание занятого email
- русские строки; config.toml как source of truth настроек Auth

## После мержа (владелец, по docs/SUPABASE_AUTH_SETUP.md)
1. Site URL + Redirect URLs в панели Supabase
2. Русские шаблоны писем
3. Сквозная проверка на проде; удалить тестовых пользователей ix.regtest*.20260712@gmail.com

## Проверено
build+lint зелёные; 5 UI-сценариев вживую через vite preview (скриншоты в сессии).
До настройки панели письма продолжают вести на localhost — это чинится шагом 1.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01WVTWdYh6xGwKrXG7YH8FaD
EOF
)"
```

Expected: URL созданного PR.

- [ ] **Step 3: Сообщить владельцу**

Итоговое сообщение: ссылка на PR + напоминание порядка (мерж → панель по `docs/SUPABASE_AUTH_SETUP.md` → сквозная проверка). Прод-проверка (Task 7) возможна только после этих ручных шагов.

---

### Task 7: Сквозная проверка на проде (после мержа и настроек панели) — ЧЕКПОЙНТ

**Files:** нет. Выполняется ТОЛЬКО после: (а) PR смержен и Vercel задеплоил, (б) владелец сделал шаги из `docs/SUPABASE_AUTH_SETUP.md`.

- [ ] **Step 1: Дымовая проверка редиректа verify**

```bash
curl -s -o /dev/null -w "%{redirect_url}\n" \
  "https://kcjlrvgjtoefqgzxuizz.supabase.co/auth/v1/verify?token=bogus&type=signup"
```

Expected: редирект на `https://inspectorx-v2.vercel.app/#error=…` (НЕ localhost). Это подтверждает Site URL без отправки писем.

- [ ] **Step 2: Реальный круг с участием владельца**

Владелец (или агент с реальным ящиком владельца): регистрация на проде → письмо пришло (рус., тема «Подтвердите адрес — ИнспекторX») → клик → `/auth/confirm` → кабинет. Затем «Забыли пароль?» → письмо → новый пароль → вход. Учесть лимит встроенной почты (2 письма/час) — между письмами выдерживать паузу.

- [ ] **Step 3: Зафиксировать результат**

Обновить память проекта (auth-флоу в проде, что осталось: Resend). Сообщить `result:`.
