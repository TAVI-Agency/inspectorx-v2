# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

InspectorX v2 — compliance-платформа для Узбекистана: «чек-лист соответствия бизнеса», а не справочник законов. Прод: https://inspectorx-v2.vercel.app (автодеплой `main` через Vercel, SPA-rewrite в `vercel.json`).

Язык проекта — русский: комментарии, строки UI, коммиты (conventional commits по-русски, напр. `feat(landing): …`).

Экосистема: **LegalX** (законы, бывший JurisBase) + **SudX** (судебная практика — раздел внутри LegalX, схема `court` в его базе) + **InspectorX** (эта витрина). Два проекта Supabase в одной организации на одном аккаунте: LegalX-БД и InspectorX-БД. Python-воркеры обоих продуктов — на Railway. Топология зафиксирована в `docs/adr/0002-ecosystem-topology.md`.

## Команды

```bash
npm run dev        # Vite dev-сервер (localhost:5173)
npm run build      # tsc -b && vite build — это же и проверка типов
npm run lint       # oxlint
```

Юнит-тестов на фронте нет (Python-тесты — ниже). Визуальная проверка — Playwright-скрипты (нужен запущенный dev-сервер; база переопределяется `SHOT_BASE`):

```bash
node scripts/shot.mjs <path> <name> [steps.mjs]  # shots/<name>-{light,dark}-{1440,375}.png + консольные ошибки в stdout
node scripts/walkthrough.mjs                     # сквозной путь: лендинг → поиск → товар → карточка → пейволл → тариф → заявка
```

`steps.mjs` (примеры в `scripts/steps/`) экспортирует `default: async (page, ctx) => {}` — действия перед снимком.

### Конвейер контента (`importer/`, Python)

Тесты — `pytest.ini` в корне (маркер `integration` требует поднятый локальный Supabase, иначе сам себя скипает):

```bash
.venv-importer/bin/python -m pytest importer/tests -q   # 552 теста
```

Legacy-импортёр отчётов (`importer/pipeline.py`, команда `import-report`) — временный конвейер research-loop, статус в `docs/RESEARCH_PIPELINE_STATUS.md`. Целевой конвейер — Build (`importer/build/`, схема `pipeline`), CLI — `importer/cli.py`:

```bash
python -m importer build map --group <ref> --jurisdiction UZ        # Cartographer: draft-карта группы товаров
python -m importer build approve-map --map <id>                     # апрув владельцем: draft -> approved (стоп-точка ①)
python -m importer build run --map <id> [--no-publish]              # прогон 14 шагов конвейера по утверждённой карте
python -m importer build status --run <id>                          # статусы айтемов прогона
python -m importer build attention                                  # очередь needs_attention
python -m importer build coverage --run <id>                        # coverage-отчёт: карта vs факт
python -m importer build publish --run <id>                         # публикация draft_loaded по вердиктам
python -m importer build cost --run <id>                            # стоимость прогона по ролям (трейсинг, Задача 29)
python -m importer build eval-golden [--limit N] [--save-baseline]  # golden set (стоп-точка ②)
```

Мониторинг изменений LegalX (webhook → impact-маппер → history/discovery, Задачи 39–41):

```bash
python -m importer monitor process-changes                    # change_events -> impacts + флаг + ре-ревью + уведомления (cron 15 мин)
python -m importer monitor discovery                          # 'new'-события без impacts -> кандидаты pipeline.items (cron после process-changes)
python -m importer monitor build-history --requirement <id>   # ручной бэкафилл requirement_revisions
```

Живого LLM-ключа в контуре нет: `build map` / `build run` / `monitor process-changes` / `monitor discovery` падают `NotImplementedError` только при реальном обращении к модели (заглушки-раннеры в `importer/cli.py`); проверка проводки — тестами и синтетическим прогоном `scripts/pilot_synthetic.py`.

### База данных

Миграции — `supabase/migrations/` (схема + RLS + контент). Локально:

```bash
supabase db start && supabase db reset --local
```

**Накат на прод — автоматический.** К проекту Supabase подключена GitHub-интеграция
(`TAVI-Agency/inspectorx-v2`, рабочая директория `.`, ветка `main`, Deploy to production включён):
мёрж в `main` сам применяет новые файлы `supabase/migrations/` к боевой базе. Поэтому миграция
кладётся в `main` только когда готова — автоматического отката нет. Ручной путь
(`supabase db push`, Management API) остаётся запасным.

Edge Functions не используются: рантайм там Deno/TypeScript, Python туда не деплоится. Роль базы в запуске фоновых работ — только разбудить воркер на Railway: `pg_cron` для расписаний + `pg_net` для HTTP наружу (см. `20260727120000_lead_notifications.sql`).

Аккаунты, ключи и что из них сейчас протухло — `docs/INFRA_ACCOUNTS.md` (проекты переехали на
основной аккаунт владельца 02.08.2026; адрес БД и ключи проекта не менялись, токен уровня
аккаунта и ключ LegalX — менялись).

`scripts/generate_v1_content_migration.mjs` — одноразовый перенос контента из v1, обычно трогать не нужно.

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

### Схемы `catalog` и `pipeline` (Build-конвейер, мастер-план №1)

- `catalog` — товарный каталог: `product_types` (HS6 — товары, UNSPSC — услуги), `country_codes` (нацслои: ИКПУ/ТН ВЭД/ОКЭД…), `skus`. Требования привязываются только к типам (`requirement_applicability.product_type_id`) — подробности в `docs/adr/0004-product-catalog.md`.
- `pipeline` — рабочие таблицы Build-конвейера: `maps` (карта группы, апрув владельцем: draft → approved), `runs`, `items`, `verdicts`, `llm_calls` (трейсинг стоимости). Читают/пишут только модули `importer/build/`; схема экспонирована в PostgREST (Dashboard → API → Exposed schemas).
- `requirements` несёт жизненный цикл (`effective_from` / `transition_until` / `valid_to` / `repealed_by_ref`) и `jurisdiction` (ISO 3166-1 alpha-2). Статус не хранится — вычисляется `public.lifecycle_status()` через вью `requirements_with_status`: `upcoming` / `in_force` / `transitional` / `expiring` / `repealed`. `change_events` тоже несёт `jurisdiction` (страновой webhook, `docs/adr/0005-ecosystem-contracts.md`).

### Мультистрановость витрины

- Коды стран — `src/data/countries.ts` (`CountryCode = 'UZ' | 'KZ' | 'AE'`, порядок = порядок запуска); названия для UI — только `src/i18n/ru.ts`, не здесь.
- Карточка товара — табы по странам (`?country=` в URL, `parseCountryParam` фолбэчит на UZ при пустом/невалидном значении); данные не-UZ страны приходят превью-тизером без юридического слоя до проверки юристом.
- Кнопка «Сравнить страны» на карточке — модалка-матрица категорий по странам (`src/pages/c/product/CCompareMatrix.tsx`), бесплатный тизер без деталей и цитат.

### Календарь дедлайнов (.ics)

- Личный `.ics`-фид: `public.calendar_tokens` (токен → `user_id`) → `GET /api/calendar/<token>.ics` (Vercel serverless function, `api/calendar/[token].ts` + `api/_lib/ics.ts`) читает `user_deadline_events` и строит события `effective_from` / `transition_until` / `valid_to`. `SUPABASE_SERVICE_ROLE_KEY` — только в `process.env` на сервере, файл вне `src/`, в клиентский бандл не попадает.
- Переходы жизненного цикла и напоминания за 7 дней — `pg_cron` (`20260804100000_lifecycle_cron.sql`).
- Мок-подписчик (`ix-mock-subscriber`, без входа) видит на витрине уже «подключённый» календарь на фейковом токене — `CSettingsPage.tsx`, вкладка «Уведомления».

### Прочее

- Все строки UI — в `src/i18n/ru.ts` (единственный источник текста; uz/en позже с тем же контрактом). Не хардкодить текст в компонентах.
- Цена тарифа — `src/config.ts` (не утверждена, менять только там).
- SEO-файлы: `index.html` (метатеги, JSON-LD), `public/` (robots.txt, sitemap.xml, llms.txt, og.png). Канонический домен — `inspectorx.uz` (запасной `inspector-x.uz` — редирект на него в Vercel).

## Документы-источники истины

- `docs/TARGET_FORMAT.md` — ТЗ продукта, контракт данных требования (§4). Технические решения подчиняются ему, а не наоборот.
- `docs/IDEAS.md` — идеи вне MVP; **не кодировать без явного решения**.
- `docs/LAUNCH_CHECKLIST.md` — правило заморозки: в текущий код после запуска добавляется только контент, новые фичи — через TARGET_FORMAT.
- `docs/INFRA_ACCOUNTS.md` — аккаунты, доступы и счета (Supabase, GitHub, Vercel): чей аккаунт, какие ключи живые, какие протухли.
- `docs/adr/0002-ecosystem-topology.md` — топология экосистемы: названия (LegalX / SudX / InspectorX), число баз Supabase, где исполняется Python. При расхождении с другими документами верен ADR.
- `docs/adr/0003-agent-flow.md` — агентский флоу контент-фабрики: контуры Build / Runtime / Monitoring, generic-агенты с профилями, независимый Verifier, порядок конвейера. Детализация — доска в Miro.
- `docs/adr/0004-product-catalog.md` — товарный каталог: `product_types` (HS6 — товары, UNSPSC — услуги), `country_codes` (ИКПУ/ТН ВЭД/ОКЭД…), `skus`; требования привязываются только к типам.
- `docs/adr/0005-ecosystem-contracts.md` — интерфейсы между проектами: `search_norms`, `search_cases`, webhook изменений, версионирование актов в LegalX.
