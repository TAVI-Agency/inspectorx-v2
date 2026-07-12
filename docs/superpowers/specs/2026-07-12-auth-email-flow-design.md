# Дизайн: правильный флоу регистрации и входа (подтверждение e-mail + сброс пароля)

**Дата:** 2026-07-12
**Проект:** InspectorX v2 (`https://inspectorx-v2.vercel.app`)
**Ветка:** `worktree-auth-email-flow`
**Статус:** согласован, готов к плану реализации

---

## 1. Контекст и проблема

Регистрация на проде сломана. Проверено живым тестом через прод Auth API:

- Подтверждение e-mail **включено** на проде (логин отвечает `email_not_confirmed`).
- **Site URL = `http://localhost:3000`** — ссылка из письма ведёт на localhost (проверен редирект `/auth/v1/verify` → `http://localhost:3000/#error=...`).
- В коде **нет** страницы-обработчика ссылки (`/auth/confirm`), нет `emailRedirectTo`, нет экрана «Проверьте почту».
- `signUp` шлёт только `full_name`; ошибки обрабатываются строковым матчингом.
- Восстановления пароля нет вообще — ни страницы, ни метода.

Итог для реального пользователя: регистрируется → приложение молча ведёт в `/cabinet` («войдите») → письмо приходит → ссылка ведёт в никуда → войти невозможно.

## 2. Цель и границы

**Цель:** сделать корректный, законченный флоу email+password с подтверждением адреса и восстановлением пароля, с русскими письмами и правильными редиректами.

**В объёме:**
- Регистрация с подтверждением e-mail и экраном «Проверьте почту».
- Обработчик ссылки подтверждения `/auth/confirm`.
- Восстановление пароля: `/forgot-password` + `/auth/reset`.
- Повторная отправка письма подтверждения (с кулдауном).
- Русские шаблоны писем (подтверждение, сброс).
- Правильные Site URL / Redirect URLs.

**НЕ в объёме (осознанно отложено):**
- Свой SMTP (Resend) — пока встроенная почта Supabase. Переход на Resend — отдельный будущий шаг, **без изменений кода** (см. §9).
- Поле «телефон» в форме регистрации.
- OAuth / соцвходы, magic-link, 2FA.
- Редирект-guard на защищённых маршрутах (оставляем текущую inline-карточку «войдите» на `/cabinet`).

## 3. Ключевое ограничение: встроенная почта Supabase

Supabase официально указывает: встроенная почта — **только для тестов**, жёсткий лимит (несколько писем в час на весь проект), высокий риск спама. Осознанное решение: сейчас используем встроенную (нет времени на отдельный сервис), она годится для тестов и первых ручных пользователей. **Перед любым публичным потоком людей нужен Resend** (§9). Код провайдеро-независим, поэтому переход не потребует переделки.

## 4. Пользовательские сценарии

### 4.1 Регистрация
1. `/register`: имя, e-mail, пароль → `signUp({ email, password, options: { data: { full_name }, emailRedirectTo: <origin>/auth/confirm } })`.
2. Ответ без сессии → экран **«Проверьте почту»** (адрес + подсказка про «Спам» + кнопка «отправить ещё раз»).
3. Письмо (рус.) → ссылка → `/auth/confirm`: `supabase-js` забирает токены из hash, сессия появляется → «Адрес подтверждён» → авто-редирект в `/cabinet`.
4. Триггер БД `handle_new_user` создаёт `profiles` (уже существует, не трогаем).

### 4.2 Вход
1. `/login` → `signInWithPassword` → `/cabinet`.
2. `email_not_confirmed` → сообщение + кнопка «отправить письмо ещё раз».
3. Ссылка «Забыли пароль?» → `/forgot-password`.

### 4.3 Сброс пароля
1. `/forgot-password`: e-mail → `resetPasswordForEmail(email, { redirectTo: <origin>/auth/reset })`.
2. Всегда экран **«Письмо отправлено»** одинаковым текстом (анти-перебор).
3. Письмо (рус.) → `/auth/reset`: `supabase-js` создаёт recovery-сессию → форма нового пароля → `updateUser({ password })` → `/cabinet`.

### 4.4 Повторная отправка подтверждения
- `resend({ type: 'signup', email, options: { emailRedirectTo } })`.
- Кнопка с кулдауном 60 сек; ошибку `rate limit` показываем как «Отправить снова можно через минуту».

## 5. Изменения в коде

Всё это делает агент; прототип уже собран в ветке `worktree-auth-email-flow` (build + lint зелёные, 3 из 4 экранов проверены локально).

| Файл | Изменение |
|---|---|
| `src/app/auth.tsx` | `emailRedirect(path)` через `window.location.origin`; `emailRedirectTo` в `signUp`; распознавание `needsConfirmation` (нет сессии) и «уже зарегистрирован» (`identities.length === 0`); новые методы `resendConfirmation`, `requestPasswordReset`, `updatePassword` в контексте `AuthCtx`. |
| `src/pages/c/CAuthPage.tsx` | Экран «Проверьте почту» (`ConfirmSentCard`); переиспользуемая `ResendButton` с кулдауном; ссылка «Забыли пароль?»; обработка `needsConfirmation`. |
| `src/pages/c/CConfirmEmailPage.tsx` (новый) | `/auth/confirm`: статусы «подтверждаем / подтверждён / ссылка не сработала»; при ошибке — форма повторной отправки; таймаут 8 сек. |
| `src/pages/c/CForgotPasswordPage.tsx` (новый) | `/forgot-password`: форма → «Письмо отправлено» (единый текст). |
| `src/pages/c/CResetPasswordPage.tsx` (новый) | `/auth/reset`: ждёт recovery-сессию → форма нового пароля → успех/невалидная ссылка. |
| `src/lib/auth-url.ts` (новый) | `parseAuthHashError(hash)` — достаёт `error_code`/`error` из hash-фрагмента ссылок. |
| `src/App.tsx` | Маршруты `/auth/confirm`, `/auth/reset`, `/forgot-password` (внутри `CLayout`). |
| `src/i18n/ru.ts` | Строки: подтверждение, повтор, восстановление, сброс, ошибка `samePassword`. |
| `supabase/config.toml` | `site_url` и `additional_redirect_urls` на прод-домены; `enable_confirmations = true`. **Локальный source-of-truth** — на прод сам по себе не применяется (CLI не залинкован), настоящая правка — в панели (§6). |

**Технические заметки:**
- `emailRedirectTo`/`redirectTo` учитываются Supabase только если URL входит в Redirect-allow-list (иначе — фолбэк на Site URL). Поэтому §6.1 обязателен.
- Vercel preview-деплои имеют динамические URL и не входят в allow-list — auth тестируем на прод-домене. Известное ограничение, не проблема сейчас.

## 6. Настройки Supabase (панель) — делает владелец аккаунта

Агент не имеет доступа к панели (MCP в чужом аккаунте, CLI не залинкован в проект). Три шага, значения ниже — скопировать-вставить.

### 6.1 Authentication → URL Configuration
- **Site URL:** `https://inspectorx-v2.vercel.app`
- **Redirect URLs (добавить):**
  ```
  https://inspectorx-v2.vercel.app/**
  https://inspector-x.uz/**
  https://www.inspector-x.uz/**
  http://localhost:5173/**
  http://127.0.0.1:5173/**
  ```

### 6.2 Authentication → Providers → Email
- **Confirm email:** включено (уже включено — подтвердить, что не выключено).

### 6.3 Authentication → Email Templates
Вставить русские шаблоны из §7 в «Confirm signup» и «Reset password».

### 6.4 Порядок деплоя (важно)
1. **Сначала** влить и задеплоить код (появляются `/auth/confirm`, `/auth/reset`, `/forgot-password`, `emailRedirectTo`, экраны).
2. **Потом** — §6.1–6.3 в панели.
3. Проверить сквозной круг на проде (§8).

Обоснование: подтверждение на проде уже включено, ссылки уже ломаются; правка Site URL до деплоя кода всё равно не даст рабочих страниц. Поэтому код — первым.

## 7. Русские шаблоны писем

Отправитель — «ИнспекторX». Обратный адрес до Resend — стандартный Supabase (`noreply@mail.app.supabase.io`).

### 7.1 Confirm signup
**Subject:** `Подтвердите адрес — ИнспекторX`
```html
<h2 style="font-family:system-ui,sans-serif;color:#0d1f22">Подтвердите адрес</h2>
<p style="font-family:system-ui,sans-serif;color:#0d1f22">Здравствуйте! Вы создали аккаунт в&nbsp;ИнспекторX.</p>
<p style="font-family:system-ui,sans-serif;color:#0d1f22">Нажмите кнопку, чтобы подтвердить адрес и войти:</p>
<p>
  <a href="{{ .ConfirmationURL }}"
     style="display:inline-block;padding:10px 18px;border-radius:8px;background:#1f9c8f;color:#fff;font-family:system-ui,sans-serif;text-decoration:none">
    Подтвердить адрес
  </a>
</p>
<p style="font-family:system-ui,sans-serif;color:#5b6b6d;font-size:13px">
  Если вы не регистрировались в&nbsp;ИнспекторX — просто проигнорируйте это письмо.
</p>
```

### 7.2 Reset password
**Subject:** `Смена пароля — ИнспекторX`
```html
<h2 style="font-family:system-ui,sans-serif;color:#0d1f22">Смена пароля</h2>
<p style="font-family:system-ui,sans-serif;color:#0d1f22">Вы запросили смену пароля в&nbsp;ИнспекторX.</p>
<p style="font-family:system-ui,sans-serif;color:#0d1f22">Нажмите кнопку, чтобы задать новый пароль:</p>
<p>
  <a href="{{ .ConfirmationURL }}"
     style="display:inline-block;padding:10px 18px;border-radius:8px;background:#1f9c8f;color:#fff;font-family:system-ui,sans-serif;text-decoration:none">
    Сменить пароль
  </a>
</p>
<p style="font-family:system-ui,sans-serif;color:#5b6b6d;font-size:13px">
  Если вы не запрашивали смену пароля — проигнорируйте это письмо, пароль останется прежним.
</p>
```

## 8. Граничные случаи и безопасность

- **Анти-перебор (forgot-password):** всегда «Письмо отправлено», независимо от наличия аккаунта.
- **«Email уже занят» (осознанный выбор UX > строгость):** при `identities.length === 0` показываем «аккаунт уже есть — войдите». Формально подтверждает существование адреса — принято ради удобства.
- **Протухшие/повторные ссылки:** `/auth/confirm` и `/auth/reset` разбирают hash-ошибку → аккуратный экран с путём восстановления (повтор письма / запросить сброс заново).
- **Таймаут ожидания токенов:** если за 8 сек нет ни сессии, ни ошибки — считаем ссылку недействительной (случай hash без токенов).
- **Кулдаун повторной отправки:** 60 сек в UI + мягкая обработка ответа `rate limit`.
- **`phone` в триггере:** `handle_new_user` читает `raw_user_meta_data->>'phone'` → останется `NULL` (поля нет). Столбец nullable, безвредно. Не трогаем.
- **Защищённые маршруты:** без изменений — `/cabinet` при отсутствии сессии показывает inline-карточку «войдите» (текущее поведение).

## 9. Будущий шаг: Resend (не сейчас)

Когда появится время / перед публичным запуском:
1. Аккаунт `resend.com`, верификация домена `inspector-x.uz` (3 DNS-записи).
2. В панели Supabase: Authentication → SMTP Settings → включить свой SMTP (host/port/user/pass Resend), sender = `noreply@inspector-x.uz`, sender name = «ИнспекторX».
3. Поднять лимиты рассылки в Rate Limits.

**Изменений в коде не требуется** — шаблоны и `emailRedirectTo` остаются те же; меняется только транспорт и обратный адрес.

## 10. Проверка

- **Локально (vite preview):** экраны «Проверьте почту», `/auth/confirm` (ошибка ссылки), `/forgot-password` — проверены вживую (скриншоты). Форма нового пароля на `/auth/reset` без recovery-сессии показывает загрузку/невалидную ссылку — проверить визуально.
- **Сквозной круг на проде** (после §6): реальная регистрация → письмо приходит → клик → вход в кабинет; сброс пароля тем же путём. До настроек панели письма физически уходят на localhost, поэтому финальная проверка — только после §6.
- `npm run build` и `npm run lint` — зелёные (обязательный гейт перед PR).

## 11. Деплой

- Код: PR в `main` → авто-деплой Vercel. Коммиты подписывать `TAVI-Agency`.
- Настройки панели (§6): владелец аккаунта по инструкции.
- Порядок: код → панель → проверка (§6.4).
