# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

InspectorX v2 — compliance-платформа для Узбекистана: «чек-лист соответствия бизнеса», а не справочник законов. Прод: https://inspectorx.uz (технический адрес деплоя — `inspectorx-v2.vercel.app`, отдаёт ту же сборку; `inspector-x.uz` и `www.inspectorx.uz` → 308 на канонический). Автодеплой `main` через Vercel, SPA-rewrite в `vercel.json`.

Язык проекта — русский: комментарии, строки UI, коммиты (conventional commits по-русски, напр. `feat(landing): …`).

## Команды

```bash
npm run dev        # Vite dev-сервер (localhost:5173)
npm run build      # tsc -b && vite build — это же и проверка типов
npm run lint       # oxlint
```

Юнит-тестов фронта нет (в `package.json` нет скрипта `test`) — тесты есть только у Python-конвейера, см. «Конвейер данных (Python)». Визуальная проверка фронта — Playwright-скрипты (нужен запущенный dev-сервер; база переопределяется `SHOT_BASE`):

```bash
node scripts/shot.mjs <path> <name> [steps.mjs]  # shots/<name>-{light,dark}-{1440,375}.png + консольные ошибки в stdout
node scripts/walkthrough.mjs                     # сквозной путь: лендинг → поиск → товар → карточка → пейволл → тариф → заявка
```

`steps.mjs` (примеры в `scripts/steps/`) экспортирует `default: async (page, ctx) => {}` — действия перед снимком.

### База данных

Миграции — `supabase/migrations/` (схема + RLS + контент + функции и триггеры). Локально:

```bash
supabase db start && supabase db reset --local
```

**Накат на прод — вручную.** CLI не залинкован (в `supabase/.temp/` нет project-ref, `project_id` в `config.toml` — локальный) и залогинен в чужой аккаунт: `supabase db push` / `supabase projects list` падают с «Cannot find project ref», прод-проекта `kcjlrvgjtoefqgzxuizz` в списке нет; Supabase MCP требует авторизации и сейчас недоступен. Порядок: содержимое файла из `supabase/migrations/` выполняется в SQL-редакторе прод-проекта, результат проверяется REST-запросом с service-ключом из `.env.importer` (`GET {url}/rest/v1/<table>?select=<column>`, код 42703 = колонки нет). Так накатаны `20260717120000_translation_origin.sql` и `20260727120000_lead_notifications.sql`. Побочный эффект: строка в `supabase_migrations.schema_migrations` не появляется, история миграций дрейфует. Чтобы вернуть `db push` — `supabase login` под верным аккаунтом + `supabase link --project-ref kcjlrvgjtoefqgzxuizz`.

Генераторы миграций: `scripts/generate_v1_content_migration.mjs` — одноразовый перенос контента из v1, обычно трогать не нужно; `scripts/generate_services_seed.mjs` — сид модуля услуг, им сгенерированы `20260712110000_services_content.sql` и `20260712150000_cafe_content.sql` (правки вносить в генератор, а не в SQL — это указано в шапке обеих миграций).

**Уведомления о заявках** (`20260727120000_lead_notifications.sql`): триггеры `after insert` на `subscription_requests`, `content_requests`, `user_questions` → `public.notify_new_request()` → `public.notify_admin_telegram()` (`security definer`), отправка боту через `pg_net`. Одного наката мало: после него нужно вручную завести секреты `telegram_bot_token` и `telegram_chat_id` через `vault.create_secret` — в репозиторий они не попадают. Без секретов уведомления молча пропускаются (так работает локальная база); отказ отправки никогда не роняет вставку заявки. Дизайн — `docs/superpowers/specs/2026-07-27-lead-notifications-design.md`.

### Конвейер данных (Python)

Кроме фронта в репозитории живут два Python-каталога:

- `importer/` (41 файл под гитом) — конвейер импорта deep-research отчётов в БД: `cli.py`, `pipeline.py`, `parser.py`, `resolver.py`, `verifier.py`, `dedup.py`, `loader.py`, `lexuz.py`, `llm.py`, `translator.py`. Дизайн — `docs/superpowers/specs/2026-07-12-report-importer-design.md` и `2026-07-16-uz-first-pipeline-design.md` (из четырёх фаз UZ-first реализованы 1 и 2, PR #7 и #8); статус — `docs/RESEARCH_PIPELINE_STATUS.md`.
- `research-loop/` (27 файлов) — служебные скрипты прогонов по проду: `measure_prod.py`, `requeue_review.py`, `pass2_*.py`, `backfill_verbatim_uz.py`, плюс журналы `LOOP-LOG.md`, `DECISIONS.md`.

```bash
<venv>/bin/python -m pytest importer/tests -q   # 131 тест, 15 модулей
```

Зависимости — `importer/requirements.txt`; venv (`.venv-importer`) в гит не коммитится, сейчас лежит в `.claude/worktrees/report-importer-impl/`. Реквизиты — `.env.importer` (`IX_SUPABASE_URL` / `IX_SUPABASE_SERVICE_KEY` — service-role, пишет в прод-БД; `JB_*` — read-only); файл под `.gitignore`, шаблон — `.env.importer.example`. Скрипты с `--apply` пишут в прод — запускать только по явному решению владельца проекта.

## Архитектура

Стек: Vite + React 19 + TypeScript + Tailwind v4 + shadcn/ui (Base UI) · React Router · TanStack Query · Supabase (Postgres, Auth, RLS). Алиас `@` → `src/`.

### Маршруты (`src/App.tsx`)

- `/` — `src/pages/landing-b/LandingB.tsx`: лендинг «Один маршрут», самодостаточный (своя шапка/подвал, свой CSS `landing-b.css`).
- Кокпит «Маршрут товара» (дизайн C) под `CLayout`: `/catalog`, `/product/:productId`, `/service/:serviceId`, `/pricing`, `/cabinet`, `/login`, `/register`, `/auth/confirm`, `/auth/reset`, `/forgot-password` и catch-all `*` → `NotFoundPage` — всё в `src/pages/c/`.
- Флоу подтверждения e-mail и восстановления пароля (`/auth/confirm`, `/auth/reset`, `/forgot-password`) требует настройки Site URL и Redirect URLs в панели Supabase — `docs/SUPABASE_AUTH_SETUP.md`.

### Услуги — вторая ось витрины

Наряду с товарами: таблица `services` (`oked_code` — главная ось поиска, `admission_mode` по ЗРУ-701 `license/permit/notification/free`, `authority_id`, `ikpu_code` nullable, `complexity_index`). Паспорт услуги = режим допуска × 6 этапов жизни бизнеса (`svc-01-start` … `svc-06-closure` в `lifecycle_stages`). Применимость требований — по ОКЭД: scope `oked_code` / `oked_prefix` / `all_services`.

Миграции: `20260712100000_services_module.sql` (схема), `20260712110000_services_content.sql` (аптека ОКЭД 47.73), `20260712150000_cafe_content.sql` (кафе ОКЭД 56.10). Формула паспорта — `docs/SERVICES_PASSPORT_PROPOSAL.md`, ресёрч по кафе — `docs/CAFE_RESEARCH.md`, статус — `docs/SERVICES_HANDOFF.md`. Кросс-ссылки товар ↔ услуга (лекарства ↔ аптека, напитки группы 22 → кафе) — `src/data/cross-links.ts`.

### Слой данных (`src/data/`) — главное место, где легко запутаться

Компоненты ходят в данные ТОЛЬКО через React-Query-хуки `src/data/hooks.ts` → публичный API `src/data/index.ts`. Тот композиционно смешивает реальные данные Supabase (`real.ts`) с мок-фикстурами (`mock/`):

- **Сигареты** — живые данные Supabase + мок-оверлей изменений;
- **Молоко** — реальный товар, требования из фикстур;
- **Парацетамол** — полностью мок;
- **Услуги** (`/service/:serviceId`) — только живой Supabase, без мок-оверлея: `searchServicesReal` / `fetchServiceBundle` → `fetchServicePassportReal` / `fetchServiceRequirementsReal` / `fetchServiceDocumentsCountReal`, хук `useServiceBundle`. Метрика `changes30d` для услуг захардкожена нулём — конвейер изменений их не наполнял.

Закрытый RLS контент приходит как `Gated<T>` со статусом `'locked'`; мок-подписчик получает демо-шаблон details. Не обходить `index.ts` прямыми запросами к Supabase из компонентов.

### Пейволл — закрыт на сервере

Граница подписки — на уровне таблиц RLS: `requirement_contents` (бесплатный тизер) читают все, `requirement_details` — только при `profiles.is_subscribed`. Клиент не может включить подписку себе; активация — вручную админом. Дефолтные URL/publishable key Supabase зашиты в `src/lib/supabase.ts` — это публичные реквизиты, безопасность держит RLS; `.env` может их переопределить.

Dev-тумблер «я подписчик» (`src/app/app-mode.tsx`, localStorage `ix-mock-subscriber`) показывает вид подписчика на моках — не путать с реальной подпиской из `profiles`.

### Ключевые инварианты схемы

- Единая таблица `requirements`; текст — в `requirement_contents` / `requirement_details` по строке на язык (ru/uz/en).
- `flagged_by_change` — флаг поверх `published`: карточка при ре-ревью остаётся на витрине.
- Коды ТН ВЭД/ИКПУ/ОКЭД — text; применимость через `requirement_applicability.scope` — 8 значений: точный код (`hs_code`, `ikpu_code`, `oked_code`), класс-префикс (`hs_prefix`, `ikpu_prefix`, `oked_prefix`), все товары (`all_products`), все услуги (`all_services`).
- Уведомления об изменениях законодательства: `change_events → requirement_change_impacts → user_notifications` (per-user) — это **целевая схема, а не работающий механизм**. Таблицы существуют только как DDL+RLS, кода-писателя нет (ни Edge Functions, ни `importer/`, ни `research-loop/` в них не пишут), на проде все три пусты. Приложение цепочку не читает: лента изменений в кабинете строится из мок-фикстур (`src/data/index.ts` → `changeFixtures`). Не путать с уведомлениями о заявках — те работают, см. «База данных».

### Прочее

- Строки UI кокпита — в `src/i18n/ru.ts` (единственный источник текста; uz/en позже с тем же контрактом). Новый текст — туда же, не хардкодить в компонентах. Исключения, где текст пока зашит: лендинг `src/pages/landing-b/` целиком (`ru.ts` не импортирует вовсе; секция `landing` в `ru.ts` используется не лендингом, а `CCatalogPage`), плюс точечно `CCabinetPage` (подписи метрик и формы склонений), `CCatalogPage`, `CLayout`, `CAuthPage`, `CRouteNav`, `CProductPage`, `CPricingPage`, `AskQuestionDialog`, `NotFoundPage`.
- Цена тарифа — `src/config.ts` (`PRICE`, не утверждена), но `PRICE` читается только на `/pricing` (`CPricingPage.tsx`). Та же цена продублирована текстом ещё в 7 местах: `LandingB.tsx:33` и `:394`, `index.html` (JSON-LD Offer + FAQ + подвал, 4 места), `public/llms.txt`. При изменении править все, а не только `config.ts`.
- SEO-файлы: `index.html` (метатеги, JSON-LD), `public/` (robots.txt, sitemap.xml, llms.txt, og.png). Канонический домен — `inspectorx.uz` (запасной `inspector-x.uz` — редирект на него в Vercel).

## Git

- Репозиторий `TAVI-Agency/inspectorx-v2` виден только одному из залогиненных gh-аккаунтов: перед любыми `gh`-командами и push — `gh auth switch -u TAVI-Agency`, иначе push падает с «Repository not found».
- Автор коммита — из `git config` репозитория (`TAVI-Agency <218367066+TAVI-Agency@users.noreply.github.com>`). Не переопределять `-c user.email`: с посторонним адресом Vercel не собирает превью — проверка падает с «GitHub couldn't verify an account for the commit» (наблюдалось в PR #10 29.07, лечится переподписью коммитов).
- Работа — ветка на задачу + PR в `main`, прямо в `main` не коммитить.
- Рабочие worktree лежат в `.claude/worktrees/`; сам каталог `.claude/` выведен из-под гита (`.gitignore`) — там же локальный venv конвейера.

## Документы-источники истины

- `docs/TARGET_FORMAT.md` — ТЗ продукта, контракт данных требования (§4). Технические решения подчиняются ему, а не наоборот.
- `docs/IDEAS.md` — идеи вне MVP; **не кодировать без явного решения**.
- `docs/LAUNCH_CHECKLIST.md` — правило заморозки: в текущий код после запуска добавляется только контент, новые фичи — через TARGET_FORMAT.
- `docs/superpowers/specs/` — утверждённые дизайны подсистем (auth-флоу e-mail, импортёр DR-отчётов, UZ-first конвейер, уведомления о заявках), `docs/superpowers/plans/` — планы их реализации. Перед правкой подсистемы читать её спеку; спеки фиксируют принятые решения, а не статус реализации (например, в UZ-first описаны 4 фазы, реализованы 1 и 2).
