# InspectorX v2

Compliance-платформа для Узбекистана: «чек-лист соответствия бизнеса», а не справочник законов.

- **ТЗ продукта:** `docs/TARGET_FORMAT.md` (контракт данных требования — §4)
- **Контекст и план:** `docs/SESSION_SUMMARY_2026-07-11.md`
- **Идеи вне MVP:** `docs/IDEAS.md` (не кодируем без решения)

## Стек

Vite + React + TypeScript + Tailwind v4 + shadcn/ui · Supabase (Postgres, Auth, RLS) · позже: Railway (конвейер Bridge)

## Запуск

```bash
cp .env.example .env   # заполнить ключами Supabase
npm install
npm run dev
```

## База данных

Миграции — в `supabase/migrations/` (схема + RLS). Локальная проверка:

```bash
supabase db start && supabase db reset --local
```

Накат на прод — `supabase db push` (линкованный проект) или Supabase MCP.

Ключевые инварианты схемы:

- Единая таблица `requirements`; текст — в `requirement_contents` (бесплатный тизер)
  и `requirement_details` (по подписке) по строке на язык (ru/uz/en).
- Пейволл закрыт на сервере (RLS), граница — на уровне таблиц.
- `flagged_by_change` — флаг поверх `published`: карточка при ре-ревью остаётся на витрине.
- Коды ТН ВЭД/ИКПУ — text; применимость через scope (код / класс-префикс / все товары).
- Уведомления: `change_events → requirement_change_impacts → user_notifications` (per-user).
