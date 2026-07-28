# Фаза 2 UZ-first: стадия перевода — план

> **Статус на 29.07.2026:** реализована — код в `main`, PR #8 смержен
> 27.07.2026 (`importer/translator.py`, двуязычный loader, канон в dedup;
> миграция `20260717120000_translation_origin.sql` накатана на прод).
> Оговорка: стадия исправна, но ни разу не сработала на реальных данных —
> вход остаётся русским (`content_lang="ru"`), поэтому в проде
> `translation_origin` не NULL — 0 строк, `lang='uz'` — 0. Оживит её фаза 3.

> По спеке `docs/superpowers/specs/2026-07-16-uz-first-pipeline-design.md` §2.
> Утверждённые рамки: юрцитаты моделью НЕ переводятся никогда; витринные поля
> UZ→RU переводит LLM с глоссарием; признак происхождения — `translation_origin`
> (verbatim | machine); ошибка перевода не блокирует публикацию (UZ-only, честно).

## Задачи

1. **Миграция** `20260717120000_translation_origin.sql` (аддитивная, RLS не трогаем):
   enum `translation_origin` ('verbatim','machine') + nullable-колонка в
   `requirement_contents` и `requirement_details`. Старые строки остаются NULL
   (легаси до фазы 2). Накат: локальная проверка → `supabase db push`.
2. **Модель**: `content_lang: "ru"|"uz" = "ru"` в `_BaseRequirement` — язык
   витринных полей карточки. Сегодняшние DR-отчёты русские → дефолт "ru",
   поведение не меняется. Gap-ресёрчер фазы 3 будет ставить "uz".
3. **`importer/translator.py`**: `translate_card_fields(req, llm) -> dict | None` —
   переводит ТОЛЬКО whitelist полей (title, summary, how_to[].step,
   documents[].name/where, sanction.extra) единым JSON-запросом с глоссарием
   `research-loop/glossary-uz-ru.md`. Юрцитаты в промпт не попадают (негативный
   тест). Ошибка LLM → None (карточка публикуется UZ-only).
4. **Loader**: строки contents/details пишутся с `lang=req.content_lang` и
   `translation_origin='verbatim'`; при content_lang="uz" и наличии перевода —
   дополнительные строки lang="ru" с `translation_origin='machine'`.
5. **Dedup**: merge перестаёт хардкодить lang="ru" — канонической считается
   строка details с origin='verbatim' (легаси NULL при lang="ru" приравнен
   к verbatim); санкции мержатся в каноническую строку.
6. **Шов pipeline/requeue**: при content_lang="uz" перед загрузкой вызывается
   translator (если llm доступна); дедуп-ключ и гейт не меняются.

## Тесты

- translator: перевод по фейк-раннеру; глоссарий в промпте; sentinel юрцитаты
  НЕ в промпте; LLMError → None.
- loader: UZ-карточка + перевод → 2×contents (uz verbatim, ru machine) и
  2×details; RU-карточка → одна строка ru/verbatim (регрессия старого вида).
- dedup: канон = verbatim-строка (и легаси ru/NULL).
- pipeline: UZ-карточка без llm → публикация UZ-only, без падения.

## Вне скоупа (фазы 3–4)

Оркестратор, gap-ресёрчер UZ-first, добивка uz_backfill_needed, аудитор,
переключатель языка на витрине — на 29.07.2026 не начаты.
Backfill старых карточек выполнен раньше плана, 28.07.2026, инструментом
`research-loop/backfill_verbatim_uz.py` (PR #11): `act_paragraphs.verbatim_uz`
заполнен у 75 из 200 параграфов; остаются 7 ненайденных и 118 легаси-ref
из переноса v1.
