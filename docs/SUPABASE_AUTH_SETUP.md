# Настройка панели Supabase для auth-флоу

Эти три настройки в панели Supabase делает **владелец аккаунта** — у агента доступа к
панели нет (MCP в чужом аккаунте, CLI не залинкован в проект). Значения ниже —
скопировать-вставить; они совпадают с `supabase/config.toml` (source of truth в репо).

Проект: `kcjlrvgjtoefqgzxuizz` · Прод: `https://inspectorx.uz` (канонический домен с 19.07.2026;
прежний адрес `https://inspectorx-v2.vercel.app` остаётся рабочим и в списке Redirect URLs)

> ✅ **Шаги 1–2 выполнены и проверены на проде.** Код auth-флоу задеплоен с 12.07.2026
> (PR #6 смержен 12.07.2026; маршруты `/auth/confirm`, `/auth/reset`, `/forgot-password` —
> `src/App.tsx:29-31`). Site URL в панели = `https://inspectorx.uz` (обновлён 19.07.2026 под
> канонический домен), подтверждение почты включено — на localhost письма больше не ведут.
>
> **Осталось:** шаг 3 — русские шаблоны писем (косметика); позже — свой SMTP через Resend.
> Порядок работ на будущее остаётся прежним: **код → панель → сквозная проверка.**

---

## Шаг 1. Authentication → URL Configuration — ✅ сделано 12.07.2026 (домен обновлён 19.07.2026)

**Site URL:**

```
https://inspectorx.uz
```

**Redirect URLs** (добавить все пять; кнопка «Add URL» на каждую строку):

```
https://inspectorx-v2.vercel.app/**
https://inspectorx.uz/**
https://www.inspectorx.uz/**
http://localhost:5173/**
http://127.0.0.1:5173/**
```

Сохранить (Save).

---

## Шаг 2. Authentication → Providers → Email — ✅ сделано 12.07.2026

- **Confirm email** — должно быть **включено** (обычно уже включено — просто убедиться,
  что галка не снята).

---

## Шаг 3. Authentication → Email Templates — ◐ не сделано (единственное открытое из этого документа)

Вставить русские шаблоны ниже. Отправитель — «ИнспекторX». Обратный адрес до перехода на
Resend — стандартный Supabase (`noreply@mail.app.supabase.io`).

### 3.1. Confirm signup

**Subject:**

```
Подтвердите адрес — ИнспекторX
```

**Message body (HTML):**

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

### 3.2. Reset password

**Subject:**

```
Смена пароля — ИнспекторX
```

**Message body (HTML):**

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

---

## Финальная сквозная проверка (после шагов 1–3)

> ✅ Пройдена 12.07.2026 после шагов 1–2: регистрация с подтверждением почты работает
> end-to-end. Тогда проверяли на адресе `inspectorx-v2.vercel.app`; сейчас канонический
> вход — `https://inspectorx.uz` (те же маршруты). Повторить после шага 3.

1. Открыть `https://inspectorx-v2.vercel.app/register`, зарегистрироваться на **реальный
   ящик** (имя, email, пароль ≥ 6 символов).
2. Дождаться письма «Подтвердите адрес — ИнспекторX» (проверить и «Спам»). Ссылка должна
   вести на `https://inspectorx-v2.vercel.app/auth/confirm`, **не** на localhost.
3. Перейти по ссылке → страница «Адрес подтверждён» → автопереход в кабинет.
4. Выйти, нажать «Забыли пароль?» → ввести тот же email → письмо «Смена пароля —
   ИнспекторX» → перейти → задать новый пароль → вход с новым паролем.

> ⏱️ **Лимит встроенной почты Supabase — несколько писем в час на весь проект.** Между
> письмами выдерживать паузу; для публичного потока людей это не годится — см. «Позже:
> Resend» ниже.

---

## Убрать тестовых пользователей — ✅ сделано (проверено 29.07.2026)

В проде остался ровно один пользователь — демо-аккаунт `turdiev17.10+ixdemo@gmail.com`
(создан 11.07.2026, `is_subscribed=true`); три тестовые учётки ниже удалены.

Что удаляли в **Authentication → Users** после отладки флоу:

```
ix.regtest.20260712@gmail.com
ix.regtest2.20260712@gmail.com
ix.regtest3.20260712@gmail.com
```

Все три — неподтверждённые тестовые адреса, в проде не нужны.

---

## Позже: свой SMTP через Resend (не сейчас)

Встроенная почта Supabase — только для тестов (жёсткий лимит, риск спама). Перед публичным
запуском подключить Resend. **Изменений в коде не требуется** — шаблоны и `emailRedirectTo`
остаются те же, меняется только транспорт и обратный адрес.

1. Завести аккаунт на `resend.com`, верифицировать домен `inspectorx.uz`
   (3 DNS-записи).
2. Панель Supabase → **Authentication → SMTP Settings** → включить свой SMTP
   (host / port / user / pass из Resend), sender = `noreply@inspectorx.uz`,
   sender name = «ИнспекторX».
3. Поднять лимиты рассылки в **Authentication → Rate Limits**.
