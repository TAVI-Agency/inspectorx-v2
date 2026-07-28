# Импортёр deep-research отчётов → БД Inspector X — дизайн

> Утверждён 12.07.2026 (брейншторм-сессия Claude Code, продолжение сессии Cowork).
> Контекст: `~/PycharmProjects/inspectorx/docs/e2e-pipeline-design.md`,
> промпты: `docs/research-prompt-product.md`, `docs/research-prompt-service.md` (там же).
> Архитектурные решения хендоффа (дедуп от акта, scope, lifecycle, UZ-канон) — не нарушать.
>
> **Статус на 29.07.2026:** реализовано — код конвейера `importer/` в `main`
> (PR #7 смержен 17.07.2026; сама спека и план — PR #5, 12.07.2026).
> **Частично заменено:** п.4 верификационного гейта и «UZ-ветка гейта» из
> «Вне скоупа v1» отменены спекой `docs/superpowers/specs/2026-07-16-uz-first-pipeline-design.md`
> (UZ-канон penalty 1.0 / RU-сверка 0.95, причина review `uz_version_not_found`) —
> реализованы в фазах 1–2. Остальные разделы в силе.

## Задача

Временная архитектура (1–2 месяца): каталог топ-30–60 товаров/услуг наполняется отчётами
deep research внешних ИИ (ChatGPT/Gemini/Claude). Каждый отчёт = читаемая часть + JSON-блок
(схема в промпте) + «серые зоны». Импортёр — конвейер «отчёт → проверенные карточки в БД».
Прямая заливка JSON в БД запрещена: между отчётом и БД стоит верификационный гейт.

## Принятые в сессии решения

| Вопрос | Решение |
|---|---|
| Стек и место | Python-пакет `importer/` в репо `inspector-x-final` (Pydantic — решение брейншторма; рядом со схемой БД) |
| Review-очередь | Таблица в Supabase Inspector X (`import_items` со статусом `review`), не админка JurisBase |
| Гейт v1 при пустых `act_paragraphs` JurisBase | Прямой fetch страниц lex.uz + fuzzy-match цитат; переход на канонические юниты JurisBase — когда backfill наполнит таблицы |
| LLM-шаги | `claude -p` (headless CLI по подписке) через абстракцию `importer/llm.py`; позже возможен переход на Anthropic API |
| Архитектура | Вариант A: CLI-пайплайн со staging-таблицами (`import_runs`/`import_items`) — аудит + review-очередь + золотой датасет в одном слое |
| Публикация | Прошла гейт → сразу `status='published'` на витрине с `trust_label='validated'` («проверено ИИ», не юристом). Ручного шлюза нет; при необходимости меняется одной константой на `draft` |
| Тестовые данные | 3 готовых отчёта (цемент, ЛКМ — Claude; чашка — GPT) Абдурахмон кладёт в `research/incoming/`. Отладка на них до массового прогона 57 |

## Архитектура и поток данных

```
research/incoming/{product|service}--{слаг}--{модель}.md
        │  python -m importer import-report <file>
        ▼
[1 Parse]    извлечь JSON-блок → Pydantic-валидация
             └─ невалидно → claude -p конвертирует в схему → повторная валидация → нет → run failed
[2 Resolve]  каждый act.lexuz_url → JurisBase.acts (нет → очередь загрузки) + upsert в IX.acts
[3 Verify]   гейт: акт действует / редакция / ссылка жива / пункт найден / цитата сошлась
[4 Dedup]    нормализованный ключ акт+пункт → поиск по ВСЕЙ базе → merge или новое требование
[5 Load]     requirements + contents + details + citations + applicability;
             провал гейта → import_items(status='review', reason)
[6 Post]     пересчёт derived-метрик; «серые зоны» → бэклог «прохода 2»
```

Модули: `importer/models.py` (Pydantic-схема отчёта), `parser.py`, `resolver.py`,
`verifier.py`, `dedup.py`, `loader.py`, `llm.py`, `cli.py`.

Подключения: Supabase Inspector X (чтение+запись), Supabase JurisBase `lexportal`
(только чтение `acts`/`act_versions`; гейт готовности: `is_stub = false AND status = 'published'`).

Идемпотентность: повторный прогон файла не создаёт дублей — файл хэшируется,
items апсертятся по `(file_hash, idx)`, требования — по `external_key`.

Детерминизм — в валидации, не в парсинге: LLM можно звать для конвертации формата и
спорной сверки смысла, но решения «в БД / в review» принимают детерминированные правила.

## Модель данных (одна миграция)

Новые таблицы:

- **`import_runs`** — прогон одного файла: `id`, `file_name`, `file_hash unique`,
  `subject_kind` (product/service), `subject_slug`, `model` (gpt/gemini/claude),
  `status` (parsed/failed/loaded), счётчики (loaded/merged/review), `raw_json`,
  `gray_zones text[]`, `created_at`.
- **`import_items`** — требование из отчёта: `id`, `run_id`, `idx`, `raw jsonb`,
  `status` (`loaded`/`merged`/`review`/`rejected`), `review_reason`
  (код: `act_not_found`, `unit_not_found`, `quote_mismatch`, `uz_only_act`,
  `no_dictionary_slot`, `cross_model_conflict`, `needs_review_from_report`, ...),
  `requirement_id` (nullable FK), `resolution` (`pending`/`approved`/`fixed`/`rejected`),
  `resolved_by`, `resolved_at`. Это одновременно review-очередь и золотой датасет решений.
- **`requirement_sources`** — `requirement_id` × `import_item_id`: провенанс
  «какие модели/отчёты нашли требование»; при merge добавляется строка.

Изменение enum: `trust_label` + значение `'validated'`
(lifecycle `ai_draft → validated → lawyer_verified`; `official_answer` остаётся).

Маппинг полей отчёта → существующая схема:

| Отчёт | БД |
|---|---|
| `title`, `summary` | `requirement_contents` (lang='ru') |
| `how_to`, `documents`, `sanction` | `requirement_details.how_to_comply/documents/sanctions` (jsonb, форма совпадает) |
| `act` + `unit` | `acts` / `act_paragraphs` + `requirement_citations` |
| `scope` | `requirement_applicability` |
| `nature` | `deontic` |
| `type` | `operation_domain` |
| `addressees` | `addressee_roles` (`party_role[]`) |
| `agency` | `authorities` (lookup по имени; нет в словаре → review) |
| `category` | тег `requirement_category` (закрытый список) |
| `legal_quote_ru` | `act_paragraphs.verbatim_ru` |

Классификация — только в закрытые словари; нет полки → review, словари автоматически
не расширяются.

Субъект отчёта: паспорт продукта (`product.hs_code`, `ikpu`, ставки) → upsert в `products`
по `hs_code` (услуги — в `services` по ОКЭД). Если субъект уже есть — метаданные
не перезаписываются, только дополняются пустые поля.

## Верификационный гейт (v1)

Проверки по порядку; провал → item в review с кодом причины, в основные таблицы не пишем:

1. **Акт резолвится.** Нормализация `lexuz_url` (`/docs/-{id}`, языковые префиксы) → doc_id.
   Поиск в JurisBase `acts`; найден и готов → метаданные оттуда. Не найден → запись в
   очередь загрузки `importer/act_queue.jsonl` (ТЗ для скрейпера JurisBase), гейт продолжает
   работу по прямому fetch. Резолвятся ВСЕ ссылки карточки, включая `how_to[].source_act_url`
   и `sanction.url` — их провал карточку не блокирует, а помечает соответствующее поле.
2. **Ссылка жива, акт действует.** Fetch страницы lex.uz с дисковым кэшем (per doc_id + дата),
   чтобы 60 отчётов не долбили lex.uz повторно. 404 / «утратил силу» → review.
3. **Пункт существует.** Парсер `unit` («ст. 14», «п. 11», «прил. 2, строка 91») →
   канонический ref (`art.14`, `p.11`, `app2/row91`), совместимый с адресами JurisBase
   `act:{id}/para:{ref}`. Пункт ищется в HTML акта.
4. **Цитата сходится.** Есть официальный RU → fuzzy match `legal_quote_ru` против текста
   пункта (rapidfuzz): ≥85 — ок; <60 — review; между — `claude -p` отвечает «тот же смысл?».
   Акт только UZ → в v1 сразу review с причиной `uz_only_act` (UZ-ветка с переводом по
   пайплайну JurisBase — вторая итерация). На витрине для UZ-актов юридический слой позже
   показывает UZ-оригинал + наш перевод, НЕ цитату рисерча.

   > **Заменено 16.07.2026** спекой `docs/superpowers/specs/2026-07-16-uz-first-pipeline-design.md`
   > (§«UZ-канонизация гейта и лоадера»), реализовано в фазе 1 — `importer/verifier.py`:
   > канон — fuzzy-match `legal_quote_uz` против **узбекской** страницы акта (её doc_id
   > ищется по языковым ссылкам RU-страницы), penalty 1.0; UZ-версия не найдена → review
   > `uz_version_not_found`; RU-цитата против RU-страницы — переходный режим, penalty 0.95
   > + флаг `uz_backfill_needed`; `uz_only_act` сохранён, но срабатывает только когда
   > официального RU-текста нет И `legal_quote_uz` не передана. Перевод витринных полей
   > UZ→RU делает `importer/translator.py` (фаза 2, PR #8), а не «пайплайн JurisBase»;
   > юридические цитаты в промпт перевода не попадают никогда.
5. `needs_review: true` из отчёта → сразу review без прогона гейта.

## Дедуп и merge (глобальный, по ключу акт+пункт)

- Ключ: `(canonical_act, canonical_unit_ref)` первичной цитаты →
  `requirements.external_key` = `lexuz:{doc_id}/{ref}`.
- Поиск по всей базе, включая ручные карточки услуг (у них те же citations).
- Совпал ключ → **merge**: scope расширяется (`this_code`+`this_code` → `hs_list`
  с объединёнными кодами; `domain`/`all` поглощают более узкое), в `requirement_sources`
  добавляется источник. Контент существующей карточки не перезаписывается.
- Конфликт данных на одном ключе (разные санкции/сроки) → review `cross_model_conflict`.
  Исключение: два слоя санкций (КоАО + отраслевой закон, напр. ст. 46 ЗРУ-819) —
  не конфликт, а объединение списка sanctions.
- Требование с несколькими пунктами: первичная цитата = ключ дедупа, остальные — в citations.
- Сомнение в склейке («ст. 14» vs «п. 14», fuzzy-совпадение) → review:
  ложная склейка хуже дубля.

## Статусы и жизненный цикл

- Гейт пройден → `requirements`: `status='published'`, `trust_label='validated'`,
  `origin='ai_pipeline'`, `confidence_score` из качества матча цитаты.
- Merge с существующим → item `merged`.
- Провал гейта / конфликт / `needs_review` → item `review` (на витрину не попадает).
- Сброс `lawyer_verified → validated` при изменении опорного пункта — механизм
  `review_flag`/`change_events`, импортёр его не трогает. Уточнение на 29.07.2026:
  «существующий» здесь означает только схему БД — производителя данных нет,
  `change_events` в проде пуста (0 строк), сброс фактически не срабатывает.

## CLI

- `import-report <file>` — идемпотентный прогон одного отчёта;
- `import-report --dry-run` — полный прогон с отчётом в консоль, без записи в БД;
- `review list` / `review show <item>` — просмотр review-очереди из терминала
  (UI в витрине — позже, при необходимости).

## Обработка ошибок

- Невалидный JSON после LLM-конвертации → `import_runs.status='failed'`, ничего не пишем.
- Сетевые ошибки lex.uz → ретраи с бэкоффом; стойкий провал → item в review
  (`lexuz_unreachable`), прогон не падает целиком.
- Ошибка на одном item не прерывает остальные: каждый item завершает прогон
  в одном из статусов.

## Тестирование

- pytest; юнит-тесты на парсер unit-ref и нормализацию lex.uz-URL
  (таблица примеров из реальных отчётов).
- Фикстуры: 3 реальных отчёта + синтетический «кривой» (сломанный JSON, межмодельный
  конфликт, UZ-акт, needs_review).
- Fetch lex.uz в тестах замокан сохранёнными HTML-страницами.
- Интеграционный smoke: `--dry-run` на реальном отчёте против прод-БД (только чтение).
- Порядок внедрения: отладить на 3 отчётах → массовый прогон 57.

## Вне скоупа v1 (вторая итерация)

- ~~UZ-ветка гейта (поиск пункта в UZ-каноне, перевод, сверка по смыслу).~~
  **Сделано:** вынесено в спеку `docs/superpowers/specs/2026-07-16-uz-first-pipeline-design.md`
  и реализовано фазами 1–2 (PR #7 от 17.07.2026, PR #8 от 27.07.2026).
- Переход гейта на `act_paragraphs`/`change_feed` JurisBase (после backfill).
- Иерархичное покрытие ТН ВЭД в scope (нужен дамп дерева кодов).
- UI review-очереди в витрине.
- Фазы 1–2 мониторинга изменений законодательства (мониторинг diff по пунктам,
  ночная джоба по новым нормам) — нумерация из внешнего документа
  `~/PycharmProjects/inspectorx/docs/e2e-pipeline-design.md` (Фаза 0 — bootstrap,
  Фаза 1 — diff, Фаза 2 — новые нормы); **не путать** с фазами 1–4 конвейера
  UZ-first. На 29.07.2026 слой изменений не построен: в проде `change_events`,
  `requirement_change_impacts`, `user_notifications` — по 0 строк, спеки и плана
  в `docs/superpowers/` нет.

## Метрики с первого дня

Счётчики прогона: сколько карточек loaded/merged/review, распределение причин review,
доля подтверждённых цитат по моделям (GPT vs Claude vs Gemini) — это и есть метрики
пропускной способности и качества, заявленные в хендоффе.

## Результаты первого прогона (12.07.2026, 4 отчёта Claude Research)

| Отчёт | loaded | merged | review | топ причин review |
|---|---|---|---|---|
| product--cement--claude.md | 0 | 0 | 12 | needs_review_from_report ×12 (модель сама: UZ-only приложения ПКМ-43) |
| product--electric-car--claude.md | 2 | 0 | 8 | needs_review ×6, quote_mismatch ×2 |
| product--lkm--claude.md | 0 | 0 | 10 | needs_review ×8, quote_mismatch ×1, act_repealed ×1 |
| product--tyre--claude.md | 1 | 0 | 10 | needs_review ×7, lexuz_unreachable ×2, quote_mismatch ×1 |

**Итого: 3 карточки `published/validated`** (conf 0.90 / 0.66 / 0.61 — две спорные подтвердил
`claude -p` через same_meaning), **40 items в review-очереди**, 3 акта в `research/act_queue.jsonl`.
Идемпотентность подтверждена на проде: повторный прогон electric-car → `loaded=0 merged=2`, дублей
`external_key` нет.

Калибровка по живым отчётам (закоммичена):
- **lex.uz: `/docs/-N` и `/docs/N` — РАЗНЫЕ документы**; знак стал частью doc_id (иначе половина актов 404).
- unit-форматы: «прил. № 1, п. 5 (гл. 3)», диапазоны «прил. №1–3», составные «ст. 4; гл. 3» /
  «ст. 254, ст. 258» (берём первый распознанный сегмент — привязку решает гейт сверкой цитаты).
- Терпимость к данным моделей: `ikpu=[null]`, `documents=[{name:null}]`, `hs_code="8703 80"` /
  `"4011 (4011 10 — …)"` → нормализация до цифр (constraint БД `^[0-9]{2,10}$`), адресаты по-русски
  («продавец», «импортёр», …).

Наблюдения по качеству: Claude Research честно ставит `needs_review: true` там, где не смог
процитировать первоисточник (33 из 43 требований) — гейт это уважает и в БД не пускает; собственно
гейт отсёк ещё 7 (цитата не бьётся / акт утратил силу / 404). Пропускная способность v1 без
дозаполнения отчётов: ~7% в автомат, остальное — сырьё для review-очереди.
