# InspectorX v2

Compliance-платформа для Узбекистана: «чек-лист соответствия бизнеса», а не справочник законов.

- **Как работать с репо (главный контекст для агентов):** `CLAUDE.md`
- **ТЗ продукта:** `docs/TARGET_FORMAT.md` (контракт данных требования — §4)
- **Готовность к запуску, правило заморозки:** `docs/LAUNCH_CHECKLIST.md`
- **Статус конвейера данных:** `docs/RESEARCH_PIPELINE_STATUS.md`
- **Идеи вне MVP:** `docs/IDEAS.md` (не кодируем без решения)
- **Исторический контекст:** `docs/SESSION_SUMMARY_2026-07-11.md` (стратегия и план 11.07.2026; в конце — сверка с фактом, что вышло иначе)

## Стек

Vite + React 19 + TypeScript + Tailwind v4 + shadcn/ui (Base UI) · React Router + TanStack Query · Supabase (Postgres, Auth, RLS) · конвейер данных — Python-пакет `importer/` (запускается локально, ключи в `.env.importer`)

## Запуск

```bash
npm install
npm run dev     # Vite dev-сервер, localhost:5173
```

`.env` необязателен: публичные дефолты Supabase (URL + publishable key) зашиты в
`src/lib/supabase.ts`, доступ к данным ограничивает серверный RLS. Копировать
`.env.example` имеет смысл, только если заполняете его реальными ключами (например,
staging), — незаполненные плейсхолдеры перебьют рабочие дефолты и приложение уедет
на несуществующий проект.

Проверки:

```bash
npm run build   # tsc -b && vite build — это же и проверка типов
npm run lint    # oxlint
```

Юнит-тестов на фронте нет. Визуальная проверка — Playwright-скрипты, нужен запущенный
dev-сервер (база переопределяется `SHOT_BASE`):

```bash
node scripts/shot.mjs <path> <name> [steps.mjs]  # shots/<name>-{light,dark}-{1440,375}.png + консольные ошибки
node scripts/walkthrough.mjs                     # сквозной путь: лендинг → поиск → товар → карточка → пейволл → тариф → заявка
```

## База данных

Миграции — в `supabase/migrations/` (схема + RLS + контент). Локальная проверка:

```bash
supabase db start && supabase db reset --local
```

На прод миграции накатываются вручную — SQL-редактором в панели Supabase: CLI залогинен
в другой аккаунт и проект не залинкован, поэтому `supabase db push` не работает.

Ключевые инварианты схемы:

- Единая таблица `requirements`; текст — в `requirement_contents` (бесплатный тизер)
  и `requirement_details` (по подписке) по строке на язык (ru/uz/en).
- Пейволл закрыт на сервере (RLS), граница — на уровне таблиц.
- `flagged_by_change` — флаг поверх `published`: карточка при ре-ревью остаётся на витрине.
- Коды ТН ВЭД/ИКПУ — text; применимость через scope (код / класс-префикс / все товары).
- Уведомления об изменениях: `change_events → requirement_change_impacts → user_notifications`
  (per-user). Схема есть, мониторинг изменений законодательства ещё не построен — таблицы пусты.

## Конвейер данных

`importer/` — Python-пакет, который превращает deep-research-отчёт в карточки требований:
парсинг отчёта → резолв ссылок на акты (lex.uz, JurisBase) → верификация → дедуп → загрузка
в staging-таблицы `import_runs` / `import_items` и далее в `requirements`. Требования, которые
он опубликовал, помечены `origin = 'ai_pipeline'`. CLI: `import-report` (в т.ч. `--dry-run`,
`--no-llm`) и `review list` / `review show` для разбора очереди ревью.

`research-loop/` — инструменты вокруг конвейера: замер прода (`measure_prod.py`), разбор
очереди (`requeue_review.py`, `pass2_*.py`), добивка узбекских цитат (`backfill_verbatim_uz.py`),
сиды, журнал итераций `LOOP-LOG.md` и решения фаундера `DECISIONS.md`.

Окружение (готового venv в репозитории нет — он в `.gitignore`):

```bash
python3 -m venv .venv-importer
.venv-importer/bin/pip install -r importer/requirements.txt
.venv-importer/bin/python -m pytest importer/tests     # 131 тест
```

Ключи — в `.env.importer` (не под гитом), шаблон — `.env.importer.example`:
`IX_SUPABASE_URL`, `IX_SUPABASE_SERVICE_KEY` (service-роль, пишет в БД InspectorX),
`JB_SUPABASE_URL`, `JB_SUPABASE_KEY` (JurisBase, read-only). Прогоны с записью в прод
делает владелец проекта.

Таймлайн трека, решения и текущая точка остановки — `docs/RESEARCH_PIPELINE_STATUS.md`.
