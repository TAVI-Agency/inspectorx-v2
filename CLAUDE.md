# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

InspectorX v2 — compliance-платформа для Узбекистана: «чек-лист соответствия бизнеса», а не справочник законов. Прод: https://inspectorx-v2.vercel.app (автодеплой `main` через Vercel, SPA-rewrite в `vercel.json`).

Язык проекта — русский: комментарии, строки UI, коммиты (conventional commits по-русски, напр. `feat(landing): …`).

## Команды

```bash
npm run dev        # Vite dev-сервер (localhost:5173)
npm run build      # tsc -b && vite build — это же и проверка типов
npm run lint       # oxlint
```

Юнит-тестов нет. Визуальная проверка — Playwright-скрипты (нужен запущенный dev-сервер; база переопределяется `SHOT_BASE`):

```bash
node scripts/shot.mjs <path> <name> [steps.mjs]  # shots/<name>-{light,dark}-{1440,375}.png + консольные ошибки в stdout
node scripts/walkthrough.mjs                     # сквозной путь: лендинг → поиск → товар → карточка → пейволл → тариф → заявка
```

`steps.mjs` (примеры в `scripts/steps/`) экспортирует `default: async (page, ctx) => {}` — действия перед снимком.

### База данных

Миграции — `supabase/migrations/` (схема + RLS + контент). Локально:

```bash
supabase db start && supabase db reset --local
```

Накат на прод — `supabase db push` (линкованный проект) или Supabase MCP. `scripts/generate_v1_content_migration.mjs` — одноразовый перенос контента из v1, обычно трогать не нужно.

## Архитектура

Стек: Vite + React 19 + TypeScript + Tailwind v4 + shadcn/ui (Base UI) · React Router · TanStack Query · Supabase (Postgres, Auth, RLS). Алиас `@` → `src/`.

### Маршруты (`src/App.tsx`)

- `/` — `src/pages/landing-b/LandingB.tsx`: лендинг «Один маршрут», самодостаточный (своя шапка/подвал, свой CSS `landing-b.css`).
- Кокпит «Маршрут товара» (дизайн C) под `CLayout`: `/catalog`, `/product/:productId`, `/pricing`, `/cabinet`, `/login`, `/register` — всё в `src/pages/c/`.

### Слой данных (`src/data/`) — главное место, где легко запутаться

Компоненты ходят в данные ТОЛЬКО через React-Query-хуки `src/data/hooks.ts` → публичный API `src/data/index.ts`. Тот композиционно смешивает реальные данные Supabase (`real.ts`) с мок-фикстурами (`mock/`):

- **Сигареты** — живые данные Supabase + мок-оверлей изменений;
- **Молоко** — реальный товар, требования из фикстур;
- **Парацетамол** — полностью мок.

Закрытый RLS контент приходит как `Gated<T>` со статусом `'locked'`; мок-подписчик получает демо-шаблон details. Не обходить `index.ts` прямыми запросами к Supabase из компонентов.

### Пейволл — закрыт на сервере

Граница подписки — на уровне таблиц RLS: `requirement_contents` (бесплатный тизер) читают все, `requirement_details` — только при `profiles.is_subscribed`. Клиент не может включить подписку себе; активация — вручную админом. Дефолтные URL/publishable key Supabase зашиты в `src/lib/supabase.ts` — это публичные реквизиты, безопасность держит RLS; `.env` может их переопределить.

Dev-тумблер «я подписчик» (`src/app/app-mode.tsx`, localStorage `ix-mock-subscriber`) показывает вид подписчика на моках — не путать с реальной подпиской из `profiles`.

### Ключевые инварианты схемы

- Единая таблица `requirements`; текст — в `requirement_contents` / `requirement_details` по строке на язык (ru/uz/en).
- `flagged_by_change` — флаг поверх `published`: карточка при ре-ревью остаётся на витрине.
- Коды ТН ВЭД/ИКПУ — text; применимость через scope (код / класс-префикс / все товары).
- Уведомления: `change_events → requirement_change_impacts → user_notifications` (per-user).

### Прочее

- Все строки UI — в `src/i18n/ru.ts` (единственный источник текста; uz/en позже с тем же контрактом). Не хардкодить текст в компонентах.
- Цена тарифа — `src/config.ts` (не утверждена, менять только там).
- SEO-файлы: `index.html` (метатеги, JSON-LD), `public/` (robots.txt, sitemap.xml, llms.txt, og.png). Канонический домен — `inspectorx.uz` (запасной `inspector-x.uz` — редирект на него в Vercel).

## Документы-источники истины

- `docs/TARGET_FORMAT.md` — ТЗ продукта, контракт данных требования (§4). Технические решения подчиняются ему, а не наоборот.
- `docs/IDEAS.md` — идеи вне MVP; **не кодировать без явного решения**.
- `docs/LAUNCH_CHECKLIST.md` — правило заморозки: в текущий код после запуска добавляется только контент, новые фичи — через TARGET_FORMAT.
