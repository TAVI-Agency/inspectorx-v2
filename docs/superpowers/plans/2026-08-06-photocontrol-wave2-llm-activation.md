# Волна 2 — включение LLM-контуров (фотоконтроль + Build + мониторинг) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В день появления живых API-ключей включить все LLM-контуры поверх детерминированного ядра Волны 1: VLM-слой фотоконтроля (кропы, привратник, переспрос, деградация), живые раннеры Build-конвейера и мониторинга (Claude API), Rule-maker как генератор PR-кандидатов, контрольные прогоны на золотом наборе и сквозной смоук.

**Architecture:** Два репозитория. `inspectorx-vision` — движок фотоконтроля: VLM-экстракторы (`src/ixvision/engines/extractor.py`), пайплайн (`src/ixvision/pipeline.py`), детерминированный судья (`engines/rule_engine.py`), локальный чтец (`vision/ocr.py`). `inspector-x-final` — витрина + Build-конвейер (`importer/build/`, CLI `importer/cli.py`) + мониторинг (`importer/monitoring/`). LLM-вызовы Build/мониторинга идут через инжектируемый runner `(prompt, model) -> str | tuple[str, dict]` (`importer/build/llm_client.py:RunnerAgentLLM`) — Волна 2 заменяет три заглушки в `importer/cli.py` одним живым Claude-раннером. VLM фотоконтроля — Gemini flash-lite (основной) + gpt-4.1-mini (резерв), за фича-флагом `extraction.vlm` в `config/routing.yaml`.

**Tech Stack:** Python 3.12 (venv `.venv-importer` в inspector-x-final, `.venv` в inspectorx-vision), pytest, Supabase (локальный для проверок), Anthropic SDK (`anthropic`), httpx (Gemini), openai SDK (резерв VLM), pydantic.

**Суммарный бюджет живых вызовов Волны 2: ≈ $3.30, жёсткий потолок $5.**

| Статья | Задача | Оценка | Потолок |
|---|---|---|---|
| Первый живой прогон VLM + контрольный bench (запись паспортов) | 6 | $0.05 | `IXV_VLM_MAX_CALLS=80` |
| Воспроизводимость: 20 живых прогонов одной серии | 7 | $0.06 | $0.20 (спека §8), `IXV_VLM_MAX_CALLS=140` |
| Тест резервного провайдера (2-3 вызова gpt-4.1-mini) | 6 | $0.06 | суточный потолок `IXV_VLM_FALLBACK_DAILY_MAX` |
| Cartographer: `build map` группы 2204 (expensive-тир) | 11 | $0.40 | `IMPORTER_LLM_MAX_CALLS=60` на команду |
| `build run --no-publish` (3 айтема × 14 шагов + Verifier) | 11 | $1.20 | контроль `build cost`, стоп при > $2 |
| `eval-golden --live` (5 + 20 айтемов) | 11 | $1.10 | `--limit 5` сначала |
| Мониторинг: process-changes + discovery на тестовых событиях | 12 | $0.30 | `IMPORTER_LLM_MAX_CALLS=40` |
| Rule-maker кандидаты + живой веб-поиск samples | 10, 11 | $0.10 | max_uses=3 на запрос |
| Смоук полного контура (1 фотопрогон + 1 макет) | 13 | $0.02 | макет = $0 по построению |

## Global Constraints

- **Правка YAML-пакетов инвалидирует VLM-кэш** (`data/vlm_cache/facts/` — ключ кэша включает подпись схемы): живые прогоны после правок пересчитывают всё и бюджет утекает. Порядок жёсткий: сначала фиксируются пакеты `config/requirements/*.yaml` и `config/policy.yaml` (задачи 1–5, ни одного живого вызова), потом гоняются живые прогоны (задачи 6–7). Перед каждым живым прогоном: `git -C ~/inspectorx-vision status --porcelain config/` обязан быть пустым.
- **`runs/vlm_calls.json` — неатомарный read-modify-write** (`extractor.py:_CallBudget`). Вторая реплика воркера на Railway ЗАПРЕЩЕНА до переноса счётчика в `photo_model_calls`. Волна 2 не масштабирует воркер.
- **Лимиты трат в консолях провайдеров выставляет владелец ДО первого живого прогона** (ADR-0002 решение 4). Это гейт в Задаче 1 с пометкой «требует владельца» — без подтверждения задачи 6+ не стартуют.
- **Писать в прод-БД InspectorX агенту запрещено классификатором.** Все проверки в этом плане — через локальный Supabase (`supabase db start && supabase db reset --local`) и синтетические/локальные прогоны. Прод-шаги оформлены как инструкции владельцу с готовыми SQL-сниппетами (Задача 13).
- **Не ослаблять `config/policy.yaml` ради красивых цифр** (§6 нормативного плана): `absence_requires_reader: strict` и пороги не трогаются ни в одной задаче. Гейты `missed_as_pass=0` и `unsupported_decision=0` обязаны держаться на живых ответах — падение гейта = разбор, не правка политики.
- Язык: комментарии/строки — русский, код и идентификаторы — английские, коммиты — conventional по-русски (`feat(vision): …`, `feat(importer): …`).
- Тесты не ходят в сеть (правило обоих репозиториев): живые провайдеры в тестах подменяются скриптованными фейками; живые вызовы — только в явных шагах «живой прогон» с указанным потолком.
- Модели Claude API (решение Волны 2, см. Задачу 8): cheap → `claude-haiku-4-5` ($1/$5 за MTok), mid → `claude-sonnet-5` ($3/$15), expensive → `claude-opus-5` ($5/$25). Ключ — стандартный `ANTHROPIC_API_KEY` (SDK читает сам), кладётся в `/Users/abduraxmonturdiyev/inspector-x-final/.env.importer`.
- Ключи VLM (фактические имена из `~/inspectorx-vision/src/ixvision/env.py`): Gemini — `GEMINI_API_KEY` (либо `GOOGLE_API_KEY`), OpenAI — `OPENAI_API_KEY` (принимаются также `OPEN_AI_API_KEY`, `OPENAI_KEY`). Кладутся в `~/inspectorx-vision/.env`. Потолок вызовов — `IXV_VLM_MAX_CALLS` (уже читается `_CallBudget`).
- Пути репозиториев: витрина `/Users/abduraxmonturdiyev/inspector-x-final`, движок `/Users/abduraxmonturdiyev/inspectorx-vision`. Python витрины: `.venv-importer/bin/python`. CLI движка: `./ix` (сам находит venv).

---

### Task 1: Санитарный чек Волны 1 — гейт всей сессии

Исполняемый список проверок, что детерминированное ядро на месте. **Любой упавший чек = сессия Волны 2 не стартует**: результат чека возвращается владельцу/сессии Волны 1, ни одна следующая задача не начинается.

**Files:**
- Не создаёт и не меняет файлов (только чтение и запуск).

**Interfaces:**
- Consumes: артефакты Волны 1 — CI обоих репозиториев, гейты bench, воркер с эндпоинтами `/internal/inspect`, `/internal/rejudge`, миграции `photo_runtime`/`photo_storage`, Vercel-функции `api/vision/*`, фича-флаг VLM.
- Produces: подтверждение «ядро на месте» + фактическое имя фича-флага VLM (нужно Задаче 2).

- [ ] **Step 1: Волна 1 смержена в main обоих репозиториев**

Run:
```bash
cd /Users/abduraxmonturdiyev/inspectorx-vision && git log --oneline -3 main && \
  ls .github/workflows/ci.yml scripts/lint_params.py tests/scenarios/ 2>&1
cd /Users/abduraxmonturdiyev/inspector-x-final && \
  ls .github/workflows/ci.yml supabase/migrations/ | grep -E "ci.yml|photo" 2>&1
```
Expected: в vision есть `.github/workflows/ci.yml`, `scripts/lint_params.py`, `tests/scenarios/` (этап 1 фотоконтроля); в витрине есть `ci.yml` и миграции вида `*_photo_runtime.sql`, `*_photo_storage.sql`. Если чего-то нет — проверить неслитые ветки (`git branch -a | grep photocontrol`) и ОСТАНОВИТЬСЯ: мёрж Волны 1 — предусловие.

- [ ] **Step 2: тесты и гейты ядра зелёные без сети**

Run:
```bash
cd /Users/abduraxmonturdiyev/inspectorx-vision && ./ix test -q && \
  ./ix bench --assert missed_as_pass=0 --assert unsupported_decision=0
cd /Users/abduraxmonturdiyev/inspector-x-final && .venv-importer/bin/python -m pytest importer/tests -q
```
Expected: pytest обоих репо PASS (в витрине ~570+ тестов, integration скипаются без локального Supabase); bench на кэшированных паспортах проходит оба ассерта с кодом 0.

- [ ] **Step 3: воркер и мост Волны 1 на месте**

Run:
```bash
grep -n "internal/inspect\|internal/rejudge\|api/vision/ruleset" \
  /Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/server.py | head
ls /Users/abduraxmonturdiyev/inspector-x-final/api/vision/ 2>&1
grep -rn "request_photo_inspection\|finalize_photo_inspection\|photo_model_calls" \
  /Users/abduraxmonturdiyev/inspector-x-final/supabase/migrations/ | cut -d: -f1 | sort -u
```
Expected: в `server.py` есть оба internal-эндпоинта; в `api/vision/` лежат `check.ts`, `checklist.ts`, `progress.ts`, `ruleset.ts`; миграции определяют RPC `request_photo_inspection`, `finalize_photo_inspection` и таблицу `photo_model_calls`. Записать фактические имена файлов миграций — Задачи 3 и 13 их читают.

- [ ] **Step 4: фича-флаг VLM и его фактическое имя**

Run:
```bash
grep -rn "vlm" /Users/abduraxmonturdiyev/inspectorx-vision/config/routing.yaml
grep -rn "vlm_enabled\|extraction.vlm\|IXV_VLM_ENABLED" \
  /Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/pipeline.py | head -5
```
Expected: Волна 1 оставила VLM-слой за выключателем. Записать фактическое имя ключа. Канон этого плана — `extraction.vlm` в `config/routing.yaml`; если Волна 1 назвала иначе, Задача 2 Step 1 переименовывает к канону (одним коммитом, grep по всем вхождениям). Если флага нет вовсе — Задача 2 его создаёт.

- [ ] **Step 5: ключи в окружении**

Run:
```bash
cd /Users/abduraxmonturdiyev/inspectorx-vision && \
  ./.venv/bin/python -c "from ixvision import env; print('gemini:', bool(env.gemini_key()), 'openai:', bool(env.openai_key()))" 2>/dev/null \
  || PYTHONPATH=src python3 -c "from ixvision import env; print('gemini:', bool(env.gemini_key()), 'openai:', bool(env.openai_key()))"
grep -c "^ANTHROPIC_API_KEY=" /Users/abduraxmonturdiyev/inspector-x-final/.env.importer
```
Expected: `gemini: True openai: True` и `1` (ключ Anthropic в `.env.importer`). Ключи НЕ печатать. Если какого-то нет — запросить у владельца, без ключей стоят задачи 6+ (Gemini/OpenAI) и 8+ (Anthropic).

- [ ] **Step 6 (ТРЕБУЕТ ВЛАДЕЛЬЦА): лимиты трат в консолях провайдеров**

Запросить у владельца явное подтверждение (да/нет на каждый пункт): (1) в Google AI Studio выставлен бюджет/квота на ключ Gemini; (2) в консоли OpenAI выставлен monthly budget limit ≤ $10; (3) в консоли Anthropic выставлен spend limit ≤ $20; (4) лимит Railway на проект `inspectorx-workers` установлен. Это ADR-0002 решение 4 — предохранитель ДО первого живого прогона. Без «да» по всем четырём — задачи 6, 7, 11, 12, 13 не стартуют (задачи 2–5, 8–10 без сети — можно делать).

- [ ] **Step 7: локальный Supabase поднимается**

Run: `cd /Users/abduraxmonturdiyev/inspector-x-final && supabase db start && supabase db reset --local`
Expected: reset проходит, все миграции (включая photo_runtime/photo_storage Волны 1) накатываются без ошибок. Нужен задачам 11–13.

---

### Task 2: Vision — конфигурация: флаг VLM, каталог кэша, суточный потолок резерва

**Files:**
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/config/routing.yaml`
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/pipeline.py` (рядом с `reader_settings()`, строки ~145–168)
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/engines/extractor.py` (`CachedExtractor.__init__`, `_CallBudget`, `make_extractor`)
- Test: `/Users/abduraxmonturdiyev/inspectorx-vision/tests/test_vlm_config.py` (новый)

**Interfaces:**
- Consumes: `pipeline.extraction_config()` (кэш словаря `routing.yaml:extraction`, сброс в тестах через `pipeline._extraction_cfg_cache = None`), `env.get(name)` из `ixvision/env.py`.
- Produces: `pipeline.vlm_enabled() -> bool`; `extractor.DisabledExtractor` (провайдер `"off"` в `make_extractor`); `extractor._DailyCap` c методом `try_reserve() -> bool` (файл `runs/fallback_calls.json`, env `IXV_VLM_FALLBACK_DAILY_MAX`, дефолт 40); `CachedExtractor` читает `IXV_VLM_CACHE_DIR`. Задача 3 использует `_DailyCap`; задачи 6–7 — `IXV_VLM_CACHE_DIR`.

- [ ] **Step 1: нормализовать имя флага к канону `extraction.vlm`**

Если Задача 1 Step 4 нашла другое имя — переименовать все вхождения (grep по `src/`, `config/`, `tests/`) в `extraction.vlm`; если флага нет — добавить в `config/routing.yaml` в узел `extraction:`:

```yaml
  # ВЫКЛЮЧАТЕЛЬ VLM (Волна 1 оставила слой за выключателем; Волна 2 включает).
  #   vlm: false — модель не вызывается вовсе: паспорт получает пустого
  #                экстрактора с объяснением в errors, вердикт остаётся,
  #                решения выносят только детерминированные источники.
  #   vlm: true  — живые вызовы по флагу провайдера (см. providers выше).
  vlm: false
```

- [ ] **Step 2: написать падающий тест**

```python
"""Тесты конфигурации VLM-слоя: флаг, каталог кэша, суточный потолок резерва."""
import json

from ixvision import pipeline
from ixvision.engines import extractor as ex
from ixvision.facts import FactSchema


def test_vlm_disabled_by_default(monkeypatch, tmp_path):
    routing = tmp_path / "routing.yaml"
    routing.write_text("extraction:\n  vlm: false\n", encoding="utf-8")
    monkeypatch.setattr(pipeline, "ROUTING_PATH", routing)
    pipeline._extraction_cfg_cache = None
    assert pipeline.vlm_enabled() is False


def test_off_extractor_says_why():
    off = ex.make_extractor("off")
    passport = off.extract(FactSchema(), None)
    assert passport.extraction.calls == 0
    assert any("выключен" in e for e in passport.extraction.errors)


def test_daily_cap_counts_per_day(tmp_path):
    cap = ex._DailyCap(path=tmp_path / "fallback.json", max_calls=2)
    assert cap.try_reserve() and cap.try_reserve()
    assert not cap.try_reserve()
    state = json.loads((tmp_path / "fallback.json").read_text(encoding="utf-8"))
    assert state["used"] == 2 and "date" in state


def test_cache_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("IXV_VLM_MAX_CALLS", "5")
    monkeypatch.setenv("IXV_VLM_CACHE_DIR", str(tmp_path / "live"))
    import ixvision.env as env_mod
    env_mod._cache = None  # env.py кэширует окружение на процесс
    cached = ex.CachedExtractor(ex.StubExtractor({}))
    assert str(cached.cache_dir) == str(tmp_path / "live")
    env_mod._cache = None
```

Примечание к тестам задач 2–5: точные сигнатуры конструкторов `FactSchema` / `FactShard` / `FactSlot` сверить с `src/ixvision/facts.py` (`grep -n "class FactSchema\|class FactShard\|class FactSlot" -A 8 src/ixvision/facts.py`) и поправить вызовы в тестах под фактические (смысл тестов не менять; например, если `FactSchema()` требует `shards=[]` — передать явно).

- [ ] **Step 3: убедиться, что тест падает**

Run: `cd /Users/abduraxmonturdiyev/inspectorx-vision && ./ix test tests/test_vlm_config.py -v`
Expected: FAIL — `pipeline.vlm_enabled` / `_DailyCap` / провайдер `"off"` не определены.

- [ ] **Step 4: реализация**

В `pipeline.py` (после `reader_settings()`):

```python
DEFAULT_VLM = False  # Волна 1: VLM за выключателем; Волна 2 включает явно.


def vlm_enabled() -> bool:
    """Включён ли VLM-слой (`config/routing.yaml: extraction.vlm`)."""
    return bool(extraction_config().get("vlm", DEFAULT_VLM))
```

И в `inspect()` — точка выбора экстрактора (сейчас строка ~304 `active_extractor = extractor or make_extractor(provider, model=model, live=live)`):

```python
    if extractor is not None:
        active_extractor = extractor
    else:
        active_extractor = make_extractor(provider if vlm_enabled() else "off",
                                          model=model, live=live)
```

В `extractor.py`:

```python
class DisabledExtractor(FactExtractor):
    """VLM выключен флагом: ноль вызовов, причина — в аудите, не в тишине."""

    name = "off"
    model = "off"

    def extract(self, schema: FactSchema, series: PreparedSeries | None = None) -> FactPassport:
        passport = FactPassport()
        if series is not None:
            passport.photos = series.to_photo_facts()
        passport.extraction = ExtractionAudit(
            provider=self.name, model=self.model, calls=0,
            errors=["VLM выключен: config/routing.yaml → extraction.vlm"],
        )
        return passport
```

В `make_extractor` — ветка `if provider == "off": return DisabledExtractor()`.

`CachedExtractor.__init__` — замена дефолта каталога:

```python
        default_dir = env_mod.get("IXV_VLM_CACHE_DIR")
        self.cache_dir = cache_dir or (
            Path(default_dir) if default_dir else REPO_ROOT / "data" / "vlm_cache" / "facts")
```

`_DailyCap` (рядом с `_CallBudget`):

```python
FALLBACK_CAP_FILE = REPO_ROOT / "runs" / "fallback_calls.json"
DEFAULT_FALLBACK_DAILY_MAX = 40


class _DailyCap:
    """Суточный потолок дорогого резервного провайдера (§6 плана фотоконтроля).

    Файловый счётчик с ключом-датой: воркер живёт в одной реплике (см. Global
    Constraints), атомарность файла не требуется — как и у `_CallBudget`.
    """

    def __init__(self, path: Path | None = None, max_calls: int | None = None) -> None:
        self.path = path or FALLBACK_CAP_FILE
        if max_calls is None:
            raw = env_mod.get("IXV_VLM_FALLBACK_DAILY_MAX")
            max_calls = int(raw) if raw and raw.isdigit() else DEFAULT_FALLBACK_DAILY_MAX
        self.max_calls = max_calls

    def try_reserve(self) -> bool:
        import datetime
        today = datetime.date.today().isoformat()
        state = {"date": today, "used": 0}
        if self.path.exists():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if loaded.get("date") == today:
                state = loaded
        if state["used"] >= self.max_calls:
            return False
        state["used"] += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
```

- [ ] **Step 5: тесты зелёные, полный прогон**

Run: `./ix test -q`
Expected: PASS, существующие тесты не сломаны.

- [ ] **Step 6: Commit**

```bash
git add config/routing.yaml src/ixvision/pipeline.py src/ixvision/engines/extractor.py tests/test_vlm_config.py
git commit -m "feat(vision): флаг extraction.vlm, каталог кэша из env, суточный потолок резервного провайдера"
```

---

### Task 3: Vision — деградация по §6: FallbackExtractor и три ступени

Gemini недоступен → gpt-4.1-mini (авто, с записью и суточным потолком); оба недоступны → локальный режим (`degraded_mode='local_only'`, половина единицы квоты); и чтец недоступен → `failed` с возвратом резерва.

**Files:**
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/engines/extractor.py`
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/facts.py` (`ExtractionAudit` — новое поле)
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/models.py` (`AuditInfo` — новое поле)
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/pipeline.py` (проброс `degraded_mode` в аудит)
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/server.py` (обработчик `/internal/inspect` Волны 1: отказ при недоступном чтеце)
- Create: `/Users/abduraxmonturdiyev/inspector-x-final/supabase/migrations/20260817100000_degraded_half_quota.sql`
- Test: `/Users/abduraxmonturdiyev/inspectorx-vision/tests/test_fallback.py` (новый)

**Interfaces:**
- Consumes: `_DailyCap` (Задача 2), `GeminiExtractor`/`OpenAIExtractor`/`CachedExtractor`, `ExtractionAudit(errors, calls, cached)`.
- Produces: `extractor.FallbackExtractor(primary, reserve, cap=None)`; `extractor.provider_unavailable(passport) -> bool`; провайдер `"auto"` в `make_extractor` (= `CachedExtractor(FallbackExtractor(Gemini, OpenAI), live=live)`); `ExtractionAudit.degraded_mode: str` (`""` | `"fallback_provider"` | `"local_only"`); `AuditInfo.degraded_mode: str`. Задача 13 сверяет `degraded_mode` в `photo_inspections`.

- [ ] **Step 1: падающий тест трёх ступеней**

```python
"""Деградация §6: резервный провайдер -> локальный режим. Мок недоступности, без сети."""
from ixvision.engines import extractor as ex
from ixvision.facts import ExtractionAudit, FactPassport, FactSchema


class _DownExtractor(ex.FactExtractor):
    """Провайдер «лежит»: extract кидает RuntimeError (нет ключа / сеть)."""

    name = "down"
    model = "down"

    def extract(self, schema, series=None):
        raise RuntimeError("провайдер недоступен (мок)")


def _stub(name: str) -> ex.StubExtractor:
    stub = ex.StubExtractor({})
    stub.name = name
    return stub


def test_falls_back_to_reserve_with_cap(tmp_path):
    cap = ex._DailyCap(path=tmp_path / "cap.json", max_calls=5)
    fb = ex.FallbackExtractor(_DownExtractor(), _stub("openai"), cap=cap)
    passport = fb.extract(FactSchema(), None)
    assert passport.extraction.degraded_mode == "fallback_provider"


def test_cap_exhausted_means_local_only(tmp_path):
    cap = ex._DailyCap(path=tmp_path / "cap.json", max_calls=0)
    fb = ex.FallbackExtractor(_DownExtractor(), _stub("openai"), cap=cap)
    passport = fb.extract(FactSchema(), None)
    assert passport.extraction.degraded_mode == "local_only"
    assert any("потолок" in e for e in passport.extraction.errors)


def test_both_down_means_local_only(tmp_path):
    cap = ex._DailyCap(path=tmp_path / "cap.json", max_calls=5)
    fb = ex.FallbackExtractor(_DownExtractor(), _DownExtractor(), cap=cap)
    passport = fb.extract(FactSchema(), None)
    assert passport.extraction.degraded_mode == "local_only"


def test_healthy_primary_no_degradation(tmp_path):
    cap = ex._DailyCap(path=tmp_path / "cap.json", max_calls=5)
    fb = ex.FallbackExtractor(_stub("gemini"), _stub("openai"), cap=cap)
    passport = fb.extract(FactSchema(), None)
    assert passport.extraction.degraded_mode == ""
```

- [ ] **Step 2: убедиться, что тест падает**

Run: `./ix test tests/test_fallback.py -v` — Expected: FAIL (`FallbackExtractor` не определён).

- [ ] **Step 3: реализация в `extractor.py`**

`ExtractionAudit` в `facts.py` получает поле `degraded_mode: str = ""` (pydantic, старые кэшированные паспорта грузятся с дефолтом). `AuditInfo` в `models.py` — то же поле `degraded_mode: str = ""`; `pipeline.inspect()` при сборке `AuditInfo` добавляет `degraded_mode=passport.extraction.degraded_mode`.

```python
def provider_unavailable(passport: FactPassport) -> bool:
    """Провайдер «лежал»: ни одного успешного шарда (все calls дали ошибку)."""
    audit = passport.extraction
    if audit.cached:
        return False
    return audit.calls > 0 and len(audit.errors) >= audit.calls


class FallbackExtractor(FactExtractor):
    """Ступени деградации §6: primary -> reserve (суточный потолок) -> local_only.

    Каждая ступень помечается в `ExtractionAudit.degraded_mode` — плашку
    «сокращённый режим» и половину квоты серверная финализация выводит из
    этого поля, а не угадывает по ошибкам.
    """

    name = "fallback"

    def __init__(self, primary: FactExtractor, reserve: FactExtractor,
                 cap: "_DailyCap | None" = None) -> None:
        self.primary = primary
        self.reserve = reserve
        self.model = primary.model
        self._cap = cap or _DailyCap()

    def _try(self, inner: FactExtractor, schema: FactSchema,
             series: PreparedSeries | None) -> FactPassport:
        try:
            return inner.extract(schema, series)
        except RuntimeError as exc:  # нет ключа, сеть до первого шарда
            passport = FactPassport()
            if series is not None:
                passport.photos = series.to_photo_facts()
            passport.extraction = ExtractionAudit(
                provider=inner.name, model=inner.model, calls=1,
                errors=[f"{inner.name}: {exc}"])
            return passport

    def extract(self, schema: FactSchema, series: PreparedSeries | None = None) -> FactPassport:
        passport = self._try(self.primary, schema, series)
        if not provider_unavailable(passport):
            return passport
        primary_errors = list(passport.extraction.errors)
        if not self._cap.try_reserve():
            passport.extraction.degraded_mode = "local_only"
            passport.extraction.errors.append(
                "резервный провайдер: суточный потолок исчерпан (IXV_VLM_FALLBACK_DAILY_MAX)")
            return passport
        fallback = self._try(self.reserve, schema, series)
        fallback.extraction.errors = primary_errors + list(fallback.extraction.errors)
        if provider_unavailable(fallback):
            fallback.extraction.degraded_mode = "local_only"
            return fallback
        fallback.extraction.degraded_mode = "fallback_provider"
        return fallback
```

В `make_extractor` — провайдер по умолчанию для воркера:

```python
    if provider == "auto":
        return CachedExtractor(
            FallbackExtractor(GeminiExtractor(model=model), OpenAIExtractor()), live=live)
```

- [ ] **Step 4: тесты зелёные**

Run: `./ix test tests/test_fallback.py tests/test_vlm_config.py -q && ./ix test -q` — Expected: PASS.

- [ ] **Step 5: ступень «и чтец недоступен → failed» в воркере**

Прочитать обработчик `/internal/inspect` в `src/ixvision/server.py` (артефакт Волны 1). Добавить после прогона: если `verdict.audit.degraded_mode == "local_only"` И чтец не покрыл ни одной грани (`verdict.facts.reader.faces == {}` при фотопути), эндпоинт возвращает `{"status": "failed", "reason": "vlm_unavailable"}` вместо вердикта — причина из закрытого списка возврата квоты (§4 нормативного плана). Тест — рядом с существующими тестами server (grep `test_server` в `tests/`), через `fastapi.testclient` и мок extractor с `degraded_mode="local_only"`.

- [ ] **Step 6: миграция половины квоты**

`supabase/migrations/20260817100000_degraded_half_quota.sql` — прочитать сначала фактическую сигнатуру `finalize_photo_inspection` из миграции Волны 1 (имя файла — из Задачи 1 Step 3) и дописать поверх неё:

```sql
-- Сокращённый режим (§6, ступень 2): оба VLM недоступны, прогон выполнен только
-- детерминированными источниками -> списывается ПОЛОВИНА единицы квоты.
-- used становится numeric, чтобы половина была числом, а не легендой.
alter table public.photo_quota
  alter column used type numeric(6,1) using used::numeric(6,1);

-- Перегрузка финализации: p_degraded_mode приходит из degraded_mode вердикта
-- воркера (серверная функция передаёт его при outcome='done').
-- Тело: как в исходной finalize_photo_inspection Волны 1, но при
-- p_outcome='done' and p_degraded_mode='local_only' квота списывается 0.5:
--   update public.photo_quota set reserved = reserved - 1, used = used + 0.5 ...
-- (точный текст скопировать из миграции Волны 1 и поправить одну строку списания;
--  сама исходная функция остаётся для обратной совместимости вызовов без параметра).
```

Проверка: `supabase db reset --local` проходит; SQL-тест руками: `select public.finalize_photo_inspection(...)` на строке-фикстуре даёт `used = 0.5`. В `api/vision/check.ts` (Волна 1) добавить проброс `degraded_mode` из ответа воркера в вызов финализации.

- [ ] **Step 7: Commit (оба репозитория)**

```bash
cd /Users/abduraxmonturdiyev/inspectorx-vision && git add -A && \
  git commit -m "feat(vision): деградация §6 — FallbackExtractor, degraded_mode, отказ при недоступном чтеце"
cd /Users/abduraxmonturdiyev/inspector-x-final && git add supabase/migrations/20260817100000_degraded_half_quota.sql api/vision/check.ts && \
  git commit -m "feat(db): сокращённый режим — половина единицы квоты при local_only"
```

---

### Task 4: Vision — привратник: подтверждение вторым ключом, отбраковка рамок

Ответ VLM принимается только подтверждённым: текст — Левенштейн ≤ 2 по словам чтеца; пиктограммы — второй ключ YOLO; координаты вне [0,100] отвергаются (не зажимаются). Неподтверждённое → «требует человека» с цитатой (слот понижается до `unclear`, verbatim сохраняется как цитата).

**Files:**
- Create: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/engines/gatekeeper.py`
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/engines/extractor.py` (`_clamp_bbox` → `_validate_bbox`)
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/facts.py` (`FactPassport.confirmed`)
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/pipeline.py` (вызов привратника между слиянием и судом)
- Test: `/Users/abduraxmonturdiyev/inspectorx-vision/tests/test_gatekeeper.py` (новый)

**Interfaces:**
- Consumes: `FactPassport.texts/elements/reader/sources`, `ReaderWord(text, conf, face)`, `yolo_zone_facts(series) -> dict[slot_id, ElementFact]` (pipeline, шаг 3-4), `FactSchema.shards`, `SlotKind`.
- Produces: `gatekeeper.confirm_passport(passport, schema, yolo_slots: set[str]) -> dict[str, str]` (slot_id → `"reader"|"yolo"`), `gatekeeper.enforce(passport, schema) -> list[str]` (понижённые слоты), `FactPassport.confirmed: dict[str, str]`. Задача 5 (переспрос) читает `confirmed` для правила «пуст ИЛИ не подтверждён».

- [ ] **Step 1: падающий тест**

```python
"""Привратник §5: неподтверждённый ответ VLM не становится вердиктом."""
from ixvision.engines import gatekeeper
from ixvision.engines.extractor import _validate_bbox
from ixvision.facts import (ElementFact, FactPassport, FactSchema, FactShard,
                            FactSlot, ReaderFact, ReaderWord, SlotKind, TextFact)


def _schema_with_text_slot(slot_id="mfg_date"):
    slot = FactSlot(id=slot_id, instruction_ru="дата изготовления")
    return FactSchema(shards=[FactShard(id="texts_1", kind=SlotKind.TEXT, slots=[slot])])


def test_text_confirmed_by_reader_levenshtein_2():
    passport = FactPassport()
    passport.texts["mfg_date"] = TextFact(found="yes", verbatim="12.2025")
    passport.sources["mfg_date"] = "vlm"
    passport.reader = ReaderFact(engine="easyocr", words=[
        ReaderWord(text="12.2O25", conf=0.9, face="side_panel")])  # OCR спутал 0/O
    confirmed = gatekeeper.confirm_passport(passport, _schema_with_text_slot(), set())
    assert confirmed.get("mfg_date") == "reader"


def test_unconfirmed_text_downgraded_with_quote_kept():
    passport = FactPassport()
    passport.texts["mfg_date"] = TextFact(found="yes", verbatim="12.2025")
    passport.sources["mfg_date"] = "vlm"
    passport.reader = ReaderFact(engine="easyocr", words=[])
    schema = _schema_with_text_slot()
    gatekeeper.confirm_passport(passport, schema, set())
    downgraded = gatekeeper.enforce(passport, schema)
    assert downgraded == ["mfg_date"]
    assert passport.texts["mfg_date"].found == "unclear"      # решает человек
    assert passport.texts["mfg_date"].verbatim == "12.2025"   # цитата сохранена


def test_element_confirmed_by_yolo_second_key():
    slot = FactSlot(id="cert_mark", instruction_ru="знак EAC")
    schema = FactSchema(shards=[FactShard(id="elements_1", kind=SlotKind.ELEMENT, slots=[slot])])
    passport = FactPassport()
    passport.elements["cert_mark"] = ElementFact(seen="yes")
    passport.sources["cert_mark"] = "vlm"
    confirmed = gatekeeper.confirm_passport(passport, schema, {"cert_mark"})
    assert confirmed.get("cert_mark") == "yolo"


def test_bbox_out_of_range_rejected_not_clamped():
    assert _validate_bbox([0, 0, 100, 100]) == [0.0, 0.0, 100.0, 100.0]
    assert _validate_bbox([10, 10, 640, 480]) == []   # пиксели, а не проценты
    assert _validate_bbox([-5, 0, 50, 50]) == []
```

Примечание: имена `FactSlot`/поля конструкторов проверить по `src/ixvision/facts.py` (`grep -n "class FactSlot\|class FactShard" src/ixvision/facts.py`) и поправить тест под фактические, не меняя смысла.

- [ ] **Step 2: убедиться, что тест падает**

Run: `./ix test tests/test_gatekeeper.py -v` — Expected: FAIL (модуля нет).

- [ ] **Step 3: реализация `engines/gatekeeper.py`**

```python
"""Привратник (§5 плана фотоконтроля): ответ VLM принимается, только если
подтверждён независимо. Текст — нечёткое совпадение со словами чтеца
(Левенштейн <= 2 на слово); элементы-пиктограммы — второй ключ YOLO;
семантика без второго ключа вердикта не получает никогда — слот уходит
человеку с цитатой (понижение found/seen до "unclear", verbatim сохраняется).

Детерминирован и бесплатен: ни сети, ни модели — только паспорт и схема.
"""
from __future__ import annotations

import re

from ..facts import FactPassport, FactSchema, SlotKind

READER_MIN_CONF = 0.5   # тот же порог, что policy.yaml: reader_min_conf
MAX_DISTANCE = 2


def _levenshtein(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > MAX_DISTANCE:
        return MAX_DISTANCE + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[\w.,/%-]+", text.lower()) if len(t) > 1]


def confirm_text(verbatim: str, passport: FactPassport) -> bool:
    """Каждый токен цитаты VLM находит пару среди слов чтеца (Левенштейн <= 2)."""
    words = [w.text.lower() for w in passport.reader.words if w.conf >= READER_MIN_CONF]
    need = _tokens(verbatim)
    if not words or not need:
        return False
    return all(any(_levenshtein(t, w) <= MAX_DISTANCE for w in words) for t in need)


def confirm_passport(passport: FactPassport, schema: FactSchema,
                     yolo_slots: set[str]) -> dict[str, str]:
    """slot_id -> чем подтверждён ('reader' | 'yolo'). Пишет passport.confirmed."""
    confirmed: dict[str, str] = {}
    for shard in schema.shards:
        for slot in shard.slots:
            if shard.kind == SlotKind.TEXT:
                fact = passport.texts.get(slot.id)
                if fact is not None and fact.found == "yes" and fact.verbatim \
                        and confirm_text(fact.verbatim, passport):
                    confirmed[slot.id] = "reader"
            elif shard.kind == SlotKind.ELEMENT:
                fact = passport.elements.get(slot.id)
                if fact is not None and fact.seen == "yes" and slot.id in yolo_slots:
                    confirmed[slot.id] = "yolo"
    passport.confirmed = confirmed
    return confirmed


def unconfirmed_slots(passport: FactPassport, schema: FactSchema) -> list[str]:
    """Слоты с ответом VLM без второго ключа — кандидаты на переспрос (Задача 5)."""
    out: list[str] = []
    for shard in schema.shards:
        if shard.kind == SlotKind.SCAN:
            continue
        for slot in shard.slots:
            if passport.sources.get(slot.id) != "vlm":
                continue
            fact = passport.texts.get(slot.id) or passport.elements.get(slot.id)
            answered = fact is not None and (
                getattr(fact, "found", None) == "yes" or getattr(fact, "seen", None) == "yes")
            if answered and slot.id not in passport.confirmed:
                out.append(slot.id)
    return out


def enforce(passport: FactPassport, schema: FactSchema) -> list[str]:
    """Понижение неподтверждённых ответов VLM до 'unclear' (цитата сохраняется).

    Судья увидит 'unclear' и вынесет UNREADABLE — «требует человека», а цитата
    (verbatim) уедет в отчёт как то, что модель прочитала.
    """
    downgraded: list[str] = []
    for slot_id in unconfirmed_slots(passport, schema):
        if slot_id in passport.texts:
            passport.texts[slot_id].found = "unclear"
        elif slot_id in passport.elements:
            passport.elements[slot_id].seen = "unclear"
        downgraded.append(slot_id)
    return downgraded
```

`FactPassport` в `facts.py` получает поле `confirmed: dict[str, str] = Field(default_factory=dict)`.

В `extractor.py` `_clamp_bbox` переименовывается в `_validate_bbox`, тело:

```python
def _validate_bbox(raw: Any) -> list[float]:
    """Ровно четыре числа В ПРЕДЕЛАХ [0,100] — иначе пустая рамка.

    Зажимание превращало мусор (пиксельные координаты) в валидную с виду
    рамку [100,100,100,100]; отбраковка превращает мусор в честное «не прочитано».
    """
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return []
    try:
        values = [float(v) for v in raw]
    except (TypeError, ValueError):
        return []
    if any(v < 0.0 or v > 100.0 for v in values):
        return []
    return values
```

Обновить оба вызова (`_parse_element`, `_parse_scan`) и существующий тест на клампинг (`grep -rn "_clamp_bbox" tests/ src/`).

- [ ] **Step 4: вызов в pipeline**

В `pipeline.inspect()` после шага 6 (слияние чтеца, строка ~327) и ДО шага 7 (судья):

```python
    # 6b. привратник: ответы VLM без второго ключа уходят человеку с цитатой.
    from .engines import gatekeeper
    gatekeeper.confirm_passport(passport, schema, set(yolo_facts.keys()))
    #    (переспрос между confirm и enforce добавит Задача 5)
    gatekeeper.enforce(passport, schema)
```

- [ ] **Step 5: тесты и гейты**

Run: `./ix test -q && ./ix bench --assert missed_as_pass=0 --assert unsupported_decision=0`
Expected: PASS. Bench на кэшированных паспортах: решительность может упасть (снятие неподтверждённых решений — ожидаемо), гейты держатся, ложные тревоги не растут.

- [ ] **Step 6: Commit**

`git add -A && git commit -m "feat(vision): привратник — подтверждение вторым ключом, отбраковка рамок вне [0,100]"`

---

### Task 5: Vision — кропы вместо целых кадров и детерминированный переспрос (vlm_reask)

**Files:**
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/engines/extractor.py` (`_collect_images`, `_run_shard` — метка стадии)
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/pipeline.py` (переспрос между `confirm_passport` и `enforce`)
- Test: `/Users/abduraxmonturdiyev/inspectorx-vision/tests/test_reask.py` (новый)

**Interfaces:**
- Consumes: `gatekeeper.unconfirmed_slots` (Задача 4), `PreparedPhoto.crops` (список `Crop`; поля проверить: `grep -n "class Crop" -A 10 src/ixvision/vision/preprocess.py` — ожидаются `image`, `cls`), `_CallBudget.log`, `vlm_enabled()`.
- Produces: `_collect_images(series, jpeg_quality, max_images=4, shard=None)` — для TEXT/ELEMENT-шардов кропы `label_zone`, для SCAN — целые кадры; `pipeline._reask(extractor, schema, series, passport, slot_ids)` — ровно один переспрос; записи бюджета с `"stage": "vlm_reask"` (по ним воркер Волны 1 пишет строку `photo_model_calls.stage='vlm_reask'`).

- [ ] **Step 1: падающий тест переспроса**

```python
"""Переспрос по детерминированному правилу: слот пуст ИЛИ не подтверждён; ровно один раз."""
from ixvision import pipeline
from ixvision.engines import extractor as ex
from ixvision.facts import FactPassport, FactSchema, FactShard, FactSlot, SlotKind, TextFact


class _CountingExtractor(ex.StubExtractor):
    def __init__(self, payloads):
        super().__init__(payloads)
        self.extract_calls = 0

    def extract(self, schema, series=None):
        self.extract_calls += 1
        return super().extract(schema, series)


def _schema():
    return FactSchema(shards=[FactShard(id="texts_1", kind=SlotKind.TEXT, slots=[
        FactSlot(id="mfg_date", instruction_ru="дата изготовления")])])


def test_reask_targets_only_empty_or_unconfirmed():
    passport = FactPassport()
    passport.texts["mfg_date"] = TextFact(found="unclear")   # слот пуст -> кандидат
    passport.sources["mfg_date"] = "vlm"
    slots = pipeline._reask_candidates(passport, _schema())
    assert slots == ["mfg_date"]


def test_reask_happens_exactly_once():
    reask_extractor = _CountingExtractor(
        {"reask_texts_1": {"mfg_date": {"found": "yes", "verbatim": "12.2025"}}})
    passport = FactPassport()
    passport.texts["mfg_date"] = TextFact(found="unclear")
    passport.sources["mfg_date"] = "vlm"
    pipeline._reask(reask_extractor, _schema(), None, passport, ["mfg_date"])
    assert reask_extractor.extract_calls == 1
    assert passport.texts["mfg_date"].verbatim == "12.2025"
```

- [ ] **Step 2: тест падает** — `./ix test tests/test_reask.py -v` → FAIL.

- [ ] **Step 3: реализация**

В `extractor.py` `_collect_images` получает параметр `shard`:

```python
def _collect_images(series: PreparedSeries | None, jpeg_quality: int,
                    max_images: int = 4, shard: FactShard | None = None) -> list[bytes]:
    """SCAN-шарду — целые кадры; TEXT/ELEMENT — кропы label_zone из оригинала.

    Кроп режет и счёт токенов, и площадь для выдумки (§5). Нет кропов
    (детектор не нашёл label_zone) — честный откат к целым кадрам.
    """
    if series is None:
        return []
    if shard is not None and shard.kind != SlotKind.SCAN:
        crops = [c for ph in series.photos for c in ph.crops if c.cls == "label_zone"]
        if crops:
            return [encode_jpeg(c.image, quality=jpeg_quality) for c in crops[:max_images]]
    out: list[bytes] = []
    for photo in series.photos:
        if photo.image is None:
            continue
        out.append(encode_jpeg(photo.image, quality=jpeg_quality))
        if len(out) >= max_images:
            break
    return out
```

`_extract_via` собирает картинки пошардно: `images` считается внутри цикла `_run_shard(...)` (передать `_collect_images(series, extractor.jpeg_quality, shard=shard)`); проверка «нет пригодных фотографий» остаётся по целым кадрам. В `_run_shard` запись бюджета помечается стадией:

```python
    budget.log({
        "shard": shard.id, "provider": extractor.name, "model": extractor.model,
        "stage": "vlm_reask" if shard.id.startswith("reask_") else "vlm_shard",
        "latency_ms": int((time.monotonic() - t0) * 1000), **meta,
    })
```

В `pipeline.py`:

```python
def _reask_candidates(passport: FactPassport, schema: FactSchema) -> list[str]:
    """Правило переспроса (§6, механизм 2): слот ПУСТ или НЕ ПОДТВЕРЖДЁН."""
    from .engines import gatekeeper
    empty: list[str] = []
    for shard in schema.shards:
        if shard.kind == SlotKind.SCAN:
            continue
        for slot in shard.slots:
            fact = passport.texts.get(slot.id) or passport.elements.get(slot.id)
            value = getattr(fact, "found", None) or getattr(fact, "seen", None)
            if fact is None or value == "unclear":
                empty.append(slot.id)
    return sorted(set(empty) | set(gatekeeper.unconfirmed_slots(passport, schema)))


def _reask(extractor: FactExtractor, schema: FactSchema, series,
           passport: FactPassport, slot_ids: list[str]) -> None:
    """Ровно ОДИН переспрос: суб-схема из проблемных слотов, шарды reask_*."""
    if not slot_ids:
        return
    shards = []
    for shard in schema.shards:
        picked = [s for s in shard.slots if s.id in set(slot_ids)]
        if picked:
            shards.append(FactShard(id=f"reask_{shard.id}", kind=shard.kind, slots=picked))
    if not shards:
        return
    sub = FactSchema(shards=shards)
    answer = extractor.extract(sub, series)
    for slot_id in slot_ids:
        if slot_id in answer.texts and answer.texts[slot_id].found == "yes":
            passport.texts[slot_id] = answer.texts[slot_id]
            passport.sources[slot_id] = "vlm"
        elif slot_id in answer.elements and answer.elements[slot_id].seen == "yes":
            passport.elements[slot_id] = answer.elements[slot_id]
            passport.sources[slot_id] = "vlm"
    passport.extraction.calls += answer.extraction.calls
    passport.extraction.errors.extend(answer.extraction.errors)
```

Вставка в `inspect()` (блок из Задачи 4 Step 4 становится):

```python
    gatekeeper.confirm_passport(passport, schema, set(yolo_facts.keys()))
    if live and vlm_enabled() and not passport.extraction.cached:
        _reask(active_extractor, schema, series, passport, _reask_candidates(passport, schema))
        gatekeeper.confirm_passport(passport, schema, set(yolo_facts.keys()))
    gatekeeper.enforce(passport, schema)
```

(На кэшированных/выключенных прогонах переспроса нет — bench детерминирован; живой переспрос меряется задачами 6–7.) Импорты `FactShard`, `SlotKind` в `pipeline.py` уже есть/добавить из `facts`.

- [ ] **Step 4: тесты и полный прогон** — `./ix test -q` → PASS; `./ix bench --assert missed_as_pass=0 --assert unsupported_decision=0` → PASS (кэш не тронут: сигнатура схемы не менялась).

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(vision): VLM по кропам label_zone и детерминированный переспрос vlm_reask"`

---

### Task 6: Vision — первый живой прогон и контрольный bench на живых ответах

**Деньги: ≈ $0.05–0.11, потолок `IXV_VLM_MAX_CALLS=80`.** Предусловие: Задача 1 Step 6 подтверждена владельцем; `git status --porcelain config/` пуст.

**Files:**
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/runs/benchmark-live.json` (новый, коммитится как факт замера)
- Не меняет код (использует задачи 2–5).

**Interfaces:**
- Consumes: `./ix record gemini` (пишет живые паспорта через `CachedExtractor`), `IXV_VLM_CACHE_DIR` (Задача 2), `./ix bench --assert ...`.
- Produces: живой кэш `runs/live_cache/` (не коммитится, в `.gitignore`), файл сравнения `runs/benchmark-live.json`, включённый флаг `extraction.vlm: true` в коммите.

- [ ] **Step 1: включить флаг и зафиксировать пакеты**

```bash
cd /Users/abduraxmonturdiyev/inspectorx-vision
git status --porcelain config/            # ОБЯЗАН быть пуст (Global Constraints)
# в config/routing.yaml: extraction.vlm: false -> true
```

- [ ] **Step 2: живая запись паспортов эталонных серий**

```bash
export IXV_VLM_MAX_CALLS=80
export IXV_VLM_CACHE_DIR="$PWD/runs/live_cache"
./ix record gemini
```
Expected: по одному живому прогону на серию из `data/eval/sets.yaml` (5 фото-серий; ~4–6 шардов на серию ≈ 25–35 вызовов, ≈ $0.02–0.04 по прайсу Gemini flash-lite $0.10/$0.40 за MTok). Повторный запуск читает из кэша — бюджет не тратится. `runs/vlm_calls.json` показывает фактический расход: `python3 -c "import json;print(json.load(open('runs/vlm_calls.json'))['used'])"`.

- [ ] **Step 3: контрольный bench на живых ответах против кэшированных**

```bash
IXV_VLM_CACHE_DIR="$PWD/runs/live_cache" ./ix bench \
  --assert missed_as_pass=0 --assert unsupported_decision=0 > /tmp/bench-live.txt; echo "exit=$?"
./ix bench > /tmp/bench-baseline.txt   # без env — старый кэш data/vlm_cache/facts
diff <(grep -E "серия|итог" /tmp/bench-baseline.txt) <(grep -E "серия|итог" /tmp/bench-live.txt) || true
```
Expected: exit=0 — **оба гейта держатся на живых ответах** (это обязательное условие §8; падение гейта = стоп и разбор конкретной находки, политика не ослабляется). Расхождение чисел (решительность, ложные тревоги, fact_fill) — фиксируется, не replаyится: скопировать свежий `runs/benchmark.json` живого прогона в `runs/benchmark-live.json`. Отдельно проверить «подозрения»: живые `scan.forbidden_imagery_seen` НЕ порождают `fail` — только `unreadable` с подклассом `suspected` (механизм уже в ядре, `rule_engine.py:2159–2183`; в JSON bench не должно появиться ни одного `fail` с basis forbidden_imagery).

- [ ] **Step 4: разовый тест резервного провайдера (≈ $0.06)**

```bash
GEMINI_API_KEY=broken GOOGLE_API_KEY=broken IXV_VLM_MAX_CALLS=95 \
  ./ix check tobacco --level consumer \
  --photos "$(ls data/photos/*.jpg | head -1)" --provider auto --facts | tail -20
```
Expected: в аудите `degraded_mode: fallback_provider`, провайдер ответа — `openai`, счётчик `runs/fallback_calls.json` = 1. Один прогон gpt-4.1-mini ≈ $0.03–0.06 (detail:high, 9359 tok_in/шард). Ключи вернуть как были (env сломан только на команду).

- [ ] **Step 5: Commit**

```bash
echo "runs/live_cache/" >> .gitignore
git add config/routing.yaml runs/benchmark-live.json .gitignore
git commit -m "feat(vision): VLM включён — живой контрольный замер, гейты держатся на живых ответах"
```

---

### Task 7: Vision — воспроизводимость: 20 живых прогонов одной серии

**Деньги: ≈ $0.06, бюджет по спеке §8 — $0.20, потолок `IXV_VLM_MAX_CALLS=140`.**

**Files:**
- Create: `/Users/abduraxmonturdiyev/inspectorx-vision/scripts/reproducibility.py`
- Modify: `/Users/abduraxmonturdiyev/inspectorx-vision/ix` (кейс `repro`)
- Create: `/Users/abduraxmonturdiyev/inspectorx-vision/docs/REPRODUCIBILITY.md` (публикация доли стабильных пунктов — deliverable спеки §8)
- Test: `/Users/abduraxmonturdiyev/inspectorx-vision/tests/test_reproducibility.py` (новый, на функции агрегации, без сети)

**Interfaces:**
- Consumes: `pipeline.inspect(product_id, level, photos, extractor=...)` с живым `GeminiExtractor()` (мимо кэша), `data/eval/sets.yaml: sets` (поля `id`, `product`, `level`, `photos`, опц. `faces`).
- Produces: `stability(results: list[dict[str, str]]) -> tuple[float, dict[str, float]]` — доля чекпойнтов со 100%-стабильным статусом и по-чекпойнтная стабильность; отчёт в `docs/REPRODUCIBILITY.md`.

- [ ] **Step 1: падающий тест агрегации**

```python
from scripts.reproducibility import stability


def test_stability_share_and_per_checkpoint():
    runs = [
        {"a": "pass", "b": "fail"},
        {"a": "pass", "b": "unreadable"},
        {"a": "pass", "b": "fail"},
    ]
    share, per_cp = stability(runs)
    assert share == 0.5                 # стабилен 1 из 2 чекпойнтов
    assert per_cp["a"] == 1.0
    assert round(per_cp["b"], 2) == 0.67
```
(Импорт из `scripts/` — добавить в тест `sys.path.insert(0, str(ROOT))` по образцу других тестов репозитория, либо запуск `PYTHONPATH=.:src`.)

- [ ] **Step 2: тест падает** — `./ix test tests/test_reproducibility.py -v` → FAIL.

- [ ] **Step 3: скрипт**

```python
"""Воспроизводимость (§8 п.8): N живых прогонов одной серии, доля стабильных пунктов.

    ./ix repro                 — серия tobacco_c2 (по умолчанию), 20 прогонов, gemini
    ./ix repro dairy_c1 5      — другая серия / меньше прогонов

Каждый прогон — живой extract МИМО кэша (одинаковый вход, разные ответы модели),
судья детерминирован, значит разброс статусов = разброс извлечения.
Бюджет: 20 прогонов * ~5 шардов ~= 100 вызовов ~= $0.06 (потолок IXV_VLM_MAX_CALLS).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ixvision.engines.extractor import GeminiExtractor  # noqa: E402
from ixvision.pipeline import inspect, warmup  # noqa: E402


def stability(runs: list[dict[str, str]]) -> tuple[float, dict[str, float]]:
    """Доля чекпойнтов, у которых статус одинаков во ВСЕХ прогонах, и
    по-чекпойнтная доля самого частого статуса."""
    checkpoints = sorted({cp for r in runs for cp in r})
    per_cp = {}
    for cp in checkpoints:
        statuses = [r.get(cp, "missing") for r in runs]
        per_cp[cp] = Counter(statuses).most_common(1)[0][1] / len(statuses)
    stable = sum(1 for v in per_cp.values() if v == 1.0)
    return (stable / len(per_cp) if per_cp else 1.0), per_cp


def main() -> int:
    set_id = sys.argv[1] if len(sys.argv) > 1 else "tobacco_c2"
    n_runs = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    sets = yaml.safe_load((ROOT / "data/eval/sets.yaml").read_text(encoding="utf-8"))["sets"]
    series = next(s for s in sets if s["id"] == set_id)
    warmup()
    results, cost = [], 0.0
    for i in range(n_runs):
        verdict = inspect(series["product"], series["level"], series["photos"],
                          extractor=GeminiExtractor(), faces=series.get("faces"))
        results.append({f.checkpoint_id: f.status.value for f in verdict.findings})
        cost += verdict.audit.cost_usd
        print(f"  прогон {i + 1}/{n_runs}: решено "
              f"{sum(1 for s in results[-1].values() if s in ('pass', 'fail'))}, "
              f"итого ${cost:.4f}")
    share, per_cp = stability(results)
    lines = [
        "# Воспроизводимость извлечения VLM", "",
        f"Серия: `{set_id}`, прогонов: {n_runs}, провайдер: gemini, "
        f"стоимость: ${cost:.4f} (бюджет $0.20).", "",
        f"**Доля пунктов со стабильным статусом: {share:.1%}**", "",
        "| Чекпойнт | Стабильность |", "|---|---|",
    ]
    lines += [f"| {cp} | {v:.0%} |" for cp, v in sorted(per_cp.items(), key=lambda kv: kv[1])]
    (ROOT / "docs/REPRODUCIBILITY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"доля стабильных: {share:.1%} -> docs/REPRODUCIBILITY.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Поле `Finding.checkpoint_id` / `Finding.status` — проверить фактические имена (`grep -n "checkpoint_id\|class Finding" src/ixvision/models.py | head`) и поправить.

В `ix` добавить кейс: `repro)    exec "$PY" scripts/reproducibility.py "$@" ;;`

- [ ] **Step 4: тест зелёный** — `./ix test tests/test_reproducibility.py -q` → PASS.

- [ ] **Step 5: живой замер (деньги)**

Run: `IXV_VLM_MAX_CALLS=140 ./ix repro tobacco_c2 20`
Expected: 20 прогонов, суммарная стоимость ≤ $0.20 (реально ≈ $0.06), `docs/REPRODUCIBILITY.md` создан, доля стабильных опубликована. Порога-гейта нет — это первый замер, число публикуется как есть.

- [ ] **Step 6: Commit** — `git add scripts/reproducibility.py ix docs/REPRODUCIBILITY.md tests/test_reproducibility.py && git commit -m "feat(vision): метрика воспроизводимости — 20 живых прогонов, доля стабильных пунктов опубликована"`

---

### Task 8: Importer — живой Claude-раннер для Build-конвейера и мониторинга

Заменяет три заглушки `_cartographer_llm_runner` / `_build_llm_runner` / `_monitor_llm_runner` в `importer/cli.py` одним живым раннером (Anthropic SDK). Тиры `models.yaml` переводятся с плейсхолдеров gpt-5 на Claude (решение владельца: модель Build-контура — Claude API).

**Files:**
- Create: `/Users/abduraxmonturdiyev/inspector-x-final/importer/build/llm_live.py`
- Modify: `/Users/abduraxmonturdiyev/inspector-x-final/importer/build/models.yaml`
- Modify: `/Users/abduraxmonturdiyev/inspector-x-final/importer/cli.py`
- Modify: `/Users/abduraxmonturdiyev/inspector-x-final/importer/requirements.txt` (добавить `anthropic`)
- Test: `/Users/abduraxmonturdiyev/inspector-x-final/importer/tests/build/test_llm_live.py` (новый)

**Interfaces:**
- Consumes: контракт раннера `RunnerAgentLLM` (`importer/build/llm_client.py`): `runner(prompt, model) -> str | tuple[str, dict]`; `tuple`-форма несёт реальные токены (`{"input_tokens", "output_tokens"}`) → `Tracer` пишет их в `pipeline.llm_calls` без оценки.
- Produces: `llm_live.AnthropicRunner` (callable), `llm_live.make_live_runner() -> AnthropicRunner`; env `ANTHROPIC_API_KEY` (стандарт SDK), `IMPORTER_LLM_MAX_CALLS` (потолок вызовов на процесс, дефолт 400). Задачи 9–12 используют `make_live_runner`.

- [ ] **Step 1: падающий тест (без сети — фейковый клиент)**

```python
"""Живой Claude-раннер: контракт (text, usage), потолок вызовов, ошибки -> AgentLLMError."""
from types import SimpleNamespace

import pytest

from importer.build.llm_client import AgentLLMError, RunnerAgentLLM
from importer.build.llm_live import AnthropicRunner


class _FakeAnthropic:
    def __init__(self):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"ok": true}')],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=120, output_tokens=8),
        )


def test_returns_text_and_real_usage():
    fake = _FakeAnthropic()
    runner = AnthropicRunner(client=fake)
    llm = RunnerAgentLLM(runner)
    assert llm.complete("вопрос", "claude-sonnet-5") == '{"ok": true}'
    assert llm.last_usage == {"input_tokens": 120, "output_tokens": 8, "estimated": False}
    assert fake.calls[0]["model"] == "claude-sonnet-5"


def test_call_cap_raises_agent_llm_error():
    runner = AnthropicRunner(client=_FakeAnthropic(), max_calls=1)
    runner("раз", "claude-haiku-4-5")
    with pytest.raises(AgentLLMError, match="потолок"):
        runner("два", "claude-haiku-4-5")


def test_missing_key_is_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    runner = AnthropicRunner()  # клиент ленивый — конструктор без ключа не падает
    with pytest.raises(AgentLLMError, match="ANTHROPIC_API_KEY"):
        runner("вопрос", "claude-haiku-4-5")
```

- [ ] **Step 2: тест падает** — `.venv-importer/bin/python -m pytest importer/tests/build/test_llm_live.py -v` → FAIL (модуля нет).

- [ ] **Step 3: реализация `importer/build/llm_live.py`**

```python
"""Живой LLM-runner Build-конвейера и мониторинга: Claude API (Волна 2).

Контракт — `Callable[[prompt, model], tuple[str, dict]]` для `RunnerAgentLLM`
(`llm_client.py`): tuple-форма несёт РЕАЛЬНЫЕ токены бэкенда, и `Tracer`
пишет в `pipeline.llm_calls` фактический расход, а не оценку len//4.

Модель приходит параметром из `models.yaml: tiers` — раннер моделей не выбирает.
Потолок вызовов на процесс: IMPORTER_LLM_MAX_CALLS (страховка от разгона цикла;
денежный контроль — `python -m importer build cost --run <id>` по трейсингу).
Ключ: стандартный ANTHROPIC_API_KEY (SDK читает окружение сам); .env.importer
подхватывается тем же load_dotenv, что и importer/db.py.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from importer.build.llm_client import AgentLLMError

load_dotenv(".env.importer")

DEFAULT_MAX_TOKENS = 8192
DEFAULT_MAX_CALLS = 400


class AnthropicRunner:
    """runner(prompt, model) -> (text, usage). Ленивая инициализация клиента:
    построение реестра шагов/агентов не требует ключа — падает только
    реальный вызов модели (тот же принцип, что у прежних заглушек)."""

    def __init__(self, client=None, *, max_tokens: int = DEFAULT_MAX_TOKENS,
                 max_calls: int | None = None) -> None:
        self._client = client
        self._max_tokens = max_tokens
        if max_calls is None:
            raw = os.environ.get("IMPORTER_LLM_MAX_CALLS", "")
            max_calls = int(raw) if raw.isdigit() else DEFAULT_MAX_CALLS
        self._max_calls = max_calls
        self.calls = 0

    def _ensure_client(self):
        if self._client is None:
            if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
                raise AgentLLMError(
                    "нет ANTHROPIC_API_KEY: задать в .env.importer (см. .env.importer.example)")
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def __call__(self, prompt: str, model: str) -> tuple[str, dict]:
        if self.calls >= self._max_calls:
            raise AgentLLMError(
                f"потолок вызовов исчерпан: {self.calls}/{self._max_calls} "
                "(IMPORTER_LLM_MAX_CALLS)")
        self.calls += 1
        client = self._ensure_client()
        import anthropic
        try:
            resp = client.messages.create(
                model=model, max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}])
        except anthropic.APIStatusError as exc:
            raise AgentLLMError(f"Claude API {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AgentLLMError(f"Claude API недоступен: {exc}") from exc
        if resp.stop_reason == "refusal":
            raise AgentLLMError("Claude API: refusal — классификатор отклонил запрос")
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return text, {"input_tokens": resp.usage.input_tokens,
                      "output_tokens": resp.usage.output_tokens}


def make_live_runner() -> AnthropicRunner:
    return AnthropicRunner()
```

Примечание к фейку в тесте: `_FakeAnthropic` не является `anthropic.Anthropic`, поэтому в `__call__` ветки `except anthropic...` импортируются локально и на фейке не срабатывают — это сознательно (тесты без сети и без установленного ключа).

- [ ] **Step 4: `models.yaml` — тиры Claude и актуальный прайс**

```yaml
# Тиры моделей generic-агентов Build-конвейера (ADR-0003, Задача 13).
#
# ВОЛНА 2 (2026-08): решение владельца — живой бэкенд Build-контура = Claude API.
# Прежние значения (gpt-5-*) были плейсхолдером мастер-плана №1 и живым кодом
# не вызывались ни разу (заглушки-раннеры). Соответствие тиров сохранено:
# cheap — массовые дешёвые вызовы, mid — producer-шаги, expensive — Cartographer
# (deep-research) и усиленный Verifier для cheap/mid (agents.py:verifier_model_for).
tiers:
  cheap: claude-haiku-4-5
  mid: claude-sonnet-5
  expensive: claude-opus-5

# usd за 1M токенов, публичный прайс Anthropic на 2026-08.
# У claude-sonnet-5 до 2026-08-31 действует intro-прайс $2/$10 — в таблице
# ПОЛНЫЙ прайс (консервативная оценка стоимости, счёт не занизим).
pricing:
  claude-haiku-4-5:
    input_per_1m_usd: 1.0
    output_per_1m_usd: 5.0
  claude-sonnet-5:
    input_per_1m_usd: 3.0
    output_per_1m_usd: 15.0
  claude-opus-5:
    input_per_1m_usd: 5.0
    output_per_1m_usd: 25.0
```

Прогнать `grep -rn "gpt-5" importer/` — тесты, зашитые на старые имена моделей, обновить на тиры (`load_models_config().tiers["mid"]` вместо литералов).

- [ ] **Step 5: подключить в `importer/cli.py`**

Заменить тела трёх заглушек делегированием одному разделяемому раннеру (общий потолок на процесс):

```python
from importer.build.llm_live import make_live_runner

_live_runner = None


def _shared_live_runner(prompt: str, model: str):
    """Один живой раннер на процесс CLI: общий потолок IMPORTER_LLM_MAX_CALLS
    для build map / build run / monitor — перерасход невозможен по построению."""
    global _live_runner
    if _live_runner is None:
        _live_runner = make_live_runner()
    return _live_runner(prompt, model)
```

`_cartographer_llm_runner`, `_build_llm_runner`, `_monitor_llm_runner` становятся однострочными обёртками `return _shared_live_runner(prompt, model)` (докстринги обновить: «живой Claude-раннер, Волна 2»; `NotImplementedError` уходит). `importer/requirements.txt` += `anthropic`; `pip install anthropic` в `.venv-importer`.

- [ ] **Step 6: тесты зелёные** — `.venv-importer/bin/python -m pytest importer/tests -q` → PASS (все 552+; старые тесты заглушек, если ссылались на `NotImplementedError` в cli, обновить на новый контракт).

- [ ] **Step 7: Commit** — `git add importer/build/llm_live.py importer/build/models.yaml importer/cli.py importer/requirements.txt importer/tests/build/test_llm_live.py && git commit -m "feat(importer): живой Claude-раннер Build и мониторинга, тиры моделей Claude вместо плейсхолдеров"`

---

### Task 9: Importer — живой веб-поиск для шага samples

`_LiveWebSearcher` (`importer/build/websearch.py`) перестаёт падать `NotImplementedError`: реализация через server-side инструмент `web_search_20260209` Claude API (доступен на mid-тире `claude-sonnet-5`).

**Files:**
- Modify: `/Users/abduraxmonturdiyev/inspector-x-final/importer/build/websearch.py`
- Test: `/Users/abduraxmonturdiyev/inspector-x-final/importer/tests/build/test_websearch_live.py` (новый)

**Interfaces:**
- Consumes: `SearchResult` (TypedDict `title/url/snippet`), контракт `WebSearcher.search(query) -> list[SearchResult]` (пустой список = «не нашёл», не ошибка).
- Produces: `_LiveWebSearcher(client=None, max_uses=3)` — живая реализация; `get_web_searcher()` без изменений интерфейса (env `WEBSEARCH_BACKEND=live` — дефолт).

- [ ] **Step 1: падающий тест**

```python
from types import SimpleNamespace

from importer.build.websearch import _LiveWebSearcher


def _resp(text, stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)], stop_reason=stop_reason)


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def test_parses_json_array_of_results():
    fake = _FakeClient([_resp('[{"title": "Шаблон", "url": "https://lex.uz/x", "snippet": "..." }]')])
    results = _LiveWebSearcher(client=fake).search("шаблон декларации")
    assert results == [{"title": "Шаблон", "url": "https://lex.uz/x", "snippet": "..."}]
    assert any(t.get("type") == "web_search_20260209" for t in fake.calls[0]["tools"])


def test_garbage_answer_means_empty_not_crash():
    fake = _FakeClient([_resp("ничего не нашлось, вот прости")])
    assert _LiveWebSearcher(client=fake).search("абракадабра") == []


def test_pause_turn_resumed_once():
    fake = _FakeClient([_resp("", stop_reason="pause_turn"), _resp('[]')])
    assert _LiveWebSearcher(client=fake).search("query") == []
    assert len(fake.calls) == 2
```

- [ ] **Step 2: тест падает** — pytest → FAIL (`_LiveWebSearcher.search` кидает NotImplementedError).

- [ ] **Step 3: реализация (заменить тело `_LiveWebSearcher`)**

```python
class _LiveWebSearcher:
    """Живой веб-поиск: server-side инструмент web_search Claude API.

    Модель просят вернуть СТРОГО JSON-массив находок — парсим текстовые блоки,
    а не внутренности tool_result (их формат — деталь провайдера). Мусорный
    ответ = пустой список: контракт WebSearcher трактует пусто как «не нашёл».
    """

    MODEL = "claude-sonnet-5"   # web_search_20260209 требует Sonnet 4.6+ / Opus 4.6+
    MAX_RESUMES = 2             # server-side цикл может вернуть pause_turn

    def __init__(self, client=None, max_uses: int = 3) -> None:
        self._client = client
        self._max_uses = max_uses

    def _ensure_client(self):
        if self._client is None:
            from importer.build.llm_live import AnthropicRunner  # noqa: F401  (load_dotenv)
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def search(self, query: str) -> list[SearchResult]:
        import json
        client = self._ensure_client()
        prompt = (
            "Найди в интернете официальные шаблоны/образцы документов по запросу. "
            'Верни СТРОГО JSON-массив (до 5 элементов) объектов '
            '{"title": str, "url": str, "snippet": str} без пояснений и markdown.\n'
            f"Запрос: {query}")
        messages = [{"role": "user", "content": prompt}]
        resp = client.messages.create(
            model=self.MODEL, max_tokens=2048,
            tools=[{"type": "web_search_20260209", "name": "web_search",
                    "max_uses": self._max_uses}],
            messages=messages)
        for _ in range(self.MAX_RESUMES):
            if resp.stop_reason != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": resp.content}]
            resp = client.messages.create(
                model=self.MODEL, max_tokens=2048,
                tools=[{"type": "web_search_20260209", "name": "web_search",
                        "max_uses": self._max_uses}],
                messages=messages)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            return []
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return []
        return [SearchResult(title=str(r.get("title", "")), url=str(r.get("url", "")),
                             snippet=str(r.get("snippet", "")))
                for r in data if isinstance(r, dict) and r.get("url")]
```

- [ ] **Step 4: тесты зелёные** — `pytest importer/tests/build/test_websearch_live.py importer/tests -q` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(importer): живой веб-поиск шага samples через web_search Claude API"`

---

### Task 10: Importer — Rule-maker как генератор PR-кандидатов

Шаг `rule` вместо no-op генерирует черновик атомарной проверки в YAML-формате пакетов inspectorx-vision (kind/severity/subject/params/question_ru/hint_ru + цитата нормы) и кладёт файл-кандидат в `config/requirements/candidates/` репозитория vision (PR через `gh` — опционально, за флагом). **НЕ пишет в базу, НЕ мёржится автоматически.** Verifier («критическая точка» ADR-0003 решение 5) сохраняется: на каждое правило отдельный вердикт, отклонено хоть одно — весь набор бракуется.

**Files:**
- Modify: `/Users/abduraxmonturdiyev/inspector-x-final/importer/build/steps_rule.py`
- Test: `/Users/abduraxmonturdiyev/inspector-x-final/importer/tests/build/test_steps_rule.py` (расширить существующий)
- Create (генерируется в рантайме, не коммитится планом): `/Users/abduraxmonturdiyev/inspectorx-vision/config/requirements/candidates/*.yaml`

**Interfaces:**
- Consumes: `Classifier`/`Verifier`/`verifier_model_for` (`agents.py`), `NormFragment.content` (`legalx.py`), `ItemContext` (`ctx.item.id`, `ctx.item.expected_item`, `ctx.data['category_slug']`, `ctx.data['norm_fragment']`), формат проверки vision-пакета (см. `config/requirements/tobacco.yaml`, ключи `id/kind/severity/group/subject/params/level/question_ru/hint_ru`).
- Produces: `RuleStep` с новым выходом: `ctx.data['rules'] = []` ВСЕГДА (в базу ничего не едет), `ctx.data['rule_candidates'] = [str(path), ...]`; env `IXV_CANDIDATES_DIR` (дефолт `/Users/abduraxmonturdiyev/inspectorx-vision/config/requirements/candidates`), env `RULE_CANDIDATE_PR=1` — открыть PR через `gh` (только создание, без мёржа); `validate_candidate(check: dict) -> list[str]` — локальный линтер params.

- [ ] **Step 1: падающие тесты (расширить `test_steps_rule.py`, старые тесты no-op заменить)**

```python
def test_rule_step_writes_candidate_yaml_not_db(tmp_path, monkeypatch):
    """Формат «машина предлагает — человек утверждает»: файл-кандидат, rules=[]."""
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([
        # Rule-maker (Classifier): валидная проверка в формате vision-пакета
        json.dumps({"rules": [{
            "kind": "text_semantic", "severity": "major", "subject": "other:check",
            "params": {"expect": "any_mention", "pattern_hints": ["состав"],
                       "language": ["uz"]},
            "question_ru": "Указан ли состав на узбекском?",
            "hint_ru": "Оборотная сторона, мелкий кегль",
        }]}),
        # Verifier: pass
        json.dumps({"passed": True, "reasoning": "правило следует из нормы"}),
    ])
    ctx = make_marking_ctx()  # хелпер существующих тестов файла: category_slug='marking' + norm_fragment
    result = RuleStep(llm)(ctx)
    assert result.status == "ok"
    assert ctx.data["rules"] == []                      # в requirement_rules НЕ едет
    paths = ctx.data["rule_candidates"]
    assert len(paths) == 1
    doc = yaml.safe_load(Path(paths[0]).read_text(encoding="utf-8"))
    assert doc["check"]["kind"] == "text_semantic"
    assert "quote_ru" in doc["source"]                  # цитата нормы обязательна
    scenario = Path(paths[0].replace(".yaml", "-scenario.yaml"))
    assert scenario.exists()                            # фикстура — вместе с кандидатом


def test_invalid_candidate_rejected_by_linter(tmp_path, monkeypatch):
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([json.dumps({"rules": [{"kind": "teleportation"}]}),
                       json.dumps({"rules": [{"kind": "teleportation"}]})])
    result = RuleStep(llm)(make_marking_ctx())
    assert result.status == "fail"
    assert list(tmp_path.glob("*.yaml")) == []          # мусор кандидатом не становится
```

(`ScriptedLLM`/`make_marking_ctx` — переиспользовать/адаптировать фикстуры существующего `test_steps_rule.py`; сверить фактические имена перед правкой: `grep -n "def \|class " importer/tests/build/test_steps_rule.py | head -20`.)

- [ ] **Step 2: тесты падают** — pytest → FAIL.

- [ ] **Step 3: реализация в `steps_rule.py`**

Обновить `RULE_PROFILE.system_prompt` и `response_schema` на формат vision-проверки:

```python
RULE_PROFILE = Profile(
    name="rule",
    system_prompt=(
        "Ты превращаешь текст нормы права о маркировке/упаковке в ЧЕРНОВИК "
        "атомарной машинной проверки для фото-чека (формат пакетов inspectorx-vision). "
        'Каждое правило — объект: {"kind": "presence|absence|text_semantic|geometry", '
        '"severity": "critical|major|minor|info", "subject": str, "params": object, '
        '"question_ru": str, "hint_ru": str}. Правил может быть несколько — по одному '
        "на каждое проверяемое условие. Ничего не придумывай: каждое правило обязано "
        "напрямую следовать из текста нормы."
    ),
    response_schema={
        "type": "object",
        "properties": {"rules": {"type": "array", "minItems": 1, "items": {"type": "object"}}},
        "required": ["rules"],
    },
    tier="mid",
)

CHECK_KINDS = {"presence", "absence", "text_semantic", "geometry"}
SEVERITIES = {"critical", "major", "minor", "info"}
DEFAULT_CANDIDATES_DIR = "/Users/abduraxmonturdiyev/inspectorx-vision/config/requirements/candidates"


def validate_candidate(check: dict) -> list[str]:
    """Локальный линтер кандидата — дефекты ловятся ДО того, как начнут стоить
    ревью-часов (мини-версия vision scripts/lint_params.py; полный линтер
    прогонит CI vision по каталогу candidates/)."""
    problems = []
    if check.get("kind") not in CHECK_KINDS:
        problems.append(f"kind вне словаря: {check.get('kind')!r}")
    if check.get("severity") not in SEVERITIES:
        problems.append(f"severity вне словаря: {check.get('severity')!r}")
    if not isinstance(check.get("params"), dict):
        problems.append("params отсутствует или не объект")
    if not check.get("question_ru"):
        problems.append("нет question_ru")
    return problems
```

В `RuleStep._run` после цикла Verifier (все вердикты pass) — вместо `ctx.data["rules"] = verified_rules`:

```python
        candidates_dir = Path(os.environ.get("IXV_CANDIDATES_DIR", DEFAULT_CANDIDATES_DIR))
        candidates_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        for index, entry in enumerate(verified_rules, start=1):
            check = dict(entry["rule"])
            problems = validate_candidate(check)
            if problems:
                return StepResult(status="fail", verdicts=verdicts,
                                  error="шаг 'rule': кандидат не прошёл линтер: " + "; ".join(problems))
            check.setdefault("id", f"candidate.{ctx.item.id}.{index}")
            check.setdefault("group", "candidate")
            check.setdefault("level", "consumer")
            doc = {
                "candidate": True,
                "generated_by": "build-pipeline/rule-step",
                "item_id": str(ctx.item.id),
                "requirement_title_ru": ctx.item.expected_item,
                "source": {"quote_ru": norm_fragment.content[:800]},
                "check": check,
                "review": "НЕ мёржить автоматически: ревью человеком, сценарная фикстура "
                          "(tests/scenarios/) — до переноса в пакет",
            }
            path = candidates_dir / f"{ctx.item.id}-{index}.yaml"
            path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                            encoding="utf-8")
            # Сценарная фикстура — ВМЕСТЕ с кандидатом (валидация «до предложения»,
            # §8 нормативного плана): pass-набор фактов (искомая формулировка есть)
            # и fail-набор (грань прочитана, формулировки нет). Формат — как в
            # tests/scenarios/*.yaml vision (Волна 1); CI vision гоняет каталог
            # candidates/ через scenario_runner вместе с пакетами.
            hints = check.get("params", {}).get("pattern_hints") or ["<формулировка>"]
            fixture = {
                "candidate_check_id": check["id"],
                "cases": [
                    {"name": "pass", "expect": "pass",
                     "reader_words": [{"text": hints[0], "face": "front_panel", "conf": 0.9}]},
                    {"name": "fail", "expect": "fail",
                     "reader_words": [{"text": "нейтральный-текст", "face": "front_panel",
                                       "conf": 0.9}]},
                ],
            }
            fixture_path = candidates_dir / f"{ctx.item.id}-{index}-scenario.yaml"
            fixture_path.write_text(
                yaml.safe_dump(fixture, allow_unicode=True, sort_keys=False), encoding="utf-8")
            paths.append(str(path))
        ctx.data["rules"] = []              # в requirement_rules по-прежнему НИЧЕГО
        ctx.data["rule_candidates"] = paths
        return StepResult(status="ok", verdicts=verdicts)
```

Ключи сценарной фикстуры (`cases/expect/reader_words`) сверить с фактическим форматом `tests/scenarios/tobacco.yaml` vision (Волна 1): `sed -n '1,40p' /Users/abduraxmonturdiyev/inspectorx-vision/tests/scenarios/tobacco.yaml` — и привести генератор к нему один в один (фикстуру должен исполнять существующий `tests/scenario_runner.py`, а не новый код).

Импорты `os`, `yaml`, `Path` добавить. Опциональный PR (в конце `_run`, только при `os.environ.get("RULE_CANDIDATE_PR") == "1"` и наличии `gh`): `subprocess.run(["git", "-C", vision_repo, "checkout", "-b", branch], ...)` + `git add candidates/` + `git commit` + `gh pr create --title "rule-candidate: <item>" --body "машина предлагает — человек утверждает"` — любые ошибки subprocess НЕ валят шаг (кандидат-файл уже записан), только warning в `ctx.data`.

- [ ] **Step 4: тесты зелёные** — `pytest importer/tests/build/test_steps_rule.py importer/tests -q` → PASS.

- [ ] **Step 5: Commit** — `git commit -am "feat(importer): шаг rule — генератор PR-кандидатов в YAML-пакеты vision вместо no-op"`

---

### Task 11: Первый живой прогон Build-конвейера и eval-golden на живой модели

**Деньги: ≈ $2.7, контроль через `build cost`, стоп при > $2 за прогон run.** Предусловия: задачи 8–10; локальный Supabase (Задача 1 Step 7); `LEGALX_BACKEND=mock` (живой LegalX — внешняя зависимость D1/D2, вне Волны 2).

**Files:**
- Modify: `/Users/abduraxmonturdiyev/inspector-x-final/importer/cli.py` (флаг `--live` у eval-golden)
- Modify: `/Users/abduraxmonturdiyev/inspector-x-final/importer/golden/baseline.json` (после ревью владельца)

**Interfaces:**
- Consumes: CLI `build map/approve-map/run/status/attention/coverage/cost/publish/eval-golden`; `run_eval(items, legalx=..., llm=..., valid_category_slugs=..., backend=..., baseline=...)`; `HeuristicBaselineLLM`.
- Produces: живой baseline golden-набора (стоп-точка ②), живая карта и прогон группы 2204/UZ (стоп-точка ① — апрув владельца), первые rule-кандидаты в vision.

- [ ] **Step 1: eval-golden получает `--live`**

В `importer/cli.py` к парсеру eval-golden добавить `p_build_eval_golden.add_argument("--live", action="store_true", help="живые агенты (Claude API) вместо HeuristicBaselineLLM")`, в ветке исполнения:

```python
            if args.live:
                llm = RunnerAgentLLM(_shared_live_runner)
                print("backend=%s + ЖИВАЯ модель (Claude API): числа — мера качества"
                      % os.environ.get("LEGALX_BACKEND", "mock"))
            else:
                llm = HeuristicBaselineLLM()
                print("backend=mock (LEGALX_BACKEND) + HeuristicBaselineLLM "
                      "(живого LLM-ключа нет — числа НЕ мера качества, только smoke)")
            report = run_eval(
                items, legalx=get_legalx_client(), llm=llm,
                valid_category_slugs=store.list_category_slugs(),
                backend=os.environ.get("LEGALX_BACKEND", "mock"), baseline=baseline,
            )
```

Тест: существующий тестовый контур cli (grep `eval-golden` в `importer/tests/`) + новый кейс «`--live` подставляет RunnerAgentLLM» через monkeypatch `_shared_live_runner`. Run pytest → PASS. Commit: `feat(importer): eval-golden --live — живые агенты вместо эвристики`.

- [ ] **Step 2: карта группы (стоп-точка ①), ≈ $0.4**

```bash
cd /Users/abduraxmonturdiyev/inspector-x-final && export IMPORTER_LLM_MAX_CALLS=60
.venv-importer/bin/python -m importer build map --group 2204 --jurisdiction UZ
```
Expected: `map=<uuid> group=2204 jurisdiction=UZ items=<N> status=draft` (первый живой Cartographer, expensive-тир `claude-opus-5`). Показать владельцу карту (`select expected_item, category_slug from pipeline.maps ...` на локальном Supabase — SQL-сниппет из `docs/RESEARCH_PIPELINE_STATUS.md`); после «да»:
`python -m importer build approve-map --map <uuid>` → `status=approved`.

- [ ] **Step 3: осторожный прогон 14 шагов (≈ $1.2)**

```bash
export IMPORTER_LLM_MAX_CALLS=250
.venv-importer/bin/python -m importer build run --map <uuid> --no-publish
.venv-importer/bin/python -m importer build status --run <run_id>
.venv-importer/bin/python -m importer build cost --run <run_id>
.venv-importer/bin/python -m importer build attention
```
Expected: `run=<id> total=<N> draft_loaded>=1 needs_attention` — разобрать каждый needs_attention (это очередь менеджера исключений, не мусор); `build cost` — суммарный `cost_usd` по ролям < $2 (иначе стоп и разбор до продолжения); в `IXV_CANDIDATES_DIR` появились rule-кандидаты для marking-айтемов. Публикация — ТОЛЬКО после ревью владельца: `python -m importer build publish --run <run_id>` (локальная база; прод-прогон — Задача 13, инструкция владельцу).

- [ ] **Step 4: eval-golden на живой модели (стоп-точка ②), ≈ $1.1**

```bash
IMPORTER_LLM_MAX_CALLS=80 .venv-importer/bin/python -m importer build eval-golden --live --limit 5
# числа осмысленные, стоимость по last_usage разумная -> полный набор (20 айтемов):
IMPORTER_LLM_MAX_CALLS=250 .venv-importer/bin/python -m importer build eval-golden --live
```
Expected: markdown-отчёт с retrieval_hit / verifier_agreement / category_accuracy / lifecycle_date_accuracy на живых агентах (backend=mock — retrieval ограничен фикстурами LegalX, зафиксировать это в выводе владельцу). После ревью чисел владельцем: `... build eval-golden --live --save-baseline` → `importer/golden/baseline.json` коммитится.

- [ ] **Step 5: Commit** — `git add importer/golden/baseline.json && git commit -m "chore(importer): живой baseline golden-набора после ревью владельца (стоп-точка ②)"`

---

### Task 12: Мониторинг вживую: process-changes и discovery на тестовом событии

**Деньги: ≈ $0.3, `IMPORTER_LLM_MAX_CALLS=40`.** Локальный Supabase; прод-cron не трогаем.

**Files:**
- Не меняет кода (использует Задачу 8). SQL — только на локальной базе.

**Interfaces:**
- Consumes: RPC `public.ingest_change_event(p_secret text, p_payload jsonb)` (миграция `20260804110000_ingest_change_event.sql`; секрет — Vault-ключ `legalx_webhook_secret`), CLI `monitor process-changes` / `monitor discovery`, цепочка `change_events → requirement_change_impacts → flagged_by_change → ре-ревью → user_notifications`.
- Produces: подтверждённый полный путь мониторинга на живой модели.

- [ ] **Step 1: завести секрет и тестовое событие в локальной базе**

Прочитать точные ключи payload: `sed -n '65,150p' supabase/migrations/20260804110000_ingest_change_event.sql` (jurisdiction / change_type / effective_date / act_id и обязательные поля). Затем через `psql` локального Supabase (порт из `supabase status`):

```sql
select vault.create_secret('wave2-test-secret', 'legalx_webhook_secret');
-- событие типа 'amended' по акту, на который ССЫЛАЕТСЯ существующее
-- published-требование (act_id взять: select act_id from requirement_citations
-- join requirements ... limit 1) — это путь (а) точного совпадения и путь (б)
-- LLM-классификатора на соседних кандидатах:
select public.ingest_change_event('wave2-test-secret', '{ ...payload по фактической схеме... }'::jsonb);
select id, event_type, title from public.change_events order by created_at desc limit 3;
```

- [ ] **Step 2: живой process-changes**

```bash
IMPORTER_LLM_MAX_CALLS=40 .venv-importer/bin/python -m importer monitor process-changes
```
Expected: `events_seen>=1 processed>=1`, `impacts_created>=1 requirements_flagged>=1 rereviews_enqueued>=1 notifications_sent>=1 revisions_recorded>=1`. Проверка SQL: `select count(*) from requirement_change_impacts;`, `select review_flag from requirements where id=...;`, `select kind, title from user_notifications order by created_at desc limit 3;`.

- [ ] **Step 3: живой discovery**

Вторым событием — `event_type='new'` без совпадающих требований (payload с новым act_id), затем:

```bash
IMPORTER_LLM_MAX_CALLS=40 .venv-importer/bin/python -m importer monitor discovery
```
Expected: `events_seen>=1 ... candidates_created>=1` — кандидаты появились в `pipeline.items` (`select expected_item, status from pipeline.items order by created_at desc limit 5;`).

- [ ] **Step 4: повторный запуск идемпотентен**

`python -m importer monitor process-changes` второй раз → `duplicates_skipped>=1`, `impacts_created=0` — событие не обрабатывается дважды. Ноль новых строк в `user_notifications`.

(Коммитов нет — задача проверочная; результаты — в отчёт сессии.)

---

### Task 13: Смоук всей цепочки и инструкции владельцу для прода

Один живой фотопрогон и один макетный через полный контур: RPC → воркер → финализация → отчётные таблицы; стоимость сверяется с `photo_model_calls`. Локально — исполняет агент; на проде — владелец по инструкции (агенту писать в прод-БД запрещено).

**Files:**
- Create: `/Users/abduraxmonturdiyev/inspector-x-final/scripts/photocontrol_smoke.py`

**Interfaces:**
- Consumes: локальный Supabase (service key из `supabase status`), воркер vision локально (`cd ~/inspectorx-vision && IXV_PORT=8010 ./ix serve`), RPC `request_photo_inspection` / `finalize_photo_inspection` (сигнатуры — из миграций Волны 1, Задача 1 Step 3), `POST /internal/inspect` воркера, `extraction.vlm: true` (Задача 6).
- Produces: скрипт сквозного смоука + печать инструкции владельцу.

- [ ] **Step 1: прочитать фактические контракты Волны 1**

```bash
grep -n "create or replace function public.request_photo_inspection\|create or replace function public.finalize_photo_inspection" -A 8 supabase/migrations/*photo*.sql
grep -n "internal/inspect" -B 3 -A 30 /Users/abduraxmonturdiyev/inspectorx-vision/src/ixvision/server.py | head -60
sed -n '1,60p' api/vision/check.ts
```
Зафиксировать: параметры RPC, тело запроса `/internal/inspect`, как `check.ts` мапит ответ воркера в финализацию (скрипт повторяет ровно этот маппинг).

- [ ] **Step 2: скрипт смоука**

`scripts/photocontrol_smoke.py` (запуск: `.venv-importer/bin/python scripts/photocontrol_smoke.py --kind photo|master_pdf`), структура — по фактическим контрактам Step 1:

```python
"""Сквозной смоук фотоконтроля на ЛОКАЛЬНОМ контуре (Волна 2, Задача 13).

Путь как в проде, минус браузер и Vercel: (1) тест-юзер через auth admin;
(2) файл в приватный бакет; (3) RPC request_photo_inspection под JWT юзера
(резерв квоты + idempotency_key); (4) POST /internal/inspect воркеру с
signed URLs (роль серверной функции играет этот скрипт — маппинг тот же,
что в api/vision/check.ts); (5) finalize_photo_inspection под service_role;
(6) сверка: status='done', cost_usd вердикта == sum(photo_model_calls.cost_usd),
degraded_mode пуст, у фотопути есть строки stage='vlm_shard' (и 'vlm_reask',
если переспрос был), у макетного пути строк photo_model_calls НЕТ (цена $0).
"""
```

Шаги внутри — supabase-py: `create_client(local_url, service_key)`, `auth.admin.create_user`, `storage.from_("packaging-photos").upload(...)`, `postgrest.rpc("request_photo_inspection", {...})` под клиентом с JWT юзера, `httpx.post("http://127.0.0.1:8010/internal/inspect", json={...}, headers={"X-Worker-Secret": ...})`, `rpc("finalize_photo_inspection", {...})` под service, ассерты `select` из `photo_inspections`/`photo_model_calls`/`photo_findings`. Вход: `data/photos/*.jpg` из vision для `--kind photo`, `data/fixtures/mackets/*.pdf` для `--kind master_pdf`.

- [ ] **Step 3: локальный прогон обоих путей (деньги: ≈ $0.01–0.02 фото, $0 макет)**

```bash
cd /Users/abduraxmonturdiyev/inspectorx-vision && IXV_PORT=8010 IXV_VLM_MAX_CALLS=160 ./ix serve &
cd /Users/abduraxmonturdiyev/inspector-x-final
.venv-importer/bin/python scripts/photocontrol_smoke.py --kind master_pdf   # $0, ноль строк photo_model_calls
.venv-importer/bin/python scripts/photocontrol_smoke.py --kind photo        # живой VLM
```
Expected: оба смоука печатают `SMOKE OK`: `photo_inspections.status='done'`, у фото `cost_usd > 0` и равен сумме `photo_model_calls.cost_usd` этой проверки, у макета `cost_usd = 0` и строк вызовов нет.

- [ ] **Step 4: инструкция владельцу для прод-смоука (агент в прод не пишет)**

Передать владельцу текст (и продублировать в отчёте сессии):

1. Vercel env: `WORKER_URL`, `WORKER_SECRET`, `SUPABASE_SERVICE_ROLE_KEY` заданы; Railway: сервис `vision-worker` жив (`/health` 200), переменные `GEMINI_API_KEY`, `OPENAI_API_KEY`, `IXV_VLM_MAX_CALLS=200`, `IXV_VLM_FALLBACK_DAILY_MAX=40`, **одна реплика**.
2. Браузером (прод, подписчик): `/checks/packaging` → выбрать товар (табак) → загрузить PDF-макет → дождаться отчёта; затем то же с 4 фото.
3. SQL в Supabase Dashboard (read-only сниппеты):
```sql
select id, status, source_kind, degraded_mode, cost_usd, ruleset_sha256
  from photo_inspections order by created_at desc limit 2;
select stage, provider, model, tokens_in, tokens_out, cost_usd
  from photo_model_calls where inspection_id = '<id фото-прогона>' order by stage;
select coalesce(sum(cost_usd), 0) from photo_model_calls
  where inspection_id = '<id фото-прогона>';   -- обязан совпасть с cost_usd проверки
select used, reserved, refunds_used from photo_quota where user_id = '<uid>';
```
Ожидания: макет — `cost_usd=0`, ноль строк вызовов; фото — стадии `vlm_shard` (+`vlm_reask` при переспросе), суммы сходятся, квота: `used` вырос на 2, `reserved=0`.

- [ ] **Step 5: Commit** — `git add scripts/photocontrol_smoke.py && git commit -m "feat(pipeline): сквозной смоук фотоконтроля — RPC, воркер, финализация, сверка стоимости"`

---

## Приёмка Волны 2

Все команды — из соответствующих корней репозиториев; ожидаемые числа:

| Проверка | Команда | Ожидание |
|---|---|---|
| Гейты на живых ответах | `IXV_VLM_CACHE_DIR=$PWD/runs/live_cache ./ix bench --assert missed_as_pass=0 --assert unsupported_decision=0` | exit 0; `runs/benchmark-live.json` закоммичен |
| Ложные тревоги | там же | не выросли против `runs/benchmark.json` (baseline main) |
| Деградация | `./ix test tests/test_fallback.py -q` + разовый живой тест Задачи 6 Step 4 | 3 ступени с пометкой `degraded_mode`; `failed`+возврат при недоступном чтеце |
| Привратник/переспрос | `./ix test tests/test_gatekeeper.py tests/test_reask.py -q` | PASS; рамки вне [0,100] → `[]`; переспрос ровно один |
| Воспроизводимость | `IXV_VLM_MAX_CALLS=140 ./ix repro tobacco_c2 20` | стоимость ≤ $0.20; `docs/REPRODUCIBILITY.md` с долей стабильных |
| Build live | `python -m importer build run --map <id> --no-publish` затем `build cost --run <id>` | `draft_loaded>=1`; cost прогона < $2; rule-кандидаты в `candidates/` |
| Golden live | `python -m importer build eval-golden --live` | 20/20 айтемов; `baseline.json` сохранён после ревью |
| Мониторинг | `python -m importer monitor process-changes` (локальная база, тест-событие) | `impacts_created>=1, requirements_flagged>=1, notifications_sent>=1`; повтор — `duplicates_skipped>=1` |
| Смоук контура | `scripts/photocontrol_smoke.py --kind master_pdf` и `--kind photo` | `SMOKE OK`; `sum(photo_model_calls.cost_usd) == photo_inspections.cost_usd`; макет $0 |
| Бюджет волны | `runs/vlm_calls.json` + `build cost` по всем прогонам | суммарно < $5 |
| Тесты обоих репо | `./ix test -q` и `pytest importer/tests -q` | PASS, без сети |

## Открытые вопросы (решает владелец / сессия исполнения)

1. **Фактическое имя фича-флага VLM у Волны 1** — план канонизирует `extraction.vlm`; Задача 1 Step 4 фиксирует реальность, Задача 2 Step 1 приводит к канону.
2. **`LEGALX_BACKEND=mock` на живых прогонах Build** — retrieval_hit golden-набора ограничен фикстурами; живой LegalX (D1/D2) — внешняя зависимость вне Волны 2. Числа baseline подписываются с этой оговоркой.
3. **PR-флоу rule-кандидатов** — по умолчанию файл-кандидат в `config/requirements/candidates/`; `RULE_CANDIDATE_PR=1` открывает PR через `gh` (памятка: `gh pr merge` блокируется классификатором — мёрж всегда руками владельца).
4. **Формулировка плашки «сокращённый режим»** в UI отчёта (данные `degraded_mode` уже едут) — текст в `src/i18n/ru.ts` согласовать с владельцем; в Волне 2 плашка минимальная.
5. **Intro-прайс claude-sonnet-5** ($2/$10 до 2026-08-31) — в `models.yaml` заложен полный прайс $3/$15; фактический счёт будет ниже оценок.
