# Фотоконтроль упаковки — Волна 1: детерминированное ядро. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** построить всё детерминированное ядро фотоконтроля упаковки — мёржи фундамента, пакетирование воркера, три эндпоинта, миграции рантайма и storage, Vercel-границу, фронт от выбора товара до отчёта, детерминированный фотопуть, self-host OCR с привратником, канал правки факта, правила-как-данные и жизненный цикл — без единого живого LLM-вызова и без внешних вендоров.

**Architecture:** «Тонкий мост» (нормативный план `docs/PHOTOCONTROL_INTEGRATION_PLAN.md`, редакция 2): витрина InspectorX (Vite/React + Supabase) + один Vision-воркер (FastAPI на Railway, в Волне 1 — локальный Docker). Воркер — чистая функция «файлы + прежние факты → вердикт», в базу не пишет ничего и ключей Supabase не держит; единственный писатель — Vercel-функции под service_role через SECURITY DEFINER RPC. Судит только детерминированный `rule_engine`; модели поставляют факты. Правило двух ключей (утверждение об отсутствии выносит только чтец: pdf_text / ocr / zbar / human) уже реализовано в движке — Волна 1 его не ослабляет ни в одной точке.

**Tech Stack:** Python 3.14 (FastAPI, pdfminer.six, pypdfium2, EasyOCR + PaddleOCR, ultralytics/YOLO, pyzbar, pillow-heif), TypeScript (Vercel Node functions, React 19, TanStack Query, vitest), Postgres/Supabase (RLS, pg_cron, pg_net, Vault, Storage), Docker.

**Нормативные источники (читать при сомнении, они главнее этого плана):**
- `/Users/abduraxmonturdiyev/inspector-x-final/docs/PHOTOCONTROL_INTEGRATION_PLAN.md` — §4 таблицы и поток, §5 комбинация моделей, §6 ретраи, §10 этапы;
- `/Users/abduraxmonturdiyev/inspector-x-final/docs/PHOTOCONTROL_PLAN_FIXLOG.md` — разбор критика;
- `/Users/abduraxmonturdiyev/inspectorx-vision/docs/PHOTOCONTROL_DECISIONS.md` (в ветке stage1 до Задачи 1) — 14 решений владельца;
- `/Users/abduraxmonturdiyev/inspector-x-final/docs/superpowers/plans/2026-08-06-photocontrol-wave3-people-and-vendors.md` — Волна 3 (секреты, вендоры, люди): деплой-шаги этого плана гейтятся её задачами А1–А6.

---

## Что уже построено — НЕ строить заново (проверено по коду 06.08.2026)

Параллельная сессия увела `main` репозитория `inspectorx-vision` на 22 коммита вперёд от merge-base `78a3f4c` и построила макетный путь целиком. Исполнитель обязан знать, что из нормативного плана УЖЕ существует:

| Обещано планом (§) | Уже есть в vision `main` | Где |
|---|---|---|
| Правило двух ключей, `_reader_coverage`-аналог (§5) | ЕСТЬ: `absence_requires_reader: strict` (дефолт), `_reader_pool` / `_reader_support` / `_reading_gap`, ветки `PASS 0.7`/`FAIL 0.6` живы только под `off` | `src/ixvision/engines/rule_engine.py:1218,1470,1379,2194,1995` |
| `Finding.decided_by`, `Claim`, `BasisKind` (§5 п.8) | ЕСТЬ, `evaluate` заполняет | `src/ixvision/models.py:395-452` |
| Макетный путь: pdfminer + MediaBox + кегль в мм (§4) | ЕСТЬ: `inspect_artwork`, `vision/artwork.py` (938 строк), `has_text_layer` — гейт до суда | `src/ixvision/pipeline.py`, `vision/artwork.py` |
| Растеризация макета + OCR по растру (§4) | ЕСТЬ: `vision/raster.py` (pypdfium2, 400 dpi), читается тем же OCR (коммиты 9ce8184, ac8f2b2) | `vision/raster.py`, `config/routing.yaml: artwork_raster` |
| Self-host OCR, слова+полигоны+уверенность, source=ocr, SOURCE_RANK ocr=3 (§5) | ЕСТЬ: `vision/ocr.py` — **EasyOCR** (`ru+en`, узбекская латиница тем же проходом), `ReaderWord`, `reader_facts`, `merge_reader` | `src/ixvision/vision/ocr.py` (509 строк), `facts.py:43` |
| Переписанный `benchmark.py`: `missed_as_pass`, `unsupported_decision`, `decisiveness` по путям (§8) | ЕСТЬ, все метрики + `--assert` на любой числовой ключ `totals` | `scripts/benchmark.py`, `runs/benchmark.json` |
| zbar-декодер → факты (§5) | ЕСТЬ: `vision/local_facts.py` (`decode_codes`, `decoded_code_facts`, `yolo_zone_facts`) | `src/ixvision/vision/local_facts.py` |
| `GET /api/checklist` воркера (§4) | ЕСТЬ в `server.py` | `src/ixvision/server.py` |

Ветка `photocontrol-stage1` (6 коммитов, НЕ смержена) несёт: CI-workflow, `ruff.toml`, `requirements-ci.txt`, линтер `params` с ratchet-baseline (76 ключей), сценарные фикстуры `tests/scenarios/tobacco.yaml` (111 кейсов) + `tests/scenario_runner.py`, первую многокадровую серию `tobacco_c3` (4 кадра), фикс `photo_hints` из `levels.<level>` + кэш `load_all_packs`, `docs/PHOTOCONTROL_DECISIONS.md`.

Ветка `worktree-photocontrol` витрины (5 коммитов, НЕ смержена, merge-base = текущий `main` `fec8be0`): CI-workflow витрины, `npm run typecheck`/`test` + vitest + первый фронт-тест, ссылка на `api/tsconfig.json` в корневом `tsconfig.json`, фиксы importer (вакуальный pass, шаг rule → no-op), миграция `20260806130000_deprecate_requirement_rules.sql` (только comment), пять поправок ADR, копия нормативного плана.

**Чего НЕТ нигде (это и есть Волна 1):** pyproject/Dockerfile/paths.py/весов в git, эндпоинтов `/internal/*`, канала прогресса, всех таблиц `photo_*` и `ruleset_versions`, Vercel-функций `api/vision/*`, фронта проверки, per-кадровых `face_name`/`text_legible`, привратника (Левенштейн), чтения `params.surface`/`params.language` движком, PaddleOCR-бэкенда, кропов-доказательств, канала правки факта, `requirement_photo*`, `stale_since`.

---

## Global Constraints

Каждая задача обязана соблюдать всё перечисленное; нарушение — провал задачи.

- **Мёрж в `main` витрины автоматически накатывает миграции Supabase на прод БЕЗ отката** (GitHub-интеграция). Миграции кладутся в `main` только готовыми и проверенными на локальном стеке (`supabase db start && supabase db reset --local`). Политики storage-бакетов проверяются локально попыткой чтения чужого префикса (Задача 9) ДО мёржа.
- **pg_cron на проде включается в Dashboard, не через `create extension`** (записано в `20260804100000_lifecycle_cron.sql:24-27`). То же для `pg_jsonschema` (Задача 15). Оба пункта — гейт А6 Волны 3; до его закрытия миграции Волны 1 в `main` витрины НЕ мёржатся (работаем в ветке `photocontrol-wave1`).
- **Деплой воркера на Railway и env-переменные Vercel требуют секретов из Волны 3** (задачи А1–А4). До этого — только локальный Docker (`docker build` + `docker run`) и локальный Supabase; все деплой-шаги в задачах помечены «(Волна 3)».
- **Живого LLM-ключа нет и не будет в Волне 1.** Ни один тест и ни один шаг не имеет права ходить в сеть к VLM: экстрактор — только `cache`/`stub` (`make_extractor("cache", live=False)`), тесты OCR скипаются при отсутствии движка (существующий паттерн `test_ocr.py`).
- **Гейты CI не ослабляются никогда:** `missed_as_pass=0`, `unsupported_decision=0` (pytest-гейты `tests/test_benchmark_gates.py`), линтер `params` (ratchet — новые нарушения запрещены, протухшие строки baseline удаляются). CI обоих репозиториев зелёный после каждой задачи.
- **Пересборка YAML-пакетов затирает ручные правки** (`./ix build` регенерирует `config/requirements/*.yaml`) — в Волне 1 `./ix build` НЕ запускать. Правка пакетов инвалидирует VLM-кэш (`data/vlm_cache/`, ключи зависят от схемы) — после любой правки `config/requirements/*.yaml` прогнать `./ix bench` и закоммитить новый `runs/benchmark.json` вместе с правкой.
- **Правило двух ключей не ослабляется:** `config/policy.yaml` ключи `absence_requires_reader`, `unfound_element` не трогать; изменение любого ключа политики без сопутствующего изменения эталона — провал ревью.
- **Python витрины:** `.venv-importer/bin/python -m pytest importer/tests -q` (552+ теста). **Python vision:** `./ix test` (= `python -m pytest tests -q`, `PYTHONPATH=src`); сейчас venv — симлинк на соседний проект, после Задачи 3 — свой `.venv`.
- **Фронт-тесты — vitest** (появился в ветке worktree-photocontrol): `npm run test`. Типы: `npm run typecheck`. Линт: `npm run lint`.
- **PyMuPDF запрещён** (AGPL). PDF-стек: pypdfium2 (Apache-2.0) + pdfminer.six (MIT).
- **Воркер не имеет доступа к базе:** ни ключей Supabase, ни соединения. Всё, что он хочет сообщить, — через `POST {VERCEL_URL}/api/vision/progress` с `X-Worker-Secret`; пишет только сервер витрины.
- **Вердикт append-only:** у `photo_inspections`/`photo_findings`/`photo_not_checkable` нет UPDATE-политик; изменения — новая ревизия со ссылкой `superseded_by`; служебные переходы статуса — только внутри SECURITY DEFINER-функций.
- **Отсутствие данных ≠ «нарушений нет»:** пустой чек-лист, товар без профиля, нулевое покрытие — всегда явный текст, никогда не пустой зелёный экран.
- Язык: текст и комментарии — русский; код, идентификаторы, имена файлов — английский; коммиты — conventional commits по-русски (`feat(vision): …`).
- Все строки UI фронта — только в `src/i18n/ru.ts` (секция `ru.packagingCheck`, плоские ключи); хардкод текста в компонентах запрещён.
- Данные фронта — только через `src/data/hooks.ts` → `src/data/index.ts`; прямые запросы Supabase из компонентов запрещены.
- Известные git-грабли: `gh pr merge` блокируется классификатором → `git merge --no-ff` + `git push origin main`; «Repository not found» → `gh auth switch --user TAVI-Agency`. Репозиторий `inspectorx-vision` **не имеет remote** (проверено `git remote -v`) — его мёржи локальные, push не требуется.

---

## Карта задач и параллелизация

Порядок задач = порядок исполнения. Две независимые полосы после мёржей:

```
Task 1 (мёрж vision) ─┬→ Task 3 (пакетирование) → Task 4 (движок: фотопуть) → Task 5 (движок: OCR/привратник/язык)
                      │                            └→ Task 6 (ruleset-реестр) → Task 7 (эндпоинты воркера)
Task 2 (мёрж витрины) ─┬→ Task 8 (миграция runtime) → Task 9 (миграция storage) → Task 10 (Vercel-функции)
                       │                               └→ Task 11 (слой данных) → Task 12 (экран проверки) → Task 13 (отчёт)
Task 14 (этап 5: кропы/правка/подпись)  ← после 7, 10, 13
Task 15 (этап 6: правила как данные)    ← после 1, 8 (vision-часть — после 3)
Task 16 (этап 7: жизненный цикл)        ← после 8 (независима от 14–15)
```

Параллелить сабагентами можно: {1, 2}; {3, 8}; {4, 9}; {5, 6 — в vision, но разные файлы: 5 трогает `ocr.py`/`gatekeeper.py`/`rule_engine.py`, 6 — `ruleset.py`/`server.py`}; {10, 11}; {15, 16}. Нельзя параллелить: 4 и 5 (оба правят `rule_engine.py`, `facts.py`, `pipeline.py`), 12 и 13 (общие компоненты).

Работа ведётся: vision — прямо в `main` (репо без remote, локальное); витрина — в ветке `photocontrol-wave1` от `main`, мёрж в `main` только после закрытия гейта А6 Волны 3 (pg_cron/pg_jsonschema в Dashboard) и полной приёмки миграций локально.

---

### Task 1: Мёрж photocontrol-stage1 → main в inspectorx-vision

**Files:**
- Repo: `/Users/abduraxmonturdiyev/inspectorx-vision` (без remote, всё локально)
- Конфликтные (ровно 3, проверено `git merge-tree`): `data/eval/sets.yaml`, `runs/benchmark.json`, `tests/test_benchmark_gates.py`
- Modify после мёржа: `requirements-ci.txt`, `scripts/lint_params_baseline.json` (перегенерация при протухании)

**Interfaces:**
- Produces: `main` vision содержит одновременно макетный путь (22 коммита) и наследие stage1 (CI, линтер, фикстуры, multiframe-серия, кэш пакетов, `ProductProfile.photo_hints(level)`); `./ix test` зелёный; `python scripts/lint_params.py` зелёный.
- Consumes: ничего (первая задача).

- [ ] **Step 1: Зафиксировать рабочее дерево и начать мёрж**

```bash
cd /Users/abduraxmonturdiyev/inspectorx-vision
git status --short          # M runs/benchmark.json + untracked data/vlm_cache/*, runs/vision_duel.json
git stash push -u -m "pre-merge scratch"   # незакоммиченный замер и кэш — в сторону
git checkout main
git merge --no-ff photocontrol-stage1
# Ожидаемо: CONFLICT в data/eval/sets.yaml, runs/benchmark.json, tests/test_benchmark_gates.py
```

- [ ] **Step 2: Разрешить `data/eval/sets.yaml` — шапка main + серия tobacco_c3 из stage1**

Взять версию `main` целиком (в ней 5 фотосерий + 6 макетов и актуальная шапка про два входа), затем дописать в конец списка `sets:` блок серии `tobacco_c3` дословно из stage1:

```bash
git checkout --ours data/eval/sets.yaml
git show photocontrol-stage1:data/eval/sets.yaml | sed -n '/id: tobacco_c3/,/tobacco__008/p'
```

Вставить полученный блок (id `tobacco_c3`, product `tobacco`, level `consumer`, `why` про первую многокадровую серию, 4 файла `data/photos/tobacco/tobacco__005..008_Captain_Black_Blue_Cigarette_Pack_0{1..4}.jpg`) последним элементом `sets:` с тем же отступом, что у соседних серий. ВАЖНО: сами 4 файла в git отсутствуют (`data/photos/*/*.jpg` в `.gitignore`) — это нормально, см. Step 4.

- [ ] **Step 3: Разрешить `tests/test_benchmark_gates.py` — база main + гейт непустоты из stage1 как skip-aware тест**

Взять версию `main` целиком (она надстроена над макетным путём: `BASELINE` с `false_alarms: 12`, `ALLOWED_FALSE_ALARMS`, тест «прочитавший обязан цитировать»):

```bash
git checkout --ours tests/test_benchmark_gates.py
```

Затем добавить в конец файла новый тест — намерение stage1 («ноль гейта не должен быть пустым на ФОТОпути»), переписанное под реальность main, где чтец уже покрывает грани на макетах, но не на фото:

```python
def test_photo_reference_set_contains_a_multiframe_series():
    """Наследие stage1 (19a3602): в эталоне обязана быть фотосерия из 4+ кадров
    одной упаковки — иначе ветки полного покрытия не исполняются ни разу и
    ноль гейта missed_as_pass на фотопути пуст. Файлы кадров не в git
    (data/photos в .gitignore), поэтому проверяем ДЕКЛАРАЦИЮ набора, а не байты."""
    sets_doc = yaml.safe_load((ROOT / "data" / "eval" / "sets.yaml").read_text())
    multi = [s for s in sets_doc["sets"] if len(s.get("photos", [])) >= 4]
    assert multi, (
        "в data/eval/sets.yaml не осталось серии из 4+ кадров — "
        "верните tobacco_c3 или её замену"
    )
```

(`ROOT` и `yaml` в файле main уже импортированы; если `ROOT` называется иначе — взять существующую константу пути из шапки файла.)

- [ ] **Step 4: Разрешить `runs/benchmark.json` перезамером**

```bash
git checkout --ours runs/benchmark.json   # временно, чтобы завершить мёрж
git add data/eval/sets.yaml runs/benchmark.json tests/test_benchmark_gates.py
git commit --no-edit
```

Затем перезамер на объединённом наборе. Если 4 кадра Captain Black есть локально (`ls data/photos/tobacco/ | grep Captain`) — bench включит tobacco_c3; если файлов нет, bench обязан не падать, а серию пропустить (проверить поведение; если падает — временно закомментировать серию нельзя, вместо этого добавить в `scripts/benchmark.py` пропуск серии с отсутствующими файлами с печатью `skipped: tobacco_c3 (нет файлов)` — это отдельный мини-фикс в этом же шаге):

```bash
./ix bench --assert missed_as_pass=0 --assert unsupported_decision=0
git add runs/benchmark.json scripts/benchmark.py
git commit -m "chore(bench): перезамер после сшивки stage1 с макетным путём"
```

- [ ] **Step 5: Починить `requirements-ci.txt` под объединённый main**

Stage1-файл не знает макетного пути — CI упадёт на импортах `pdfminer`/`pypdfium2`/`easyocr`. Дописать (версии — фактические из локального окружения, проверено 06.08.2026):

```
pdfminer.six==20260107
pypdfium2==5.12.1
easyocr==1.7.2
```

- [ ] **Step 6: Прогнать линтер params и тесты; при протухшем baseline — перегенерировать осознанно**

```bash
python scripts/lint_params.py
# если упал на ПРОТУХШИХ строках (main правил dairy.yaml после ответвления stage1):
python scripts/lint_params.py --write-baseline
git diff scripts/lint_params_baseline.json   # глазами: только УДАЛЕНИЯ строк допустимы;
                                             # ни одного НОВОГО ключа появиться не должно
./ix test
```

Expected: `./ix test` — все тесты зелёные (main давал 399 тестов + stage1 добавляет test_lint_params, test_scenarios; суммарно ≥ 410 passed, skipped допустимы только easyocr/zbar/paddle).

- [ ] **Step 7: Commit**

```bash
git add requirements-ci.txt scripts/lint_params_baseline.json
git commit -m "fix(ci): манифест CI и baseline линтера догнали объединённый main"
git stash pop   # вернуть отложенный локальный замер (не коммитить)
```

---

### Task 2: Мёрж worktree-photocontrol → main в inspector-x-final и ветка Волны 1

**Files:**
- Repo: `/Users/abduraxmonturdiyev/inspector-x-final`, worktree ветки: `.claude/worktrees/photocontrol`
- Затрагивает: `.github/workflows/ci.yml`, `package.json`, `tsconfig.json`, `importer/build/{coverage,steps_rule}.py`, `supabase/migrations/20260806130000_deprecate_requirement_rules.sql`, docs

**Interfaces:**
- Produces: `main` витрины содержит CI, vitest, typecheck (включая `api/`), фиксы importer, поправки ADR; создана рабочая ветка `photocontrol-wave1`, в которой живут все последующие задачи витрины (8–16).
- Consumes: ничего.

- [ ] **Step 1: Проверить ветку перед мёржем — CI-команды локально**

```bash
cd /Users/abduraxmonturdiyev/inspector-x-final/.claude/worktrees/photocontrol
npm ci && npm run lint && npm run typecheck && npm run test
.venv-importer/bin/python -m pytest importer/tests -q 2>/dev/null \
  || /Users/abduraxmonturdiyev/inspector-x-final/.venv-importer/bin/python -m pytest importer/tests -q
```

Expected: lint/typecheck/test зелёные; pytest — 552+ passed (integration скипаются без локального Supabase).

- [ ] **Step 2: Мёрж в main (merge-base = HEAD main → конфликтов нет) и push**

Миграция `20260806130000_deprecate_requirement_rules.sql` уедет на прод автоматически — она безопасна (единственный `comment on table`, данных не трогает).

```bash
cd /Users/abduraxmonturdiyev/inspector-x-final
git checkout main
git merge --no-ff worktree-photocontrol -m "Merge worktree-photocontrol: CI витрины, vitest, фиксы importer, поправки ADR (этап 1 фотоконтроля)"
git push origin main
# при «Repository not found»: gh auth switch --user TAVI-Agency && git push origin main
```

- [ ] **Step 3: Проверить прод-эффекты мёржа**

```bash
gh run list --limit 3        # первый прогон нового CI: должен стартовать и позеленеть
```

Vercel задеплоит `main` сам (docs-и и CI на бандл не влияют). Если job `db-lint` CI упал на `supabase db start` в Actions — допустимо на первом прогоне починить постфиксом (например, поднять таймаут), но не удалять job.

- [ ] **Step 4: Создать рабочую ветку Волны 1**

Все задачи витрины (8–16) коммитятся сюда; мёрж этой ветки в `main` — только после «Приёмки Волны 1» и закрытия гейта А6 Волны 3 (pg_cron + pg_jsonschema включены в Dashboard прода).

```bash
git checkout -b photocontrol-wave1
git push -u origin photocontrol-wave1
```

- [ ] **Step 5: Commit-маркер начала волны**

```bash
git commit --allow-empty -m "chore(photocontrol): старт Волны 1 — детерминированное ядро"
git push
```

---

### Task 3: Пакетирование vision: pyproject.toml, paths.py, веса через git-lfs, Dockerfile

**Files:**
- Create: `pyproject.toml`, `src/ixvision/paths.py`, `Dockerfile`, `.dockerignore`, `models/` (каталог с весами), `tests/test_paths.py`
- Modify: `src/ixvision/env.py` (вырезать соседский путь), `src/ixvision/vision/preprocess.py:50-53` (`_MODEL_PATHS`), `src/ixvision/engines/rule_engine.py` (`_POLICY_PATH`), `src/ixvision/compiler/checklist.py` (`REQUIREMENTS_DIR`), `scripts/setup.sh`, `ix` (fallback на соседний venv удалить), `.gitattributes`, `.gitignore`

**Interfaces:**
- Produces:
  - `ixvision.paths.config_dir() -> Path`, `state_dir() -> Path`, `work_dir() -> Path`, `weights_path() -> Path` — единая точка путей; env-переменные `IXV_CONFIG_DIR`, `IXV_STATE_DIR`, `IXV_WORK_DIR`, `IXV_WEIGHTS`;
  - `pip install -e .` собирает пакет; `docker build` собирает образ; запуск без весов и без `IXV_ALLOW_NO_DETECTOR=1` падает при старте сервера.
- Consumes: Task 1 (объединённый main).

- [ ] **Step 1: Failing test на paths**

`tests/test_paths.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ixvision import paths


def test_defaults_point_inside_repo(monkeypatch):
    for var in ("IXV_CONFIG_DIR", "IXV_STATE_DIR", "IXV_WORK_DIR", "IXV_WEIGHTS"):
        monkeypatch.delenv(var, raising=False)
    root = Path(__file__).resolve().parents[1]
    assert paths.config_dir() == root / "config"
    assert paths.state_dir() == root / "runs"
    assert paths.work_dir() == root / "data"
    assert paths.weights_path() == root / "models" / "best.pt"


def test_env_overrides_win(monkeypatch, tmp_path):
    monkeypatch.setenv("IXV_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("IXV_WEIGHTS", str(tmp_path / "w.pt"))
    assert paths.config_dir() == tmp_path / "cfg"
    assert paths.weights_path() == tmp_path / "w.pt"


def test_no_neighbour_repo_paths_left():
    """Ни одного жёсткого пути на соседний репозиторий в исходниках."""
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for p in list((root / "src").rglob("*.py")) + [root / "ix", root / "scripts" / "setup.sh"]:
        if "Projects/personal" in p.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(str(p))
    assert offenders == []
```

- [ ] **Step 2: Run — убедиться, что падает**

Run: `./ix test tests/test_paths.py -v`
Expected: FAIL — `ModuleNotFoundError: ixvision.paths` и offenders в `env.py`, `preprocess.py`, `ix`, `setup.sh`.

- [ ] **Step 3: Реализовать `src/ixvision/paths.py`**

```python
"""Одна точка путей вместо семи вычислений Path(__file__).parents[...].

Env-переменные (для Docker/Railway):
  IXV_CONFIG_DIR — конфиги (config/), IXV_STATE_DIR — изменяемое состояние (runs/),
  IXV_WORK_DIR — данные (data/), IXV_WEIGHTS — файл весов YOLO (models/best.pt).
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _from_env(var: str, default: Path) -> Path:
    value = os.environ.get(var, "")
    return Path(value) if value else default


def config_dir() -> Path:
    return _from_env("IXV_CONFIG_DIR", REPO_ROOT / "config")


def state_dir() -> Path:
    return _from_env("IXV_STATE_DIR", REPO_ROOT / "runs")


def work_dir() -> Path:
    return _from_env("IXV_WORK_DIR", REPO_ROOT / "data")


def weights_path() -> Path:
    return _from_env("IXV_WEIGHTS", REPO_ROOT / "models" / "best.pt")


def allow_no_detector() -> bool:
    return os.environ.get("IXV_ALLOW_NO_DETECTOR", "") == "1"
```

Затем переключить потребителей:
- `env.py`: удалить строку `Path.home() / "Projects/personal/active/inspector-vision/.env"` из `ENV_FILES` (остаются `.env` и `.env.local` репозитория);
- `preprocess.py`: `_MODEL_PATHS = [paths.weights_path()]` (импорт `from ixvision import paths`); в `warmup()` — если весов нет и `not paths.allow_no_detector()`: `raise RuntimeError("нет весов YOLO (models/best.pt) и не выставлен IXV_ALLOW_NO_DETECTOR=1 — молчаливая деградация запрещена")`; существующая мягкая деградация (`detector_error()`) остаётся только под флагом;
- `rule_engine.py`: `_POLICY_PATH = paths.config_dir() / "policy.yaml"` (вместо `parents[3]`);
- `compiler/checklist.py`: `REQUIREMENTS_DIR = paths.config_dir() / "requirements"`, каталог продуктов — `paths.config_dir() / "products"`;
- `ix`: убрать fallback `NEIGHBOUR=...` (нет venv → только «Запустите: bash scripts/setup.sh»); `setup.sh`: убрать симлинк на соседний venv, создавать свой: `python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"`.

- [ ] **Step 4: `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "ixvision"
version = "0.1.0"
description = "InspectorX vision worker: детерминированная проверка упаковки"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.141",
  "uvicorn>=0.52",
  "python-multipart>=0.0.32",
  "httpx>=0.28",
  "openai>=2.52",
  "pydantic>=2.13",
  "pyyaml>=6.0",
  "opencv-python-headless>=5.0",
  "ultralytics>=8.4",
  # torch ставится с CPU-индекса (см. Dockerfile: --extra-index-url pytorch.org/whl/cpu)
  "torch>=2.13",
  "pyzbar>=0.1.9",
  "numpy>=2.5",
  "pypdfium2>=5.12",          # Apache-2.0; PyMuPDF (AGPL) запрещён
  "pdfminer.six>=20260107",   # MIT
  "pillow>=12.3",
  "pillow-heif>=1.1",         # HEIC/HEIF с айфона
  "easyocr>=1.7.2",
]

[project.optional-dependencies]
paddle = ["paddleocr>=3.0", "paddlepaddle>=3.0"]   # self-host PP-OCR (Задача 5)
dev = ["pytest>=9.1", "ruff>=0.16"]

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 5: Веса в git-lfs**

```bash
cd /Users/abduraxmonturdiyev/inspectorx-vision
brew list git-lfs >/dev/null 2>&1 || brew install git-lfs
git lfs install
git lfs track "*.pt"                       # допишет .gitattributes
mkdir -p models
cp ~/Projects/personal/active/inspector-vision/models/best.pt models/best.pt   # 5.5 МБ, yolo11n, 12 классов
git add .gitattributes models/best.pt
```

- [ ] **Step 6: Dockerfile + .dockerignore**

`Dockerfile`:

```dockerfile
FROM python:3.14-slim

# libzbar0 — pyzbar (декодер кодов); libgl1+libglib2.0-0 — opencv
RUN apt-get update && apt-get install -y --no-install-recommends \
      libzbar0 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu ".[paddle]"

COPY config /app/config
COPY models /app/models

ENV IXV_CONFIG_DIR=/app/config \
    IXV_WEIGHTS=/app/models/best.pt \
    IXV_STATE_DIR=/tmp/ixv-state \
    IXV_WORK_DIR=/tmp/ixv-work \
    IXV_OCR_DOWNLOAD=1

EXPOSE 8010
CMD ["uvicorn", "ixvision.server:app", "--host", "0.0.0.0", "--port", "8010"]
```

`.dockerignore`: `.venv`, `data/`, `runs/`, `tests/`, `docs/`, `.git`, `__pycache__`.

- [ ] **Step 7: Run tests + сборка**

```bash
bash scripts/setup.sh          # свой .venv
./ix test                      # весь набор зелёный, test_paths.py проходит
docker build -t ixvision:wave1 .                                  # локальная проверка
docker run --rm -e IXV_ALLOW_NO_DETECTOR= ixvision:wave1 python -c "from ixvision.vision.preprocess import warmup; warmup()" \
  ; echo "exit=$?"             # с весами в образе — exit=0
```

Expected: тесты зелёные; образ собирается; старт без весов (`docker run -e IXV_WEIGHTS=/nonexistent ...`) падает с текстом про `IXV_ALLOW_NO_DETECTOR`. Деплой образа на Railway — (Волна 3, задача А2).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml Dockerfile .dockerignore src/ixvision/paths.py tests/test_paths.py \
        src/ixvision/env.py src/ixvision/vision/preprocess.py src/ixvision/engines/rule_engine.py \
        src/ixvision/compiler/checklist.py ix scripts/setup.sh .gitignore
git commit -m "feat(packaging): pyproject, paths.py, веса в git-lfs, Dockerfile — репозиторий самодостаточен"
```

### Task 4: Движок: детерминированный фотопуть (per-кадр грань, YOLO-рамка, отбраковка bbox, surface, prior_facts)

**Files:**
- Modify: `src/ixvision/facts.py` (поля `PhotoFact`, `apply_overrides`, сериализация паспорта), `src/ixvision/vision/preprocess.py` (EXIF + HEIC + загрузка через PIL), `src/ixvision/vision/local_facts.py` (`face_bbox_facts`), `src/ixvision/engines/extractor.py` (`_clamp_bbox` → отбраковка), `src/ixvision/engines/rule_engine.py` (`Finding.surface` заполняется, рамка грани от YOLO), `src/ixvision/pipeline.py` (`prior_facts`/`reuse_facts`, per-кадр legibility)
- Test: `tests/test_photo_frames.py`, `tests/test_prior_facts.py`; правки в `tests/test_extractor.py`

**Interfaces:**
- Consumes: Task 1 (сценарный раннер, объединённый движок), Task 3 (`ixvision.paths`).
- Produces (нужны Задачам 5, 7):
  - `PhotoFact` получает поля: `face_name: str = "unknown"`, `text_legible: Literal["yes","partial","no"] = "no"`, `face_bbox_pct: list[float] = []`, `face_bbox_source: str = ""` (`yolo|vlm|""`), `languages: list[str] = []`;
  - `facts.passport_rows(passport: FactPassport) -> list[dict]` и `facts.passport_from_rows(rows: list[dict]) -> FactPassport` — построчная сериализация для таблицы `photo_facts` (слоты texts/elements по строке на слот + служебные строки `__scan__`, `__reader__`, `__codes__`, `__photos__` с `source='system'`);
  - `facts.apply_overrides(passport, overrides: list[dict]) -> FactPassport` — правки человека, источник `"человек"` (SOURCE_RANK 5);
  - `local_facts.face_bbox_facts(series) -> dict[int, list[float]]` — рамка грани per-кадр от YOLO `label_zone`;
  - `pipeline.inspect(..., prior_facts: FactPassport | None = None, fact_overrides: list[dict] | None = None, reuse_facts: bool = False, on_stage: Callable[[str, dict], None] | None = None)`;
  - `pipeline.inspect_artwork(..., on_stage: ... | None = None)`.

- [ ] **Step 1: Failing tests — per-кадр факты и отбраковка рамок**

`tests/test_photo_frames.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ixvision.facts import FactPassport, PhotoFact, ReaderFact, ReaderWord
from ixvision.pipeline import fill_frame_reading


def _passport_with_reader(word_counts: dict[int, int]) -> FactPassport:
    p = FactPassport()
    p.photos = [PhotoFact(index=i, path=f"{i}.jpg", sha256=f"{i:064d}", width=100, height=100)
                for i in word_counts]
    words = []
    for idx, n in word_counts.items():
        words += [ReaderWord(text=f"w{idx}{k}", source="ocr", conf=0.9, asset_index=idx)
                  for k in range(n)]
    p.reader = ReaderFact(words=words, engine="easyocr:ru+en")
    return p


def test_text_legible_is_per_frame_and_deterministic():
    p = _passport_with_reader({0: 5, 1: 1, 2: 0})
    fill_frame_reading(p, faces=["front_panel", "back_panel", "side_panel"],
                       min_words=3, min_conf=0.5)
    assert [f.text_legible for f in p.photos] == ["yes", "partial", "no"]
    assert [f.face_name for f in p.photos] == ["front_panel", "back_panel", "side_panel"]


def test_face_name_falls_back_to_frame_index_when_not_declared():
    p = _passport_with_reader({0: 5})
    fill_frame_reading(p, faces=None, min_words=3, min_conf=0.5)
    assert p.photos[0].face_name == "frame_0"
```

Дополнить `tests/test_extractor.py` (файл существует, добавляем в конец):

```python
def test_bbox_out_of_range_is_rejected_not_clamped():
    from ixvision.engines.extractor import _strict_bbox
    assert _strict_bbox([0, 0, 100, 100]) == [0.0, 0.0, 100.0, 100.0]
    assert _strict_bbox([-5, 0, 100, 100]) == []      # раньше зажималось в 0
    assert _strict_bbox([840, 60, 1900, 210]) == []   # пиксельные координаты — мусор
    assert _strict_bbox([60, 60, 60, 90]) == []       # вырожденная: x1 == x2
    assert _strict_bbox([90, 10, 10, 90]) == []       # вывернутая: x1 > x2
```

- [ ] **Step 2: Run — падает**

Run: `./ix test tests/test_photo_frames.py tests/test_extractor.py -v`
Expected: FAIL — `ImportError: fill_frame_reading`, `ImportError: _strict_bbox`, `PhotoFact` не знает `text_legible`.

- [ ] **Step 3: Реализация — facts.py, extractor.py, pipeline.py**

`facts.py` — поля `PhotoFact` (дописать к существующим index/path/sha256/width/height/usable/problems):

```python
    face_name: str = "unknown"          # объявленная вызывающим грань или frame_N
    text_legible: Literal["yes", "partial", "no"] = "no"   # ДЕТЕРМИНИРОВАННО: по словам чтеца этого кадра
    face_bbox_pct: list[float] = Field(default_factory=list)  # рамка грани, % кадра
    face_bbox_source: str = ""          # yolo | vlm | ""
    languages: list[str] = Field(default_factory=list)        # заполняет Задача 5
```

`extractor.py` — заменить `_clamp_bbox` (строки 130–138) на отбраковку, переименовав:

```python
def _strict_bbox(raw: Any) -> list[float]:
    """Ровно четыре числа в [0, 100] и невырожденный порядок — иначе рамки НЕТ.
    Зажимание превращало мусор в валидную с виду рамку ([100,100,100,100] во
    всех кэшированных паспортах); отбраковка превращает мусор в честное
    «не прочитано» (план §5, «Ремонт рамок»)."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return []
    try:
        values = [float(v) for v in raw]
    except (TypeError, ValueError):
        return []
    if any(v < 0.0 or v > 100.0 for v in values):
        return []
    x1, y1, x2, y2 = values
    if x1 >= x2 or y1 >= y2:
        return []
    return values
```

Обновить оба вызова (`_parse_element:154`, `face_bbox_pct:184`) и все упавшие ожидания в `tests/test_extractor.py`. В текст промпта экстрактора (найти: `grep -n "bbox" src/ixvision/engines/extractor.py | head`) добавить фразу «координаты рамок — в процентах кадра, числа от 0 до 100».

`pipeline.py` — новая функция + вызов в `inspect` после этапа 4b (`read_series`):

```python
def fill_frame_reading(passport: FactPassport, *, faces: list[str] | None,
                       min_words: int, min_conf: float) -> None:
    """Per-кадровая грань и читаемость. Грань — ТОЛЬКО объявленная вызывающим
    (второй ключ не зависит от вероятностного источника, policy.yaml
    reader_min_faces); читаемость — по словам чтеца этого кадра."""
    for photo in passport.photos:
        i = photo.index
        photo.face_name = (faces[i] if faces and i < len(faces) else f"frame_{i}")
        n = sum(1 for w in passport.reader.words
                if w.asset_index == i and w.conf >= min_conf)
        photo.text_legible = "yes" if n >= min_words else ("partial" if n else "no")
```

`min_words`/`min_conf` — из политики (`reader_min_words_per_face`, `reader_min_conf`).

- [ ] **Step 4: Run + commit ядра шага**

Run: `./ix test tests/test_photo_frames.py tests/test_extractor.py -v` → PASS; затем `./ix test` целиком (могут упасть тесты, ожидавшие зажатых рамок, — починить ожидания, не поведение).

```bash
git add src/ixvision/facts.py src/ixvision/engines/extractor.py src/ixvision/pipeline.py \
        tests/test_photo_frames.py tests/test_extractor.py
git commit -m "feat(engine): per-кадр грань и читаемость, рамки отбраковываются вместо зажатия"
```

- [ ] **Step 5: Рамка грани от YOLO label_zone + surface в Finding — failing test**

Дописать в `tests/test_photo_frames.py`:

```python
def test_face_bbox_comes_from_yolo_label_zone():
    from ixvision.vision.local_facts import face_bbox_facts
    from ixvision.vision.preprocess import DetectedBox, PreparedPhoto, PreparedSeries
    # синтетика: кадр 100x100, label_zone занял левую половину
    box = DetectedBox(cls_name="label_zone", conf=0.9, x1=0, y1=0, x2=50, y2=100)
    photo = PreparedPhoto(index=0, path="0.jpg", sha256="0" * 64, width=100, height=100,
                          usable=True, problems=[], boxes=[box], crops=[])
    series = PreparedSeries(photos=[photo])
    assert face_bbox_facts(series) == {0: [0.0, 0.0, 50.0, 100.0]}


def test_finding_carries_surface_from_params():
    from ixvision.engines.rule_engine import evaluate
    from tests.scenario_runner import _compiled, _build_passport
    profile, cl, schema = _compiled("tobacco", "consumer")
    cp = next(c for c in cl.checkpoints if c.params.get("surface"))
    passport = _build_passport(schema, schema.slot_by_checkpoint().get(cp.id), {})
    findings = evaluate(cl, passport, product=profile, schema=schema)
    f = next(x for x in findings if x.checkpoint_id == cp.id)
    assert f.surface == cp.params["surface"]
```

(Сигнатуры `DetectedBox`/`PreparedPhoto`/`PreparedSeries` сверить с фактическими в `preprocess.py` — поля называть как там; тест подстроить под реальные конструкторы, не наоборот.)

- [ ] **Step 6: Реализация — local_facts.face_bbox_facts, evaluate заполняет surface, геометрия предпочитает детекторную рамку**

`vision/local_facts.py`:

```python
def face_bbox_facts(series: PreparedSeries) -> dict[int, list[float]]:
    """Рамка грани per-кадр: крупнейший label_zone детектора, в % кадра.
    Детерминированная замена scan.face_bbox_pct от VLM (план §5,
    «Рамка грани больше не стоит на VLM»)."""
    out: dict[int, list[float]] = {}
    for photo in series.photos:
        zones = [b for b in photo.boxes if b.cls_name == "label_zone"]
        if not zones:
            continue
        b = max(zones, key=lambda z: (z.x2 - z.x1) * (z.y2 - z.y1))
        out[photo.index] = [100.0 * b.x1 / photo.width, 100.0 * b.y1 / photo.height,
                            100.0 * b.x2 / photo.width, 100.0 * b.y2 / photo.height]
    return out
```

`pipeline.inspect`: после локальных фактов — прописать рамки в `passport.photos[i].face_bbox_pct` с `face_bbox_source="yolo"`; если у кадра рамки от YOLO нет, а у `scan.face_bbox_pct` есть (и прошла `_strict_bbox`) — использовать её с `face_bbox_source="vlm"` (резерв, помечен).

`rule_engine.py`:
- в `evaluate` при сборке `Finding(...)` добавить `surface=_surface_of(cp)`:

```python
_SURFACE_VOCABULARY = frozenset({"front_panel", "back_panel", "side_panel", "top_panel",
                                 "bottom_panel", "top", "bottom", "any_panel", "all_panels", "any"})

def _surface_of(cp: Checkpoint) -> str:
    raw = str(cp.params.get("surface", "") or "")
    return raw if raw in _SURFACE_VOCABULARY else "any_panel"
```

- в ветке `area_fraction` внутри `_geometry` (найти: `grep -n "area_fraction" src/ixvision/engines/rule_engine.py`) заменить чтение `ctx.passport.scan.face_bbox_pct` на:

```python
def _face_bbox_for(ctx: RuleContext, photo_index: int | None) -> tuple[list[float], str]:
    """Рамка грани для геометрии: YOLO первичен, VLM — помеченный резерв."""
    if photo_index is not None:
        for photo in ctx.passport.photos:
            if photo.index == photo_index and photo.face_bbox_pct:
                return photo.face_bbox_pct, photo.face_bbox_source or "yolo"
    scan_bbox = ctx.passport.scan.face_bbox_pct
    return (scan_bbox, "vlm") if scan_bbox else ([], "")
```

и включить источник рамки в `basis` находки (`f"рамка грани: {source}"`).

- [ ] **Step 7: EXIF/HEIC на воркере + prior_facts — failing test и реализация**

`tests/test_prior_facts.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ixvision.facts import FactPassport, TextFact, apply_overrides, passport_from_rows, passport_rows


def test_passport_rows_round_trip():
    p = FactPassport()
    p.texts["tobacco.warning.text"] = TextFact(found="yes", verbatim="Предупреждение", photo_index=1)
    p.sources["tobacco.warning.text"] = "ocr"
    rows = passport_rows(p)
    slot_rows = [r for r in rows if not r["slot_id"].startswith("__")]
    assert slot_rows[0]["slot_id"] == "tobacco.warning.text"
    assert slot_rows[0]["source"] == "ocr"
    restored = passport_from_rows(rows)
    assert restored.texts["tobacco.warning.text"].verbatim == "Предупреждение"
    assert restored.sources["tobacco.warning.text"] == "ocr"


def test_override_by_human_beats_ocr():
    p = FactPassport()
    p.texts["slot.date"] = TextFact(found="yes", verbatim="11.2025")
    p.sources["slot.date"] = "ocr"
    p2 = apply_overrides(p, [{"slot_id": "slot.date",
                              "payload": {"found": "yes", "verbatim": "12.2025"}}])
    assert p2.texts["slot.date"].verbatim == "12.2025"
    assert p2.sources["slot.date"] == "человек"


def test_weak_prior_does_not_overwrite_strong_current():
    # переиспользование прежних фактов при досъёмке: merge_slot сохраняет приоритет
    prior = FactPassport()
    prior.texts["slot.a"] = TextFact(found="yes", verbatim="из прошлой ревизии")
    prior.sources["slot.a"] = "ocr"
    current = FactPassport()
    current.texts["slot.a"] = TextFact(found="unclear")
    current.sources["slot.a"] = "vlm"
    current.merge_slot("slot.a", prior.texts["slot.a"], "ocr")
    assert current.texts["slot.a"].verbatim == "из прошлой ревизии"
```

Реализация:
- `facts.py`: `passport_rows` / `passport_from_rows` (слоты texts → `payload = fact.model_dump()`, `kind: "text"`; elements → `kind: "element"`; служебные строки `__scan__`/`__reader__`/`__codes__`/`__photos__` с `payload = model_dump()` и `source="system"`); `apply_overrides` — глубокая копия паспорта (`model_copy(deep=True)`), для каждого override построить `TextFact`/`ElementFact` из payload (по наличию ключей `found`/`seen`) и `merge_slot(slot_id, fact, "человек")`;
- `pipeline.inspect`: параметры `prior_facts`, `fact_overrides`, `reuse_facts`; после сборки паспорта новых кадров — если `prior_facts`: для каждого слота prior вызвать `merge_slot` c его источником (слабое не затирает сильное); затем `apply_overrides`; при `reuse_facts=True` VLM-извлечение запускать только для слотов, оставшихся пустыми (передать экстрактору список нужных слотов — если текущий `extract` не умеет частичный список, отфильтровать шарды по незаполненным слотам);
- `preprocess.py`: загрузка кадра через PIL с разворотом и HEIC:

```python
from PIL import Image, ImageOps
try:  # HEIC/HEIF с айфона; без библиотеки поведение прежнее
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

def _load_image(path: Path) -> np.ndarray:
    """PIL вместо cv2.imread: EXIF-ориентация разворачивается ЗДЕСЬ
    (вторая страховка после клиентской, план §2Б шаг 3)."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        return cv2.cvtColor(np.array(im.convert("RGB")), cv2.COLOR_RGB2BGR)
```

и заменить существующее чтение файла в `prepare()` на `_load_image`.

- [ ] **Step 8: Run всё + бенч + commit**

```bash
./ix test
./ix bench --assert missed_as_pass=0 --assert unsupported_decision=0
git add -A src/ixvision tests runs/benchmark.json
git commit -m "feat(engine): рамка грани от YOLO, surface в находке, EXIF/HEIC, prior_facts для досъёмки"
```

---

### Task 5: Движок: PaddleOCR-бэкенд, привратник (Левенштейн ≤ 2), чтение params.language

**Files:**
- Create: `src/ixvision/engines/gatekeeper.py`, `src/ixvision/engines/language.py`, `scripts/ocr_duel.py`
- Modify: `src/ixvision/vision/ocr.py` (выбор движка easy|paddle), `src/ixvision/facts.py` (`FactPassport.confirmations`), `src/ixvision/pipeline.py` (привратник после извлечения, языки per-кадр), `src/ixvision/engines/rule_engine.py` (`_language_gap`, гейт неподтверждённого значения), `config/routing.yaml` (`extraction.ocr_engine`)
- Test: `tests/test_gatekeeper.py`, `tests/test_language.py`; дополнение `tests/scenarios/tobacco.yaml` языковыми кейсами

**Interfaces:**
- Consumes: Task 4 (`PhotoFact.languages`, `fill_frame_reading`), Task 1 (`scenario_runner`).
- Produces:
  - `gatekeeper.levenshtein(a: str, b: str, *, limit: int = 2) -> int` (обрезка при превышении limit);
  - `gatekeeper.confirm_text(claim: str, reader: ReaderFact, *, asset_index: int | None = None, bbox_pct: list[float] | None = None, max_distance: int = 2) -> str | None` — дословная цитата чтеца, подтверждающая VLM-текст, или None;
  - `FactPassport.confirmations: dict[str, str]` — slot_id → подтверждающая цитата чтеца;
  - `language.word_language(word: ReaderWord) -> str` (`ru|uz-cyrl|uz-latn|en|digit|other`), `language.face_languages(reader: ReaderFact, *, min_conf: float = 0.5) -> dict[str, set[str]]`;
  - движок: `text_semantic` с `params.language` даёт FAIL только при прочитанной чтецом грани (утверждение об отсутствии), иначе UNREADABLE «нет чтеца»;
  - `_text_value_check`: значение от неподтверждённого VLM → UNREADABLE «прочитали, но не смогли сопоставить со значением — проверьте вручную».

- [ ] **Step 1: Failing tests привратника и языка**

`tests/test_gatekeeper.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ixvision.engines.gatekeeper import confirm_text, levenshtein
from ixvision.facts import ReaderFact, ReaderWord


def _reader(*texts: str, asset_index: int = 0) -> ReaderFact:
    words = [ReaderWord(text=t, source="ocr", conf=0.9, asset_index=asset_index,
                        bbox_pct=[10.0 * i, 10, 10.0 * i + 8, 15])
             for i, t in enumerate(texts)]
    return ReaderFact(words=words, engine="easyocr:ru+en")


def test_levenshtein_early_exit():
    assert levenshtein("smola", "smola") == 0
    assert levenshtein("smola", "smol0") == 1
    assert levenshtein("abc", "xyz", limit=2) > 2   # обрезан, точное значение не считается


def test_confirms_within_distance_two():
    reader = _reader("Смолы", "10", "мг")
    assert confirm_text("Смоны 10 мг", reader) == "Смолы 10 мг"


def test_rejects_text_reader_never_saw():
    reader = _reader("MARLBORO", "GOLD")
    assert confirm_text("Не для продажи несовершеннолетним", reader) is None


def test_polygon_restriction_applies():
    reader = _reader("Смолы", asset_index=0)
    # слово чтеца лежит в левом верхнем углу; ищем в правом нижнем — не подтверждено
    assert confirm_text("Смолы", reader, asset_index=0, bbox_pct=[80, 80, 100, 100]) is None
```

`tests/test_language.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ixvision.engines.language import face_languages, word_language
from ixvision.facts import ReaderFact, ReaderWord


def _w(text: str, face: str = "front_panel") -> ReaderWord:
    return ReaderWord(text=text, source="ocr", conf=0.9, face=face)


def test_scripts_and_uz_markers():
    assert word_language(_w("состав")) == "ru"
    assert word_language(_w("маҳсулот")) == "uz-cyrl"    # ҳ — узбекская кириллица
    assert word_language(_w("mahsulot")) == "uz-latn"    # узбекское слово латиницей
    assert word_language(_w("oʻzbek")) == "uz-latn"      # апостроф oʻ
    assert word_language(_w("ingredients")) == "en"
    assert word_language(_w("2025")) == "digit"


def test_face_languages_aggregates_by_face():
    reader = ReaderFact(words=[_w("состав"), _w("saqlash"), _w("shelf", face="back_panel")])
    langs = face_languages(reader)
    assert langs["front_panel"] >= {"ru", "uz-latn"}
    assert "en" in langs["back_panel"]
```

- [ ] **Step 2: Run — падает**

Run: `./ix test tests/test_gatekeeper.py tests/test_language.py -v`
Expected: FAIL — модулей нет.

- [ ] **Step 3: Реализовать gatekeeper.py и language.py**

`src/ixvision/engines/gatekeeper.py`:

```python
"""Привратник: VLM-текст принимается, только если подтверждён чтецом —
нечёткое совпадение (Левенштейн ≤ 2 на слово) внутри полигона чтеца (план §5).
Для пиктограмм второй ключ — YOLO (см. rule_engine.detector_may_claim_absence),
для чисто семантических утверждений второго ключа НЕ СУЩЕСТВУЕТ — такие пункты
вердикта не получают (это уже поведение движка, привратник его не меняет)."""
from __future__ import annotations

import re

from ixvision.facts import ReaderFact

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def levenshtein(a: str, b: str, *, limit: int = 2) -> int:
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
            best = min(best, cur[-1])
        if best > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _overlaps(word_bbox: list[float], zone: list[float]) -> bool:
    if not zone or not word_bbox:
        return True   # ограничение полигоном включается только когда обе рамки есть
    wx1, wy1, wx2, wy2 = word_bbox
    zx1, zy1, zx2, zy2 = zone
    return wx1 < zx2 and wx2 > zx1 and wy1 < zy2 and wy2 > zy1


def confirm_text(claim: str, reader: ReaderFact, *, asset_index: int | None = None,
                 bbox_pct: list[float] | None = None, max_distance: int = 2) -> str | None:
    """Каждый значимый токен утверждения должен найтись у чтеца (Левенштейн ≤ 2)
    в нужном кадре и полигоне. Возвращает цитату из СЛОВ ЧТЕЦА (не VLM)."""
    tokens = [t for t in _TOKEN_RE.findall(claim) if len(t) >= 2]
    if not tokens:
        return None
    pool = [w for w in reader.words
            if (asset_index is None or w.asset_index == asset_index)
            and _overlaps(w.bbox_pct, bbox_pct or [])]
    quote: list[str] = []
    for token in tokens:
        hit = next((w for w in pool
                    if levenshtein(token.casefold(), w.text.casefold(),
                                   limit=max_distance) <= max_distance), None)
        if hit is None:
            return None
        quote.append(hit.text)
    return " ".join(quote)
```

`src/ixvision/engines/language.py`:

```python
"""Язык слова и грани — детерминированно, по словам чтеца (план §5, Х7:
«язык определяется по словам OCR на конкретной грани»). Скрипт — из
facts.script_of; узбекские маркеры отличают uz от ru/en внутри скрипта."""
from __future__ import annotations

from ixvision.facts import ReaderFact, ReaderWord, script_of

UZ_CYRL_MARKERS = set("ўқғҳЎҚҒҲ")
UZ_APOSTROPHES = set("ʻʼ'’`´")
UZ_LATN_WORDS = frozenset({
    "va", "yoki", "uchun", "tarkibi", "saqlash", "muddati", "ishlab",
    "chiqarilgan", "mahsulot", "ogohlantirish", "sana", "kun", "oy", "yil",
})
EN_WORDS = frozenset({
    "the", "and", "ingredients", "warning", "made", "best", "before",
    "keep", "shelf", "life", "net", "weight",
})


def word_language(word: ReaderWord) -> str:
    text = word.text.strip()
    low = text.casefold()
    script = script_of(text)
    if script == "digit":
        return "digit"
    if script == "cyrl":
        return "uz-cyrl" if set(text) & UZ_CYRL_MARKERS else "ru"
    if script == "latn":
        if low in UZ_LATN_WORDS or (set(text) & UZ_APOSTROPHES):
            return "uz-latn"
        if low in EN_WORDS:
            return "en"
        return "latn"   # латиница без маркеров: uz-latn и en неразличимы по одному слову
    return "other"


def face_languages(reader: ReaderFact, *, min_conf: float = 0.5) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for w in reader.words:
        if w.conf < min_conf:
            continue
        lang = word_language(w)
        if lang in ("digit", "other"):
            continue
        out.setdefault(w.face, set()).add(lang)
    # неопределённая латиница считается и uz-latn, и en только если на грани
    # есть однозначный маркер того же языка — иначе остаётся 'latn'
    return out
```

(Точную сигнатуру `script_of` сверить с `facts.py:187`; если она возвращает иные метки — привести словарь к её меткам, тест не менять по смыслу.)

- [ ] **Step 4: Run — gatekeeper/language зелёные**

Run: `./ix test tests/test_gatekeeper.py tests/test_language.py -v` → PASS.

- [ ] **Step 5: Вплести в pipeline и движок; языковые сценарные кейсы**

- `facts.py`: `FactPassport.confirmations: dict[str, str] = Field(default_factory=dict)`;
- `pipeline.inspect`: после слияния источников — для каждого текстового слота с `sources[slot] == "vlm"` и `found == "yes"`: `q = gatekeeper.confirm_text(fact.verbatim, passport.reader, asset_index=fact.photo_index, bbox_pct=fact_bbox)`; при успехе `passport.confirmations[slot] = q`; кроме того `photo.languages = sorted({word_language(w) for w in reader.words if w.asset_index == photo.index} - {"digit", "other"})`;
- `rule_engine.py`, `_text_value_check`: первым guard'ом —

```python
    src = ctx.passport.sources.get(ctx.slot_id or "", "")
    if src == "vlm" and (ctx.slot_id or "") not in ctx.passport.confirmations:
        return RuleOutcome(Status.UNREADABLE, 0.4,
            "Прочитали текст, но не смогли сопоставить со значением — проверьте вручную",
            basis="vlm без подтверждения чтеца")
```

- `rule_engine.py`, `_text_semantic`: до существующих веток — языковой guard:

```python
def _language_gap(ctx: RuleContext) -> RuleOutcome | None:
    """params.language (156 проверок): требуемый язык сведения. FAIL — только
    утверждением чтеца (правило двух ключей); без чтеца — человеку."""
    required = {str(v) for v in (ctx.cp.params.get("language") or [])}
    if not required:
        return None
    langs: set[str] = set()
    for face_langs in face_languages(ctx.passport.reader).values():
        langs |= face_langs
    if "latn" in langs:
        langs |= {"uz-latn", "en"}   # неразличимая латиница закрывает оба
    if required & langs:
        return None                  # требуемый язык на упаковке есть — судим содержание дальше
    support = _reader_support(ctx)
    if support is None:
        return RuleOutcome(Status.UNREADABLE, 0.3,
            "Проверка языка: грань никто не прочитал — утверждать отсутствие нельзя",
            claim=Claim.ABSENCE)
    return RuleOutcome(Status.FAIL, 0.8,
        f"Сведение не найдено на требуемом языке ({', '.join(sorted(required))}); "
        f"прочитано граней: {support.faces}",
        basis=support.source, claim=Claim.ABSENCE, decided_by=support.source)
```

и вызов `gap = _language_gap(ctx)` / `if gap is not None: return gap` в начале `_text_semantic` (после получения `text`; при `found == "yes"` и совпавшем языке guard возвращает None и величина судится дальше).
- Дописать в `tests/scenarios/tobacco.yaml` два кейса на проверку с `params.language` (взять реальный id: `grep -n "language:" config/requirements/tobacco.yaml | head`): `fail` — reader-слова только `[MARLBORO, GOLD, KING, SIZE]` при required uz; `human` — reader пуст → `unreadable`.

Run: `./ix test` целиком → PASS (упавшие сценарные кейсы, где текст решался неподтверждённым VLM, перевести в `expect: unreadable` — это снятие ложных решений, зафиксировать в сообщении коммита).

- [ ] **Step 6: PaddleOCR-бэкенд + дуэль**

`vision/ocr.py`: ввести выбор движка. Ключ `config/routing.yaml → extraction.ocr_engine: easy` (дефолт — текущее поведение), env-переопределение `IXV_OCR_ENGINE`. Реализация: `_get_engine()` возвращает `(reader, label)`; добавить ветку `paddle`:

```python
def _get_paddle() -> tuple[Any, str]:
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return False, "none"
    engine = PaddleOCR(lang="ru", use_textline_orientation=True)  # кириллица+латиница одним проходом
    return engine, "paddleocr:ru"


def _paddle_raw(engine: Any, image: np.ndarray) -> list[tuple[Any, str, Any]]:
    """Привести ответ PaddleOCR к сырым кортежам EasyOCR (bbox, text, conf),
    чтобы words_from_raw остался единственным местом разбора."""
    result = engine.predict(image)
    out: list[tuple[Any, str, Any]] = []
    for page in result:
        for poly, text, score in zip(page["rec_polys"], page["rec_texts"], page["rec_scores"]):
            out.append((poly, text, score))
    return out
```

(Форму ответа сверить с установленной версией `paddleocr` — если `predict` отдаёт объект, а не dict, адаптировать в этом же месте; контракт наружу — только сырые кортежи.) `read_words` ветвится по выбранному движку, всё остальное (`words_from_raw`, `reader_facts`, `merge_reader`) не меняется. Тесты paddle — по образцу существующих skip-тестов easyocr (`test_ocr.py`): `pytest.importorskip("paddleocr")`.

`scripts/ocr_duel.py`: гоняет оба движка по растрам `data/fixtures/mackets/adversarial/*.pdf` (через `vision.raster.render_pages`), сравнивает recall ожидаемых слов из `manifest.json`; печатает таблицу `движок × макет × найдено/всего × мс`. Решение о переключении дефолта:

```bash
./.venv/bin/python scripts/ocr_duel.py
# paddle >= easy по recall на adversarial-наборе → extraction.ocr_engine: paddle (коммит с таблицей в сообщении)
# paddle < easy → дефолт остаётся easy; paddle остаётся опцией образа (self-host чтец уже есть — EasyOCR)
```

- [ ] **Step 7: Бенч и commit**

```bash
./ix bench --assert missed_as_pass=0 --assert unsupported_decision=0
git add -A src/ixvision tests scripts/ocr_duel.py config/routing.yaml runs/benchmark.json
git commit -m "feat(engine): привратник Левенштейн-2, язык по словам чтеца на грани, PaddleOCR-бэкенд"
```

---

### Task 6: Воркер: реестр набора правил — sha256, регистрация, сверка перед судом

**Files:**
- Create: `src/ixvision/ruleset.py`, `tests/test_ruleset.py`
- Modify: `src/ixvision/server.py` (lifespan: расчёт + регистрация)

**Interfaces:**
- Consumes: Task 3 (`paths.config_dir()`).
- Produces:
  - `ruleset.fingerprint(config_dir: Path | None = None) -> dict` → `{"sha256": str, "version": str, "built_at": str, "packs": dict[str, int], "checks_count": int}`;
  - `ruleset.register(base_url: str, secret: str, fp: dict, *, client: httpx.Client | None = None) -> bool` — `POST {base_url}/api/vision/ruleset` с заголовком `X-Worker-Secret`;
  - `app.state.ruleset` — fingerprint процесса; Задача 7 сверяет его с `ruleset_sha256` задания (расхождение → 409 `ruleset_drift`).

- [ ] **Step 1: Failing test**

`tests/test_ruleset.py`:

```python
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ixvision import ruleset


def _mini_config(tmp_path: Path) -> Path:
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "a.yaml").write_text("pack: a\n", encoding="utf-8")
    (tmp_path / "policy.yaml").write_text("reader_min_faces: 3\n", encoding="utf-8")
    return tmp_path


def test_fingerprint_is_deterministic_and_sensitive(tmp_path):
    cfg = _mini_config(tmp_path)
    fp1 = ruleset.fingerprint(cfg)
    fp2 = ruleset.fingerprint(cfg)
    assert fp1["sha256"] == fp2["sha256"] and len(fp1["sha256"]) == 64
    (cfg / "policy.yaml").write_text("reader_min_faces: 2\n", encoding="utf-8")
    assert ruleset.fingerprint(cfg)["sha256"] != fp1["sha256"]


def test_register_posts_fingerprint_with_secret(tmp_path):
    fp = ruleset.fingerprint(_mini_config(tmp_path))
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["secret"] = request.headers.get("X-Worker-Secret")
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert ruleset.register("https://example.vercel.app", "s3cret", fp, client=client)
    assert seen["url"].endswith("/api/vision/ruleset")
    assert seen["secret"] == "s3cret"
```

- [ ] **Step 2: Run — падает** (`ModuleNotFoundError: ixvision.ruleset`)

Run: `./ix test tests/test_ruleset.py -v`

- [ ] **Step 3: Реализация**

```python
"""Реестр версий набора правил (план §3, «Реестр версий»): воркер считает
sha256 от отсортированного содержимого config/requirements/*.yaml +
config/policy.yaml, регистрирует себя на витрине и сверяет хеш каждого
задания со своим — вердикт по неизвестному набору правил не выдаётся."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ixvision import paths


def fingerprint(config_dir: Path | None = None) -> dict:
    cfg = config_dir or paths.config_dir()
    files = sorted((cfg / "requirements").glob("*.yaml")) + [cfg / "policy.yaml"]
    digest = hashlib.sha256()
    packs: dict[str, int] = {}
    checks_count = 0
    for f in files:
        data = f.read_bytes()
        digest.update(f.name.encode())
        digest.update(data)
        n = data.count(b"\n  - id:") + data.count(b"\n    - id:")
        if f.name != "policy.yaml":
            packs[f.stem] = n
            checks_count += n
    sha = digest.hexdigest()
    return {
        "sha256": sha,
        "version": datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + sha[:8],
        "built_at": datetime.now(timezone.utc).isoformat(),
        "packs": packs,
        "checks_count": checks_count,
    }


def register(base_url: str, secret: str, fp: dict, *, client: httpx.Client | None = None) -> bool:
    c = client or httpx.Client(timeout=10)
    try:
        r = c.post(base_url.rstrip("/") + "/api/vision/ruleset",
                   json=fp, headers={"X-Worker-Secret": secret})
        return r.status_code == 200
    except httpx.HTTPError:
        return False
```

Замечание: если грубый подсчёт `checks_count` по байтам расходится с фактическим (проверить: `python -c "...compile..."`), заменить на честный подсчёт через `load_all_packs(cfg/'requirements')` — sha256 при этом всё равно считается от байтов файлов, а не от разобранных структур.

`server.py`, в `_lifespan` после `warmup()`:

```python
    import os
    from ixvision import ruleset as ruleset_mod
    _app.state.ruleset = ruleset_mod.fingerprint()
    base, secret = os.environ.get("IXV_PROGRESS_BASE", ""), os.environ.get("IXV_WORKER_SECRET", "")
    if base and secret:
        if not ruleset_mod.register(base, secret, _app.state.ruleset):
            logger.warning("ruleset: регистрация на витрине не удалась — продолжаем, CLI жив")
```

- [ ] **Step 4: Run + commit**

Run: `./ix test tests/test_ruleset.py tests/test_server.py -v` → PASS.

```bash
git add src/ixvision/ruleset.py src/ixvision/server.py tests/test_ruleset.py
git commit -m "feat(worker): реестр набора правил — fingerprint, регистрация, сверка перед судом"
```

---

### Task 7: Воркер: POST /internal/inspect, POST /internal/rejudge, канал прогресса, кропы-доказательства

**Files:**
- Create: `src/ixvision/contracts.py`, `src/ixvision/progress.py`, `src/ixvision/vision/evidence.py`, `tests/test_internal_api.py`
- Modify: `src/ixvision/server.py` (два эндпоинта + secret-guard), `src/ixvision/pipeline.py` (`on_stage`-хуки в местах существующих `stages_ms`)

**Interfaces:**
- Consumes: Task 4 (`passport_rows`/`passport_from_rows`/`apply_overrides`, `prior_facts` в `inspect`), Task 6 (`app.state.ruleset`).
- Produces (контракт для `api/vision/check.ts` и `api/vision/rejudge.ts` Задачи 10):

```python
class FactRow(BaseModel):
    slot_id: str
    payload: dict
    source: str                      # yolo|ocr|zbar|pdf_text|vlm|human|system
    confidence: float | None = None
    asset_idx: int | None = None
    bbox: list[float] | None = None

class FactOverride(BaseModel):
    slot_id: str
    payload: dict
    note: str = ""

class InspectRequest(BaseModel):
    inspection_id: str
    product: str                     # id профиля движка: tobacco|dairy|electronics
    level: str                       # consumer|transport
    markets: list[str] = ["UZ"]
    evaluated_at: str | None = None
    ruleset_sha256: str
    kind: Literal["photo", "master_pdf"]
    asset_urls: list[str]
    pages: list[str] | None = None   # карта граней страниц макета
    faces: list[str] | None = None   # карта граней кадров
    reference_dimensions_mm: dict[str, float] | None = None   # габариты SKU (Задача 15)
    prior_facts: list[FactRow] | None = None
    fact_overrides: list[FactOverride] | None = None
    reuse_facts: bool = False

class FindingRow(BaseModel):
    checkpoint_id: str
    rule_ref: str
    group_key: str
    surface: str
    kind: str
    severity: str
    status: str                      # pass|fail|unreadable|not_applicable
    decided_by: str
    confidence_class: str            # machine_read|needs_human|not_checkable (развилка 11: класс, не число)
    message: str
    basis: str
    recommendation: str | None = None
    evidence: list[dict] = []
    evidence_crop_b64: str | None = None   # JPEG ≤ 2 МБ; в бакет кладёт СЕРВЕР витрины

class NotCheckableRow(BaseModel):
    checkpoint_key: str
    rule_ref: str
    reason: str
    klass: str                       # метод|нет данных о товаре|нет эталона|нет чтеца

class AssetRow(BaseModel):
    idx: int
    sha256: str
    width: int | None = None
    height: int | None = None
    mime: str
    face_name: str = "unknown"
    usable: bool = True
    problems: list[str] = []

class ModelCallRow(BaseModel):
    stage: str                       # pdf_text|ocr|vlm_shard|vlm_reask
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0

class InspectResponse(BaseModel):
    overall: str
    decided: int
    checked: int
    findings: list[FindingRow]
    not_checkable: list[NotCheckableRow]
    facts: list[FactRow]
    assets: list[AssetRow]
    model_calls: list[ModelCallRow]
    reader_coverage: dict
    extraction_errors: list[str]
    policy_applied: dict
    ruleset_sha256: str
    ruleset_version: str
    prompt_version: str = ""
    model_versions: dict = {}
    degraded_mode: str | None = None
    evaluated_at: str | None = None
    cost_usd: float = 0.0

class ChecklistKey(BaseModel):
    product: str
    level: str
    markets: list[str] = ["UZ"]

class RejudgeRequest(BaseModel):
    checklist_key: ChecklistKey
    facts: list[FactRow]
    overrides: list[FactOverride]
    policy: dict | None = None

class RejudgeResponse(BaseModel):
    overall: str
    decided: int
    checked: int
    findings: list[FindingRow]
    not_checkable: list[NotCheckableRow]
    policy_applied: dict
```

  - Исходящий прогресс: `POST {IXV_PROGRESS_BASE}/api/vision/progress`, JSON `{"inspection_id": str, "stage": "received|prepare|read|judge|render|done|failed", "detail": dict}`, заголовок `X-Worker-Secret`; сбои канала прогресса глотаются (warning), суд не прерывают.
  - Ошибки: нет/неверный `X-Worker-Secret` → 401; `ruleset_sha256` ≠ своего → 409 `{"reason": "ruleset_drift"}`; PDF без текстового слоя → 200 c `InspectResponse` нулевых findings не бывает — вместо этого 422 `{"reason": "no_text_layer"}` (отказ по данным, квоту не возвращает — решает витрина); недоступный asset_url → 424 `{"reason": "asset_fetch_failed"}`.

- [ ] **Step 1: Failing tests**

`tests/test_internal_api.py`:

```python
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PDF = ROOT / "data" / "fixtures" / "mackets" / "adversarial" / "adv_no_shelf_life.pdf"


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("IXV_WORKER_SECRET", "s3cret")
    monkeypatch.delenv("IXV_PROGRESS_BASE", raising=False)   # прогресс молчит в тестах
    from ixvision.server import app
    return TestClient(app)


def test_inspect_requires_secret(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/internal/inspect", json={})
    assert r.status_code == 401


def test_ruleset_drift_is_409(monkeypatch):
    client = _client(monkeypatch)
    body = {"inspection_id": "t1", "product": "tobacco", "level": "consumer",
            "ruleset_sha256": "0" * 64, "kind": "master_pdf",
            "asset_urls": [FIXTURE_PDF.as_uri()]}
    r = client.post("/internal/inspect", json=body, headers={"X-Worker-Secret": "s3cret"})
    assert r.status_code == 409
    assert r.json()["reason"] == "ruleset_drift"


def test_inspect_master_pdf_end_to_end(monkeypatch):
    client = _client(monkeypatch)
    from ixvision.server import app
    sha = app.state.ruleset["sha256"]
    body = {"inspection_id": "t2", "product": "tobacco", "level": "consumer",
            "ruleset_sha256": sha, "kind": "master_pdf",
            "asset_urls": [FIXTURE_PDF.as_uri()],
            "pages": ["front_panel", "back_panel", "side_panel"]}
    r = client.post("/internal/inspect", json=body, headers={"X-Worker-Secret": "s3cret"})
    assert r.status_code == 200
    data = r.json()
    assert data["ruleset_sha256"] == sha
    assert data["findings"] and data["facts"]
    assert all(f["decided_by"] != "vlm" or f["status"] not in ("pass", "fail")
               or f["evidence"] for f in data["findings"])
    assert any(row["slot_id"] == "__reader__" for row in data["facts"])


def test_rejudge_is_local_and_free(monkeypatch):
    client = _client(monkeypatch)
    body = {
        "checklist_key": {"product": "tobacco", "level": "consumer"},
        "facts": [{"slot_id": "__photos__", "payload": {"photos": [
            {"index": i, "path": f"{i}.jpg", "sha256": f"{i:064d}",
             "width": 100, "height": 100} for i in range(4)]}, "source": "system"}],
        "overrides": [],
    }
    r = client.post("/internal/rejudge", json=body, headers={"X-Worker-Secret": "s3cret"})
    assert r.status_code == 200
    data = r.json()
    assert data["findings"]
    assert "model_calls" not in data   # пересуд не имеет права стоить денег
```

- [ ] **Step 2: Run — падает** (404 на `/internal/*`)

Run: `./ix test tests/test_internal_api.py -v`

- [ ] **Step 3: Реализация — contracts.py, progress.py, evidence.py, эндпоинты**

`src/ixvision/contracts.py` — pydantic-модели из блока Interfaces дословно.

`src/ixvision/progress.py`:

```python
"""Исходящий канал прогресса: воркер НЕ пишет в базу — он рассказывает
нашему же серверу (api/vision/progress), а пишет сервер (план §4)."""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


class ProgressReporter:
    def __init__(self, inspection_id: str) -> None:
        self.inspection_id = inspection_id
        self.base = os.environ.get("IXV_PROGRESS_BASE", "").rstrip("/")
        self.secret = os.environ.get("IXV_WORKER_SECRET", "")

    def stage(self, name: str, **detail: object) -> None:
        if not self.base or not self.secret:
            return
        try:
            httpx.post(f"{self.base}/api/vision/progress",
                       json={"inspection_id": self.inspection_id, "stage": name,
                             "detail": detail},
                       headers={"X-Worker-Secret": self.secret}, timeout=5)
        except httpx.HTTPError as exc:   # прогресс — не суд: сбой глотаем
            logger.warning("progress %s: %s", name, exc)
```

`src/ixvision/vision/evidence.py`:

```python
"""Кроп-доказательство: вырезка по рамке из кадра или растра страницы макета.
Возвращает JPEG-байты ≤ 2 МБ; в бакет evidence-crops кладёт сервер витрины."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

MAX_BYTES = 2 * 1024 * 1024
PAD_RATIO = 0.05


def crop_jpeg(image: np.ndarray, bbox_pct: list[float]) -> bytes | None:
    if len(bbox_pct) != 4:
        return None
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox_pct
    px = int(PAD_RATIO * (x2 - x1) * w / 100)
    py = int(PAD_RATIO * (y2 - y1) * h / 100)
    xa, ya = max(0, int(x1 * w / 100) - px), max(0, int(y1 * h / 100) - py)
    xb, yb = min(w, int(x2 * w / 100) + px), min(h, int(y2 * h / 100) + py)
    if xb <= xa or yb <= ya:
        return None
    crop = image[ya:yb, xa:xb]
    for quality in (85, 70, 50):
        ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ok and buf.nbytes <= MAX_BYTES:
            return buf.tobytes()
    return None
```

`server.py` — guard и эндпоинты (скелет; скачивание поддерживает `file://` для тестов и локальной отладки):

```python
def _require_worker_secret(request: Request) -> None:
    secret = os.environ.get("IXV_WORKER_SECRET", "")
    if not secret:
        raise HTTPException(503, "IXV_WORKER_SECRET не задан")
    if request.headers.get("X-Worker-Secret") != secret:
        raise HTTPException(401, "нет доступа")


def _fetch_asset(url: str, dest: Path) -> Path:
    if url.startswith("file://"):
        src = Path(url[len("file://"):])
        dest.write_bytes(src.read_bytes())
        return dest
    with httpx.stream("GET", url, timeout=60) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_bytes():
                fh.write(chunk)
    return dest


@app.post("/internal/inspect")
def internal_inspect(req: contracts.InspectRequest, request: Request) -> dict:
    _require_worker_secret(request)
    if req.ruleset_sha256 != app.state.ruleset["sha256"]:
        return JSONResponse({"reason": "ruleset_drift"}, status_code=409)
    progress = ProgressReporter(req.inspection_id)
    progress.stage("received", assets=len(req.asset_urls))
    with tempfile.TemporaryDirectory() as tmp:
        try:
            local = [_fetch_asset(u, Path(tmp) / f"{i:02d}{_ext_of(u, req.kind)}")
                     for i, u in enumerate(req.asset_urls)]
        except (httpx.HTTPError, OSError):
            progress.stage("failed", reason="asset_fetch_failed")
            return JSONResponse({"reason": "asset_fetch_failed"}, status_code=424)
        on_stage = lambda name, detail=None: progress.stage(name, **(detail or {}))
        if req.kind == "master_pdf":
            if not artwork.has_text_layer(local[0]):
                progress.stage("failed", reason="no_text_layer")
                return JSONResponse({"reason": "no_text_layer"}, status_code=422)
            verdict = pipeline.inspect_artwork(req.product, req.level, local[0],
                                               pages=req.pages, markets=req.markets,
                                               on_stage=on_stage)
        else:
            prior = facts_mod.passport_from_rows([r.model_dump() for r in req.prior_facts]) \
                if req.prior_facts else None
            verdict = pipeline.inspect(
                req.product, req.level, local,
                provider=os.environ.get("IXV_VLM_PROVIDER", "gemini"),
                live=bool(env.gemini_key() or env.openai_key()),
                markets=req.markets, faces=req.faces,
                prior_facts=prior,
                fact_overrides=[o.model_dump() for o in (req.fact_overrides or [])],
                reuse_facts=req.reuse_facts, on_stage=on_stage)
        progress.stage("render")
        response = _inspect_response(req, verdict, local)   # сборка InspectResponse + кропы
        progress.stage("done", decided=response.decided)
        return response.model_dump()
```

`_inspect_response`: findings → `FindingRow` (маппинг `confidence_class`: `basis_kind == deterministic` → `machine_read`; `unreadable`/`suspected` → `needs_human`; `not_applicable` → `not_checkable`), кропы через `evidence.crop_jpeg` (для фото — из кадра `photo_index`; для макета — из растра `raster.render_pages` по bbox_mm→px), `facts=passport_rows(verdict.facts)`, `assets` из `verdict.facts.photos` (или sha256+mime PDF), `model_calls` из аудита экстрактора (в Волне 1 обычно пуст — деградация `local`), `degraded_mode="local"` при отсутствии VLM-ключа.

`/internal/rejudge`:

```python
@app.post("/internal/rejudge")
def internal_rejudge(req: contracts.RejudgeRequest, request: Request) -> dict:
    _require_worker_secret(request)
    passport = facts_mod.passport_from_rows([r.model_dump() for r in req.facts])
    passport = facts_mod.apply_overrides(passport, [o.model_dump() for o in req.overrides])
    profile = load_product(req.checklist_key.product)
    checklist = compile_checklist(profile, PackagingLevel(req.checklist_key.level),
                                  markets=req.checklist_key.markets)
    findings = evaluate(checklist, passport, product=profile,
                        policy=req.policy or active_policy())
    overall, decided = pipeline.summarize(findings, passport)
    return contracts.RejudgeResponse(
        overall=overall.value, decided=decided, checked=len(findings),
        findings=[_finding_row(f, passport) for f in findings],
        not_checkable=_not_checkable_rows(checklist),
        policy_applied=req.policy or active_policy()).model_dump()
```

`pipeline.py`: параметр `on_stage` в `inspect`/`inspect_artwork`; вызовы в местах, где начинаются существующие замеры `stages_ms`: `on_stage("prepare")` перед подготовкой кадров/растеризацией, `on_stage("read")` перед чтецом, `on_stage("judge")` перед `evaluate`.

- [ ] **Step 4: Run + commit**

Run: `./ix test tests/test_internal_api.py tests/test_server.py -v` → PASS; затем `./ix test` целиком.

```bash
git add src/ixvision/contracts.py src/ixvision/progress.py src/ixvision/vision/evidence.py \
        src/ixvision/server.py src/ixvision/pipeline.py tests/test_internal_api.py
git commit -m "feat(worker): /internal/inspect и /internal/rejudge, канал прогресса, кропы-доказательства"
```

### Task 8: Миграция витрины 20260810100000_photo_runtime.sql — таблицы, RLS, RPC, реперная и ретеншн-джобы

**Files:**
- Create: `supabase/migrations/20260810100000_photo_runtime.sql`, `importer/tests/db/__init__.py`, `importer/tests/db/conftest.py`, `importer/tests/db/test_photo_runtime.py`
- Repo: ветка `photocontrol-wave1` (Task 2 Step 4); слоты `202608101*` свободны (проверено: максимум на main — `20260806110000`, в ветке — `20260806130000`)

**Interfaces:**
- Consumes: Task 2 (ветка, CI).
- Produces (нужны Задачам 9–16):
  - таблицы `public.ruleset_versions`, `photo_inspections`, `photo_inspection_events`, `photo_assets`, `photo_findings`, `photo_not_checkable`, `photo_facts`, `photo_fact_overrides`, `photo_finding_actions`, `photo_finding_reviews`, `photo_model_calls`, `photo_quota`, `photo_profiles` — колонки дословно из плана §4;
  - `public.request_photo_inspection(p_product_id uuid, p_level text, p_markets text[], p_source_kind text, p_asset_paths text[], p_idempotency_key text) returns uuid` — authenticated;
  - `public.request_photo_retake(p_inspection_id uuid, p_new_asset_paths text[], p_idempotency_key text) returns uuid` — authenticated;
  - `public.finalize_photo_inspection(p_inspection_id uuid, p_outcome text, p_reason text default null, p_payload jsonb default null) returns void` — только service_role;
  - `public.create_photo_revision(p_parent_id uuid, p_payload jsonb) returns uuid` — только service_role (пересуд);
  - `public.record_finding_action(p_finding_id uuid, p_action text, p_reason text default null) returns uuid` — authenticated (своя проверка);
  - `public.sign_photo_inspection(p_inspection_id uuid) returns void` — verified-юрист;
  - `public.photo_profile_for_product(p_product_id uuid) returns text` — резолвер профиля;
  - `public.reap_stale_inspections() returns int` (pg_cron `* * * * *`), `public.purge_expired_photo_assets() returns int` (pg_cron `30 2 * * *`);
  - конфтест `importer/tests/db/conftest.py`: `STACK` (`supabase status -o json`), `requires_db`, фикстуры `service` (supabase-py под service_role), `subscriber` (юзер с `is_subscribed=true`), `current_ruleset` (строка `ruleset_versions` c `is_current`).

- [ ] **Step 1: Конфтест и failing-тесты**

`importer/tests/db/conftest.py`:

```python
"""Интеграционные тесты фотоконтроля: живой ЛОКАЛЬНЫЙ Supabase.
Паттерн скипа — тот же, что у test_eval_golden.py (маркер integration)."""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _status() -> dict | None:
    try:
        proc = subprocess.run(["supabase", "status", "-o", "json"], cwd=ROOT,
                              capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


STACK = _status()
requires_db = pytest.mark.skipif(
    STACK is None,
    reason="локальный Supabase не поднят (supabase db start && supabase db reset --local)")


@pytest.fixture(scope="session")
def service():
    from supabase import create_client
    return create_client(STACK["API_URL"], STACK["SERVICE_ROLE_KEY"])


@pytest.fixture()
def subscriber(service):
    """Свежий подписчик: auth-юзер + is_subscribed. Возвращает (client, user_id)."""
    from supabase import create_client
    email = f"ix.wave1.{uuid.uuid4().hex[:10]}@test.local"
    password = "wave1-Passw0rd"
    created = service.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True})
    uid = created.user.id
    service.table("profiles").update({"is_subscribed": True}).eq("id", uid).execute()
    client = create_client(STACK["API_URL"], STACK["ANON_KEY"])
    client.auth.sign_in_with_password({"email": email, "password": password})
    yield client, uid
    service.auth.admin.delete_user(uid)


@pytest.fixture(scope="session")
def current_ruleset(service):
    sha = "a" * 64
    # сначала снять is_current с чужих строк: частичный уникальный индекс
    # ruleset_versions_current_uidx допускает ровно одну текущую версию
    service.table("ruleset_versions").update({"is_current": False}).neq(
        "sha256", sha).eq("is_current", True).execute()
    service.table("ruleset_versions").upsert(
        {"sha256": sha, "version": "test-a", "packs": {}, "checks_count": 364,
         "is_current": True}).execute()
    return sha


@pytest.fixture(scope="session")
def tobacco_product_id(service) -> str:
    rows = service.table("products").select("id").like("hs_code", "2402%").limit(1).execute().data
    if rows:
        return rows[0]["id"]
    ins = service.table("products").insert(
        {"hs_code": "2402209000", "hierarchy_path": ["test"], "name": "test tobacco"}).execute()
    return ins.data[0]["id"]
```

(Если insert в `products` требует иных обязательных колонок — посмотреть `\d public.products` и добавить их; это тестовые данные локальной базы.)

`importer/tests/db/test_photo_runtime.py` (все тесты — `@pytest.mark.integration` + `@requires_db`):

```python
from __future__ import annotations

import pytest

from .conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]

PATHS = ["{uid}/00000000-0000-0000-0000-000000000000/0.pdf"]


def _request(client, uid, product_id, key="k1"):
    return client.rpc("request_photo_inspection", {
        "p_product_id": product_id, "p_level": "consumer", "p_markets": ["UZ"],
        "p_source_kind": "master_pdf",
        "p_asset_paths": [p.format(uid=uid) for p in PATHS],
        "p_idempotency_key": key,
    }).execute().data


def test_request_reserves_quota_and_is_idempotent(subscriber, service,
                                                  current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id = _request(client, uid, tobacco_product_id, key="idem-1")
    assert ins_id
    quota = service.table("photo_quota").select("*").eq("user_id", uid).execute().data[0]
    assert (quota["reserved"], quota["used"]) == (1, 0)
    again = _request(client, uid, tobacco_product_id, key="idem-1")
    assert again == ins_id                      # тот же ключ → та же проверка
    quota = service.table("photo_quota").select("*").eq("user_id", uid).execute().data[0]
    assert quota["reserved"] == 1               # резерв не удвоился


def test_foreign_path_prefix_is_rejected(subscriber, current_ruleset, tobacco_product_id):
    client, uid = subscriber
    with pytest.raises(Exception, match="foreign_path"):
        client.rpc("request_photo_inspection", {
            "p_product_id": tobacco_product_id, "p_level": "consumer",
            "p_markets": ["UZ"], "p_source_kind": "master_pdf",
            "p_asset_paths": ["someone-else/x/0.pdf"],
            "p_idempotency_key": "k-foreign"}).execute()


def test_finalize_done_spends_reserve(subscriber, service, current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id = _request(client, uid, tobacco_product_id, key="idem-done")
    service.rpc("finalize_photo_inspection", {
        "p_inspection_id": ins_id, "p_outcome": "done",
        "p_payload": {"overall": "review", "decided": 3, "checked": 79,
                      "findings": [], "not_checkable": [], "facts": [],
                      "model_calls": [], "assets": []}}).execute()
    quota = service.table("photo_quota").select("*").eq("user_id", uid).execute().data[0]
    assert (quota["reserved"], quota["used"]) == (0, 1)


def test_refund_only_for_closed_reason_list_and_capped(subscriber, service,
                                                       current_ruleset, tobacco_product_id):
    client, uid = subscriber
    a = _request(client, uid, tobacco_product_id, key="r1")
    service.rpc("finalize_photo_inspection",
                {"p_inspection_id": a, "p_outcome": "failed",
                 "p_reason": "worker_timeout"}).execute()
    quota = service.table("photo_quota").select("*").eq("user_id", uid).execute().data[0]
    assert (quota["reserved"], quota["used"], quota["refunds_used"]) == (0, 0, 1)
    b = _request(client, uid, tobacco_product_id, key="r2")
    service.rpc("finalize_photo_inspection",
                {"p_inspection_id": b, "p_outcome": "failed",
                 "p_reason": "no_text_layer"}).execute()   # отказ по данным — НЕ возвращается
    quota = service.table("photo_quota").select("*").eq("user_id", uid).execute().data[0]
    assert (quota["reserved"], quota["used"], quota["refunds_used"]) == (0, 1, 1)


def test_reaper_kills_stale_running_with_refund(subscriber, service,
                                                current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id = _request(client, uid, tobacco_product_id, key="stale-1")
    service.table("photo_inspections").update(
        {"status": "running",
         "heartbeat_at": "2020-01-01T00:00:00Z"}).eq("id", ins_id).execute()
    service.rpc("reap_stale_inspections", {}).execute()
    row = service.table("photo_inspections").select("status,last_error").eq(
        "id", ins_id).execute().data[0]
    assert row == {"status": "failed", "last_error": "worker_timeout"}


def test_rls_hides_foreign_inspections_and_blocks_writes(subscriber, service,
                                                         current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id = _request(client, uid, tobacco_product_id, key="rls-1")
    from supabase import create_client
    from .conftest import STACK
    stranger = create_client(STACK["API_URL"], STACK["ANON_KEY"])
    assert stranger.table("photo_inspections").select("id").eq(
        "id", ins_id).execute().data == []
    with pytest.raises(Exception):
        client.table("photo_inspections").insert(
            {"user_id": uid, "product_key": "tobacco", "packaging_level": "consumer",
             "source_kind": "photo", "idempotency_key": "hack",
             "ruleset_sha256": current_ruleset}).execute()
```

- [ ] **Step 2: Run — падает** (таблиц нет)

```bash
supabase db start && supabase db reset --local
.venv-importer/bin/python -m pip install supabase  # уже стоит (см. importer/requirements.txt)
.venv-importer/bin/python -m pytest importer/tests/db -q -m integration
```

Expected: FAIL — `relation "public.ruleset_versions" does not exist` (через PostgREST — 404/PGRST).

- [ ] **Step 3: Написать миграцию**

`supabase/migrations/20260810100000_photo_runtime.sql` — целиком:

```sql
-- Рантайм фотоконтроля упаковки (Волна 1; нормативный план docs/PHOTOCONTROL_INTEGRATION_PLAN.md §4).
-- Схема public, не pipeline: фотоконтроль — контур B (рантайм), его читает пользователь.
-- ПРОД: pg_cron и pg_net уже включены (20260804100000, 20260727120000); на свежем
-- проде pg_cron сперва разрешается в Dashboard (см. комментарий в 20260804100000).
create extension if not exists pg_cron;
create extension if not exists pg_net;

-- ── 1. Реестр версий набора правил (план §3) ────────────────────────────────
create table public.ruleset_versions (
  sha256       text primary key,
  version      text not null,
  built_at     timestamptz not null default now(),
  packs        jsonb not null default '{}'::jsonb,
  checks_count int not null default 0,
  is_current   boolean not null default false
);
create unique index ruleset_versions_current_uidx
  on public.ruleset_versions (is_current) where is_current;

alter table public.ruleset_versions enable row level security;
create policy "public read" on public.ruleset_versions
  for select to anon, authenticated using (true);
revoke insert, update, delete on public.ruleset_versions from anon, authenticated;

-- ── 2. Профили движка: какому товару собран чек-лист ────────────────────────
-- До этапа-6-выгрузки профили заданы HS-префиксами трёх категорий vision.
create table public.photo_profiles (
  profile_id  text primary key,        -- id профиля движка (config/products/*.yaml)
  title_ru    text not null,
  hs_prefixes text[] not null
);
insert into public.photo_profiles (profile_id, title_ru, hs_prefixes) values
  ('tobacco',     'Табачная продукция',  '{2402,2403}'),
  ('dairy',       'Молочная продукция',  '{0401,0402,0403,0404,0405,0406}'),
  ('electronics', 'Бытовая электроника', '{84,85}');

alter table public.photo_profiles enable row level security;
create policy "public read" on public.photo_profiles
  for select to anon, authenticated using (true);
revoke insert, update, delete on public.photo_profiles from anon, authenticated;

create or replace function public.photo_profile_for_product(p_product_id uuid)
returns text
language sql stable security definer set search_path = public
as $$
  select pp.profile_id
  from public.products p
  join public.photo_profiles pp
    on exists (select 1 from unnest(pp.hs_prefixes) pref
               where p.hs_code like pref || '%')
  where p.id = p_product_id
  limit 1;
$$;
revoke all on function public.photo_profile_for_product(uuid) from public;
grant execute on function public.photo_profile_for_product(uuid) to anon, authenticated;

-- ── 3. Проверки ─────────────────────────────────────────────────────────────
create table public.photo_inspections (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users(id) on delete cascade,
  product_id       uuid references public.products(id) on delete set null,
  product_key      text not null,      -- профиль движка (tobacco|dairy|electronics)
  packaging_level  text not null check (packaging_level in ('consumer', 'transport')),
  markets          text[] not null default '{UZ}',
  source_kind      text not null check (source_kind in ('photo', 'master_pdf')),
  status           text not null default 'queued'
                     check (status in ('queued', 'running', 'done', 'failed')),
  idempotency_key  text not null,
  heartbeat_at     timestamptz,
  overall          text,
  decided          int,
  checked          int,
  revision         int not null default 1 check (revision between 1 and 3),
  superseded_by    uuid references public.photo_inspections(id),
  stale_since      date,
  ruleset_version  text,
  ruleset_sha256   text not null references public.ruleset_versions(sha256),
  policy_applied   jsonb,
  prompt_version   text,
  model_versions   jsonb,
  reader_coverage  jsonb,
  extraction_errors jsonb,
  degraded_mode    text,
  evaluated_at     timestamptz,
  checked_at       timestamptz,
  cost_usd         numeric(10,6),
  signed_by        uuid references auth.users(id),
  signed_at        timestamptz,
  attempts         int not null default 0 check (attempts <= 2),
  last_error       text,
  created_at       timestamptz not null default now(),
  -- ключ уникален В ПРЕДЕЛАХ пользователя: одинаковый макет у двух клиентов —
  -- две независимые проверки (план §4 задаёт состав ключа, охват — наш выбор)
  unique (user_id, idempotency_key)
);
create index photo_inspections_user_idx
  on public.photo_inspections (user_id, created_at desc);
create index photo_inspections_stale_idx
  on public.photo_inspections (status) where status in ('queued', 'running');

create table public.photo_inspection_events (
  id            bigint generated always as identity primary key,
  inspection_id uuid not null references public.photo_inspections(id) on delete cascade,
  at            timestamptz not null default now(),
  stage         text not null check (stage in
                  ('received', 'prepare', 'read', 'judge', 'render', 'done', 'failed')),
  detail        jsonb not null default '{}'::jsonb
);
create index photo_inspection_events_idx
  on public.photo_inspection_events (inspection_id, at);

create table public.photo_assets (
  inspection_id uuid not null references public.photo_inspections(id) on delete cascade,
  idx           int not null,
  kind          text not null check (kind in ('photo', 'master_pdf')),
  storage_path  text not null,
  sha256        text,
  width         int,
  height        int,
  mime          text,
  face_name     text not null default 'unknown',
  usable        boolean not null default true,
  problems      jsonb not null default '[]'::jsonb,
  purged_at     timestamptz,
  primary key (inspection_id, idx)
);

create table public.photo_findings (
  id               uuid primary key default gen_random_uuid(),
  inspection_id    uuid not null references public.photo_inspections(id) on delete cascade,
  checkpoint_id    text not null,
  requirement_id   uuid references public.requirements(id) on delete set null,
  rule_ref         text not null,
  group_key        text not null,
  surface          text not null default 'any_panel',
  kind             text not null,
  severity         text not null,
  status           text not null check (status in ('pass', 'fail', 'unreadable', 'not_applicable')),
  decided_by       text not null default 'none',
  confidence_class text not null default 'needs_human'
                     check (confidence_class in ('machine_read', 'needs_human', 'not_checkable')),
  message          text not null default '',
  basis            text not null default '',
  recommendation   text,
  evidence         jsonb not null default '[]'::jsonb,
  evidence_crop_path text
);
create index photo_findings_inspection_idx on public.photo_findings (inspection_id);
create index photo_findings_requirement_idx
  on public.photo_findings (requirement_id) where requirement_id is not null;

create table public.photo_not_checkable (
  id             bigint generated always as identity primary key,
  inspection_id  uuid not null references public.photo_inspections(id) on delete cascade,
  checkpoint_key text not null,
  rule_ref       text not null default '',
  reason         text not null,
  class          text not null check (class in
                   ('метод', 'нет данных о товаре', 'нет эталона', 'нет чтеца'))
);
create index photo_not_checkable_idx on public.photo_not_checkable (inspection_id);

create table public.photo_facts (
  id            bigint generated always as identity primary key,
  inspection_id uuid not null references public.photo_inspections(id) on delete cascade,
  revision      int not null default 1,
  slot_id       text not null,
  payload       jsonb not null default '{}'::jsonb,
  -- 'system' — не источник факта, а служебная строка паспорта (__scan__ и т.п.)
  source        text not null check (source in
                  ('yolo', 'ocr', 'zbar', 'pdf_text', 'vlm', 'human', 'system')),
  confidence    real,
  asset_idx     int,
  bbox          jsonb
);
create index photo_facts_idx on public.photo_facts (inspection_id, revision);

create table public.photo_fact_overrides (
  id             uuid primary key default gen_random_uuid(),
  inspection_id  uuid not null references public.photo_inspections(id) on delete cascade,
  slot_id        text not null,
  payload        jsonb not null,
  author_user_id uuid not null references auth.users(id) on delete cascade,
  note           text not null default '',
  created_at     timestamptz not null default now()
);
create index photo_fact_overrides_idx on public.photo_fact_overrides (inspection_id);

create table public.photo_finding_actions (
  id         uuid primary key default gen_random_uuid(),
  finding_id uuid not null references public.photo_findings(id) on delete cascade,
  user_id    uuid not null references auth.users(id) on delete cascade,
  action     text not null check (action in ('fixed', 'accepted_with_reason', 'escalated')),
  reason     text,
  created_at timestamptz not null default now(),
  -- у «принять с обоснованием» обязателен текст (план §7)
  constraint action_reason_required
    check (action <> 'accepted_with_reason' or length(coalesce(reason, '')) >= 10)
);
create index photo_finding_actions_idx on public.photo_finding_actions (finding_id);

-- Калька requirement_reviews (20260729013000): заключение юриста ПО НАХОДКЕ.
-- Существующая таблица непригодна: not null FK на requirements (поправка 5 к ADR-0001).
create table public.photo_finding_reviews (
  id                  uuid primary key default gen_random_uuid(),
  finding_id          uuid not null references public.photo_findings(id) on delete cascade,
  lawyer_id           uuid not null references public.lawyer_profiles(user_id) on delete cascade,
  verdict             public.review_verdict not null,
  comment_text        text not null,
  status              public.review_status not null default 'pending',
  official_reply      text,
  official_replied_at timestamptz,
  published_at        timestamptz,
  created_at          timestamptz not null default now()
);
create index photo_finding_reviews_finding_idx
  on public.photo_finding_reviews (finding_id, status);
create unique index photo_finding_reviews_pending_uidx
  on public.photo_finding_reviews (lawyer_id, finding_id) where status = 'pending';

create table public.photo_model_calls (
  id            bigint generated always as identity primary key,
  inspection_id uuid not null references public.photo_inspections(id) on delete cascade,
  stage         text not null check (stage in ('pdf_text', 'ocr', 'vlm_shard', 'vlm_reask')),
  provider      text not null default '',
  model         text not null default '',
  tokens_in     int not null default 0,
  tokens_out    int not null default 0,
  latency_ms    int not null default 0,
  cost_usd      numeric(10, 6) not null default 0
);
create index photo_model_calls_idx on public.photo_model_calls (inspection_id);

create table public.photo_quota (
  user_id      uuid not null references auth.users(id) on delete cascade,
  period_start date not null,
  used         int not null default 0,
  reserved     int not null default 0,
  refunds_used int not null default 0,
  limit_n      int not null default 5,    -- закрытая бета: 5 проверок / 30 дней (развилка 12)
  spent_usd    numeric(10, 4) not null default 0,
  primary key (user_id, period_start)
);

-- ── 4. RLS: select только own; запись — только service_role (план §4) ───────
-- Default privileges Supabase выдают гранты всем — снимаем явно.
alter table public.photo_inspections       enable row level security;
alter table public.photo_inspection_events enable row level security;
alter table public.photo_assets            enable row level security;
alter table public.photo_findings          enable row level security;
alter table public.photo_not_checkable     enable row level security;
alter table public.photo_facts             enable row level security;
alter table public.photo_fact_overrides    enable row level security;
alter table public.photo_finding_actions   enable row level security;
alter table public.photo_finding_reviews   enable row level security;
alter table public.photo_model_calls       enable row level security;
alter table public.photo_quota             enable row level security;

revoke insert, update, delete on public.photo_inspections,
  public.photo_inspection_events, public.photo_assets, public.photo_findings,
  public.photo_not_checkable, public.photo_facts, public.photo_fact_overrides,
  public.photo_finding_actions, public.photo_finding_reviews,
  public.photo_model_calls, public.photo_quota
  from anon, authenticated;

create policy "own read" on public.photo_inspections
  for select to authenticated using (user_id = (select auth.uid()));

create policy "own read" on public.photo_inspection_events
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_assets
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_findings
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_not_checkable
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_facts
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_fact_overrides
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_finding_actions
  for select to authenticated using (exists (
    select 1 from public.photo_findings f
    join public.photo_inspections i on i.id = f.inspection_id
    where f.id = finding_id and i.user_id = (select auth.uid())));

-- Заключения: владелец проверки видит опубликованные, юрист — свои.
create policy "owner reads published" on public.photo_finding_reviews
  for select to authenticated using (
    status = 'published' and exists (
      select 1 from public.photo_findings f
      join public.photo_inspections i on i.id = f.inspection_id
      where f.id = finding_id and i.user_id = (select auth.uid())));
create policy "lawyer reads own" on public.photo_finding_reviews
  for select to authenticated using (lawyer_id = (select auth.uid()));
-- Осознанное исключение из «пишет только service_role»: калька контура ADR-0001 —
-- verified-юрист вставляет заключение сам, статус всегда default 'pending'.
grant insert (finding_id, lawyer_id, verdict, comment_text)
  on public.photo_finding_reviews to authenticated;
create policy "verified lawyer insert" on public.photo_finding_reviews
  for insert to authenticated
  with check (lawyer_id = (select auth.uid()) and public.is_verified_lawyer());

create policy "own read" on public.photo_model_calls
  for select to authenticated using (exists (
    select 1 from public.photo_inspections i
    where i.id = inspection_id and i.user_id = (select auth.uid())));

create policy "own read" on public.photo_quota
  for select to authenticated using (user_id = (select auth.uid()));

-- ── 5. RPC: единственный вход (план §4) ─────────────────────────────────────
create or replace function public.request_photo_inspection(
  p_product_id uuid, p_level text, p_markets text[], p_source_kind text,
  p_asset_paths text[], p_idempotency_key text)
returns uuid
language plpgsql security definer set search_path = public
as $$
declare
  v_uid     uuid := (select auth.uid());
  v_profile text;
  v_sha     text;
  v_version text;
  v_period  date := date_trunc('month', now())::date;
  v_id      uuid;
  v_path    text;
  v_i       int := 0;
begin
  if v_uid is null then raise exception 'not_authenticated'; end if;
  if not public.is_subscriber() then raise exception 'not_subscriber'; end if;
  if p_source_kind not in ('photo', 'master_pdf') then raise exception 'bad_source_kind'; end if;
  if p_level not in ('consumer', 'transport') then raise exception 'bad_level'; end if;
  if p_source_kind = 'photo' and coalesce(array_length(p_asset_paths, 1), 0) < 4 then
    raise exception 'need_four_photos';   -- первый ключ покрытия (план §2Б шаг 3)
  end if;
  if p_source_kind = 'master_pdf' and coalesce(array_length(p_asset_paths, 1), 0) <> 1 then
    raise exception 'need_single_pdf';
  end if;
  foreach v_path in array p_asset_paths loop
    if position(v_uid::text || '/' in v_path) <> 1 then
      raise exception 'foreign_path';     -- путь обязан начинаться с <uid>/
    end if;
  end loop;

  v_profile := public.photo_profile_for_product(p_product_id);
  if v_profile is null then raise exception 'no_checklist'; end if;

  select sha256, version into v_sha, v_version
    from public.ruleset_versions where is_current;
  if v_sha is null then raise exception 'no_ruleset'; end if;

  -- идемпотентность: тот же ключ → та же проверка, без второго резерва
  select id into v_id from public.photo_inspections
   where user_id = v_uid and idempotency_key = p_idempotency_key;
  if v_id is not null then return v_id; end if;

  -- атомарный резерв квоты (не count(*): гонка на границе лимита)
  insert into public.photo_quota as q (user_id, period_start, reserved)
  values (v_uid, v_period, 1)
  on conflict (user_id, period_start) do update
    set reserved = q.reserved + 1
    where q.used + q.reserved < q.limit_n;
  if not found then raise exception 'quota_exhausted'; end if;

  insert into public.photo_inspections
    (user_id, product_id, product_key, packaging_level, markets, source_kind,
     idempotency_key, ruleset_sha256, ruleset_version)
  values (v_uid, p_product_id, v_profile, p_level, p_markets, p_source_kind,
          p_idempotency_key, v_sha, v_version)
  returning id into v_id;

  foreach v_path in array p_asset_paths loop
    insert into public.photo_assets (inspection_id, idx, kind, storage_path, mime)
    values (v_id, v_i, p_source_kind,
            v_path, case when p_source_kind = 'master_pdf'
                         then 'application/pdf' else 'image/jpeg' end);
    v_i := v_i + 1;
  end loop;

  insert into public.photo_inspection_events (inspection_id, stage, detail)
  values (v_id, 'received', jsonb_build_object('assets', v_i));
  return v_id;
end;
$$;
revoke all on function public.request_photo_inspection(uuid, text, text[], text, text[], text) from public;
grant execute on function public.request_photo_inspection(uuid, text, text[], text, text[], text) to authenticated;

-- Досъёмка: та же проверка, revision+1, БЕЗ нового резерва (план §6 механизм 5).
create or replace function public.request_photo_retake(
  p_inspection_id uuid, p_new_asset_paths text[], p_idempotency_key text)
returns uuid
language plpgsql security definer set search_path = public
as $$
declare
  v_uid  uuid := (select auth.uid());
  parent public.photo_inspections%rowtype;
  v_id   uuid;
  v_path text;
  v_i    int;
begin
  select * into parent from public.photo_inspections
   where id = p_inspection_id and user_id = v_uid;
  if not found then raise exception 'inspection_not_found'; end if;
  if parent.source_kind <> 'photo' then raise exception 'retake_is_for_photos'; end if;
  if parent.status <> 'done' then raise exception 'parent_not_done'; end if;
  if parent.revision >= 3 then
    raise exception 'revision_limit';     -- четвёртая досъёмка = новая единица квоты
  end if;
  foreach v_path in array p_new_asset_paths loop
    if position(v_uid::text || '/' in v_path) <> 1 then raise exception 'foreign_path'; end if;
  end loop;

  insert into public.photo_inspections
    (user_id, product_id, product_key, packaging_level, markets, source_kind,
     idempotency_key, ruleset_sha256, ruleset_version, revision)
  select user_id, product_id, product_key, packaging_level, markets, source_kind,
         p_idempotency_key, r.sha256, r.version, parent.revision + 1
  from public.photo_inspections p, public.ruleset_versions r
  where p.id = p_inspection_id and r.is_current
  returning id into v_id;

  -- старые кадры переезжают в новую ревизию (переиспользуются, не переизвлекаются)
  insert into public.photo_assets (inspection_id, idx, kind, storage_path, sha256,
                                   width, height, mime, face_name, usable, problems)
  select v_id, idx, kind, storage_path, sha256, width, height, mime, face_name, usable, problems
  from public.photo_assets where inspection_id = p_inspection_id;

  select coalesce(max(idx) + 1, 0) into v_i
    from public.photo_assets where inspection_id = v_id;
  foreach v_path in array p_new_asset_paths loop
    insert into public.photo_assets (inspection_id, idx, kind, storage_path, mime)
    values (v_id, v_i, 'photo', v_path, 'image/jpeg');
    v_i := v_i + 1;
  end loop;

  update public.photo_inspections set superseded_by = v_id where id = p_inspection_id;
  insert into public.photo_inspection_events (inspection_id, stage, detail)
  values (v_id, 'received', jsonb_build_object('retake_of', p_inspection_id));
  return v_id;
end;
$$;
revoke all on function public.request_photo_retake(uuid, text[], text) from public;
grant execute on function public.request_photo_retake(uuid, text[], text) to authenticated;

-- ── 6. Финализация: единственная точка перехода done|failed (план §4) ───────
create or replace function public.finalize_photo_inspection(
  p_inspection_id uuid, p_outcome text, p_reason text default null,
  p_payload jsonb default null)
returns void
language plpgsql security definer set search_path = public
as $$
declare
  v public.photo_inspections%rowtype;
  v_period date;
  refundable constant text[] := array[
    'worker_unreachable', 'worker_timeout', 'dispatch_lost',
    'ruleset_drift', 'ocr_unavailable', 'vlm_unavailable'];
begin
  select * into v from public.photo_inspections
   where id = p_inspection_id for update;
  if not found then raise exception 'inspection_not_found'; end if;
  if v.status not in ('queued', 'running') then return; end if;  -- идемпотентно
  v_period := date_trunc('month', v.created_at)::date;

  if p_outcome = 'done' then
    update public.photo_inspections set
      status = 'done', checked_at = now(), last_error = null,
      overall          = p_payload ->> 'overall',
      decided          = (p_payload ->> 'decided')::int,
      checked          = (p_payload ->> 'checked')::int,
      reader_coverage  = p_payload -> 'reader_coverage',
      policy_applied   = p_payload -> 'policy_applied',
      extraction_errors = p_payload -> 'extraction_errors',
      degraded_mode    = p_payload ->> 'degraded_mode',
      prompt_version   = p_payload ->> 'prompt_version',
      model_versions   = p_payload -> 'model_versions',
      evaluated_at     = nullif(p_payload ->> 'evaluated_at', '')::timestamptz,
      cost_usd         = coalesce((p_payload ->> 'cost_usd')::numeric, 0)
    where id = p_inspection_id;

    insert into public.photo_findings
      (inspection_id, checkpoint_id, requirement_id, rule_ref, group_key, surface,
       kind, severity, status, decided_by, confidence_class, message, basis,
       recommendation, evidence, evidence_crop_path)
    select p_inspection_id, f ->> 'checkpoint_id',
           nullif(f ->> 'requirement_id', '')::uuid,
           f ->> 'rule_ref', f ->> 'group_key', coalesce(f ->> 'surface', 'any_panel'),
           f ->> 'kind', f ->> 'severity', f ->> 'status',
           coalesce(f ->> 'decided_by', 'none'),
           coalesce(f ->> 'confidence_class', 'needs_human'),
           coalesce(f ->> 'message', ''), coalesce(f ->> 'basis', ''),
           f ->> 'recommendation', coalesce(f -> 'evidence', '[]'::jsonb),
           f ->> 'evidence_crop_path'
    from jsonb_array_elements(coalesce(p_payload -> 'findings', '[]'::jsonb)) f;

    insert into public.photo_not_checkable (inspection_id, checkpoint_key, rule_ref, reason, class)
    select p_inspection_id, n ->> 'checkpoint_key', coalesce(n ->> 'rule_ref', ''),
           n ->> 'reason', n ->> 'klass'
    from jsonb_array_elements(coalesce(p_payload -> 'not_checkable', '[]'::jsonb)) n;

    insert into public.photo_facts (inspection_id, revision, slot_id, payload, source,
                                    confidence, asset_idx, bbox)
    select p_inspection_id, v.revision, r ->> 'slot_id',
           coalesce(r -> 'payload', '{}'::jsonb), r ->> 'source',
           (r ->> 'confidence')::real, (r ->> 'asset_idx')::int, r -> 'bbox'
    from jsonb_array_elements(coalesce(p_payload -> 'facts', '[]'::jsonb)) r;

    insert into public.photo_model_calls (inspection_id, stage, provider, model,
                                          tokens_in, tokens_out, latency_ms, cost_usd)
    select p_inspection_id, m ->> 'stage', coalesce(m ->> 'provider', ''),
           coalesce(m ->> 'model', ''), coalesce((m ->> 'tokens_in')::int, 0),
           coalesce((m ->> 'tokens_out')::int, 0), coalesce((m ->> 'latency_ms')::int, 0),
           coalesce((m ->> 'cost_usd')::numeric, 0)
    from jsonb_array_elements(coalesce(p_payload -> 'model_calls', '[]'::jsonb)) m;

    update public.photo_assets a set
      sha256 = x.sha256, width = x.width, height = x.height, mime = x.mime,
      face_name = x.face_name, usable = x.usable, problems = x.problems
    from (select (e ->> 'idx')::int idx, e ->> 'sha256' sha256,
                 (e ->> 'width')::int width, (e ->> 'height')::int height,
                 e ->> 'mime' mime, coalesce(e ->> 'face_name', 'unknown') face_name,
                 coalesce((e ->> 'usable')::boolean, true) usable,
                 coalesce(e -> 'problems', '[]'::jsonb) problems
          from jsonb_array_elements(coalesce(p_payload -> 'assets', '[]'::jsonb)) e) x
    where a.inspection_id = p_inspection_id and a.idx = x.idx;

    update public.photo_quota set reserved = greatest(reserved - 1, 0), used = used + 1,
      spent_usd = spent_usd + coalesce((p_payload ->> 'cost_usd')::numeric, 0)
    where user_id = v.user_id and period_start = v_period;

  elsif p_outcome = 'failed' then
    update public.photo_inspections
      set status = 'failed', checked_at = now(), last_error = p_reason
      where id = p_inspection_id;
    if p_reason = any (refundable) then
      -- возврат — только по закрытому списку причин и не больше 3 за период
      update public.photo_quota
        set reserved = greatest(reserved - 1, 0),
            refunds_used = refunds_used + 1
        where user_id = v.user_id and period_start = v_period and refunds_used < 3;
      if not found then
        update public.photo_quota
          set reserved = greatest(reserved - 1, 0), used = used + 1
          where user_id = v.user_id and period_start = v_period;
      end if;
    else
      -- отказ по данным (no_text_layer, asset_fetch_failed, checklist_empty…)
      update public.photo_quota
        set reserved = greatest(reserved - 1, 0), used = used + 1
        where user_id = v.user_id and period_start = v_period;
    end if;
  else
    raise exception 'bad_outcome';
  end if;

  insert into public.photo_inspection_events (inspection_id, stage, detail)
  values (p_inspection_id,
          case when p_outcome = 'done' then 'done' else 'failed' end,
          jsonb_build_object('reason', p_reason));
end;
$$;
revoke all on function public.finalize_photo_inspection(uuid, text, text, jsonb) from public;
revoke all on function public.finalize_photo_inspection(uuid, text, text, jsonb) from anon, authenticated;
grant execute on function public.finalize_photo_inspection(uuid, text, text, jsonb) to service_role;

-- ── 7. Ревизия после пересуда (правка факта; план §6 механизм 5, этап 5) ────
create or replace function public.create_photo_revision(
  p_parent_id uuid, p_payload jsonb)
returns uuid
language plpgsql security definer set search_path = public
as $$
declare
  parent public.photo_inspections%rowtype;
  v_id uuid;
begin
  select * into parent from public.photo_inspections where id = p_parent_id for update;
  if not found then raise exception 'inspection_not_found'; end if;
  if parent.revision >= 3 then raise exception 'revision_limit'; end if;

  insert into public.photo_inspections
    (user_id, product_id, product_key, packaging_level, markets, source_kind,
     idempotency_key, ruleset_sha256, ruleset_version, revision, status,
     overall, decided, checked, reader_coverage, policy_applied, degraded_mode,
     evaluated_at, checked_at, cost_usd)
  values (parent.user_id, parent.product_id, parent.product_key,
          parent.packaging_level, parent.markets, parent.source_kind,
          parent.idempotency_key || ':r' || (parent.revision + 1),
          parent.ruleset_sha256, parent.ruleset_version, parent.revision + 1, 'done',
          p_payload ->> 'overall', (p_payload ->> 'decided')::int,
          (p_payload ->> 'checked')::int, p_payload -> 'reader_coverage',
          p_payload -> 'policy_applied', parent.degraded_mode,
          parent.evaluated_at, now(), 0)
  returning id into v_id;

  insert into public.photo_assets (inspection_id, idx, kind, storage_path, sha256,
                                   width, height, mime, face_name, usable, problems)
  select v_id, idx, kind, storage_path, sha256, width, height, mime, face_name,
         usable, problems
  from public.photo_assets where inspection_id = p_parent_id;

  insert into public.photo_findings
    (inspection_id, checkpoint_id, requirement_id, rule_ref, group_key, surface,
     kind, severity, status, decided_by, confidence_class, message, basis,
     recommendation, evidence, evidence_crop_path)
  select v_id, f ->> 'checkpoint_id', nullif(f ->> 'requirement_id', '')::uuid,
         f ->> 'rule_ref', f ->> 'group_key', coalesce(f ->> 'surface', 'any_panel'),
         f ->> 'kind', f ->> 'severity', f ->> 'status',
         coalesce(f ->> 'decided_by', 'none'),
         coalesce(f ->> 'confidence_class', 'needs_human'),
         coalesce(f ->> 'message', ''), coalesce(f ->> 'basis', ''),
         f ->> 'recommendation', coalesce(f -> 'evidence', '[]'::jsonb),
         f ->> 'evidence_crop_path'
  from jsonb_array_elements(coalesce(p_payload -> 'findings', '[]'::jsonb)) f;

  insert into public.photo_not_checkable (inspection_id, checkpoint_key, rule_ref, reason, class)
  select v_id, n ->> 'checkpoint_key', coalesce(n ->> 'rule_ref', ''),
         n ->> 'reason', n ->> 'klass'
  from jsonb_array_elements(coalesce(p_payload -> 'not_checkable', '[]'::jsonb)) n;

  insert into public.photo_facts (inspection_id, revision, slot_id, payload, source,
                                  confidence, asset_idx, bbox)
  select v_id, parent.revision + 1, r ->> 'slot_id',
         coalesce(r -> 'payload', '{}'::jsonb), r ->> 'source',
         (r ->> 'confidence')::real, (r ->> 'asset_idx')::int, r -> 'bbox'
  from jsonb_array_elements(coalesce(p_payload -> 'facts', '[]'::jsonb)) r;

  update public.photo_inspections set superseded_by = v_id where id = p_parent_id;
  insert into public.photo_inspection_events (inspection_id, stage, detail)
  values (v_id, 'done', jsonb_build_object('rejudge_of', p_parent_id));
  return v_id;
end;
$$;
revoke all on function public.create_photo_revision(uuid, jsonb) from public;
revoke all on function public.create_photo_revision(uuid, jsonb) from anon, authenticated;
grant execute on function public.create_photo_revision(uuid, jsonb) to service_role;

-- ── 8. Действия по находке и подпись (план §7, §8; этап 5) ──────────────────
create or replace function public.record_finding_action(
  p_finding_id uuid, p_action text, p_reason text default null)
returns uuid
language plpgsql security definer set search_path = public
as $$
declare
  v_uid uuid := (select auth.uid());
  v_id uuid;
begin
  if v_uid is null then raise exception 'not_authenticated'; end if;
  if not exists (
      select 1 from public.photo_findings f
      join public.photo_inspections i on i.id = f.inspection_id
      where f.id = p_finding_id and i.user_id = v_uid) then
    raise exception 'finding_not_found';
  end if;
  insert into public.photo_finding_actions (finding_id, user_id, action, reason)
  values (p_finding_id, v_uid, p_action, p_reason)
  returning id into v_id;
  return v_id;
end;
$$;
revoke all on function public.record_finding_action(uuid, text, text) from public;
grant execute on function public.record_finding_action(uuid, text, text) to authenticated;

-- Подпись: вердикт с fail или критичной находкой не окончателен без неё (§8).
create or replace function public.sign_photo_inspection(p_inspection_id uuid)
returns void
language plpgsql security definer set search_path = public
as $$
declare
  v_uid uuid := (select auth.uid());
begin
  if not public.is_verified_lawyer() then raise exception 'not_a_verified_lawyer'; end if;
  update public.photo_inspections
    set signed_by = v_uid, signed_at = now()
    where id = p_inspection_id and status = 'done' and signed_by is null;
  if not found then raise exception 'nothing_to_sign'; end if;
end;
$$;
revoke all on function public.sign_photo_inspection(uuid) from public;
grant execute on function public.sign_photo_inspection(uuid) to authenticated;

-- ── 9. Реперная джоба: никто не висит в queued/running вечно (план §4, §6) ──
create or replace function public.reap_stale_inspections()
returns int
language plpgsql security definer set search_path = public
as $$
declare
  r record;
  n int := 0;
begin
  for r in select id from public.photo_inspections
            where status = 'running' and heartbeat_at < now() - interval '3 minutes'
  loop
    perform public.finalize_photo_inspection(r.id, 'failed', 'worker_timeout');
    n := n + 1;
  end loop;
  for r in select id from public.photo_inspections
            where status = 'queued' and created_at < now() - interval '5 minutes'
  loop
    perform public.finalize_photo_inspection(r.id, 'failed', 'dispatch_lost');
    n := n + 1;
  end loop;
  return n;
end;
$$;
revoke all on function public.reap_stale_inspections() from public;
revoke all on function public.reap_stale_inspections() from anon, authenticated;
grant execute on function public.reap_stale_inspections() to service_role;

-- ── 10. Ретеншн 30 дней — механизм, а не обещание (план §4) ─────────────────
-- Секреты (завести владельцу ПОСЛЕ наката, гейт А6 Волны 3):
--   select vault.create_secret('https://<project>.supabase.co', 'supabase_project_url', 'Storage API');
--   select vault.create_secret('<service_role key>', 'supabase_service_role_key', 'Storage delete');
-- Пока секретов нет — джоба молча пропускает удаление (как notify_admin_telegram).
create or replace function public.purge_expired_photo_assets()
returns int
language plpgsql security definer set search_path = public, net, extensions
as $$
declare
  base_url text;
  srv_key  text;
  r record;
  n int := 0;
begin
  select decrypted_secret into base_url
    from vault.decrypted_secrets where name = 'supabase_project_url';
  select decrypted_secret into srv_key
    from vault.decrypted_secrets where name = 'supabase_service_role_key';
  if base_url is null or srv_key is null then
    raise warning 'purge_expired_photo_assets: секреты Vault не заведены, пропуск';
    return 0;
  end if;
  for r in
    select a.inspection_id, a.idx, a.storage_path,
           case a.kind when 'master_pdf' then 'packaging-artwork'
                       else 'packaging-photos' end as bucket
    from public.photo_assets a
    join public.photo_inspections i on i.id = a.inspection_id
    where a.purged_at is null
      and i.created_at < now() - interval '30 days'
    limit 500
  loop
    perform net.http_delete(
      url := base_url || '/storage/v1/object/' || r.bucket || '/' || r.storage_path,
      headers := jsonb_build_object('Authorization', 'Bearer ' || srv_key));
    update public.photo_assets set purged_at = now()
      where inspection_id = r.inspection_id and idx = r.idx;
    n := n + 1;
  end loop;
  return n;
exception when others then
  raise warning 'purge_expired_photo_assets: %', sqlerrm;
  return n;
end;
$$;
revoke all on function public.purge_expired_photo_assets() from public;
revoke all on function public.purge_expired_photo_assets() from anon, authenticated;
grant execute on function public.purge_expired_photo_assets() to service_role;

-- Расписания (идемпотентно, по образцу 20260804100000)
do $$
begin
  if not exists (select 1 from cron.job where jobname = 'photo-reap-stale') then
    perform cron.schedule('photo-reap-stale', '* * * * *',
      $cron$select public.reap_stale_inspections()$cron$);
  end if;
  if not exists (select 1 from cron.job where jobname = 'photo-purge-assets') then
    perform cron.schedule('photo-purge-assets', '30 2 * * *',
      $cron$select public.purge_expired_photo_assets()$cron$);
  end if;
end;
$$;
```

- [ ] **Step 4: Накатить локально и прогнать тесты**

```bash
supabase db reset --local
.venv-importer/bin/python -m pytest importer/tests/db -q -m integration
```

Expected: PASS все тесты Step 1. Если `supabase db reset` упал на миграции — читать ошибку, чинить SQL, повторять; на прод ничего не уехало (мы в ветке).

- [ ] **Step 5: supabase db lint + общий pytest + commit**

```bash
supabase db lint
.venv-importer/bin/python -m pytest importer/tests -q
git add supabase/migrations/20260810100000_photo_runtime.sql importer/tests/db
git commit -m "feat(db): рантайм фотоконтроля — 13 таблиц, RPC резерва квоты, репер, ретеншн"
```

---

### Task 9: Миграция 20260810110000_photo_storage.sql — три приватных бакета

**Files:**
- Create: `supabase/migrations/20260810110000_photo_storage.sql`, `importer/tests/db/test_photo_storage.py`

**Interfaces:**
- Consumes: Task 8 (конфтест).
- Produces: бакеты `packaging-artwork` (pdf, 50 МБ), `packaging-photos` (jpeg/png/heic/heif, 10 МБ), `evidence-crops` (jpeg/png, 2 МБ); политики на `storage.objects` по `(storage.foldername(name))[1] = auth.uid()::text`.

- [ ] **Step 1: Failing-тест — свой префикс работает, чужой закрыт**

`importer/tests/db/test_photo_storage.py`:

```python
from __future__ import annotations

import pytest

from .conftest import STACK, requires_db

pytestmark = [pytest.mark.integration, requires_db]

PDF_BYTES = b"%PDF-1.4 test"


def _bucket_field(bucket, name):
    return getattr(bucket, name, None) if not isinstance(bucket, dict) else bucket.get(name)


def test_buckets_exist_with_limits(service):
    rows = {_bucket_field(b, "id"): b for b in service.storage.list_buckets()}
    assert set(rows) >= {"packaging-artwork", "packaging-photos", "evidence-crops"}
    assert _bucket_field(rows["packaging-artwork"], "file_size_limit") == 52428800
    assert _bucket_field(rows["packaging-photos"], "file_size_limit") == 10485760
    assert "image/heic" in _bucket_field(rows["packaging-photos"], "allowed_mime_types")


def test_own_prefix_write_and_read(subscriber):
    client, uid = subscriber
    path = f"{uid}/test-inspection/0.pdf"
    client.storage.from_("packaging-artwork").upload(
        path, PDF_BYTES, {"content-type": "application/pdf"})
    got = client.storage.from_("packaging-artwork").download(path)
    assert got == PDF_BYTES


def test_foreign_prefix_is_sealed(subscriber, service):
    """Главная проверка риска 8: чужой префикс не читается и не пишется."""
    client, uid = subscriber
    own_path = f"{uid}/seal/0.pdf"
    client.storage.from_("packaging-artwork").upload(
        own_path, PDF_BYTES, {"content-type": "application/pdf"})
    from supabase import create_client
    stranger = create_client(STACK["API_URL"], STACK["ANON_KEY"])
    with pytest.raises(Exception):
        stranger.storage.from_("packaging-artwork").download(own_path)
    with pytest.raises(Exception):
        stranger.storage.from_("packaging-artwork").upload(
            f"{uid}/seal/1.pdf", PDF_BYTES, {"content-type": "application/pdf"})
```

(Форму ответа `list_buckets()` supabase-py подстроить по факту — dict или объект; тест правится под библиотеку, не наоборот.)

- [ ] **Step 2: Run — падает** (бакетов нет)

Run: `.venv-importer/bin/python -m pytest importer/tests/db/test_photo_storage.py -q -m integration`

- [ ] **Step 3: Миграция**

`supabase/migrations/20260810110000_photo_storage.sql`:

```sql
-- Три приватных бакета фотоконтроля (план §4, таблица Storage).
-- HEIC/HEIF в whitelist — без него загрузка с айфона падает на первом клиенте.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('packaging-artwork', 'packaging-artwork', false, 52428800,
   array['application/pdf']),
  ('packaging-photos', 'packaging-photos', false, 10485760,
   array['image/jpeg', 'image/png', 'image/heic', 'image/heif']),
  ('evidence-crops', 'evidence-crops', false, 2097152,
   array['image/jpeg', 'image/png'])
on conflict (id) do nothing;

-- Политики: владелец префикса <uid>/... читает и пишет своё; всё остальное закрыто.
-- Кропы пользователь только читает: пишет их сервер (service_role, мимо RLS).
create policy "photo owners read" on storage.objects
  for select to authenticated
  using (bucket_id in ('packaging-artwork', 'packaging-photos', 'evidence-crops')
         and (storage.foldername(name))[1] = auth.uid()::text);

create policy "photo owners upload" on storage.objects
  for insert to authenticated
  with check (bucket_id in ('packaging-artwork', 'packaging-photos')
              and (storage.foldername(name))[1] = auth.uid()::text);

-- update/delete намеренно НЕ выдаются: кадры immutable, удаляет ретеншн-джоба.
```

- [ ] **Step 4: Накат, тесты, commit**

```bash
supabase db reset --local
.venv-importer/bin/python -m pytest importer/tests/db -q -m integration
supabase db lint
git add supabase/migrations/20260810110000_photo_storage.sql importer/tests/db/test_photo_storage.py
git commit -m "feat(db): три приватных бакета фотоконтроля, политики по префиксу uid"
```

---

### Task 10: Vercel-функции api/vision/* и общий api/_lib/vision.ts

**Files:**
- Create: `api/_lib/vision.ts`, `api/_lib/vision.test.ts`, `api/vision/check.ts`, `api/vision/checklist.ts`, `api/vision/progress.ts`, `api/vision/ruleset.ts`, `api/vision/rejudge.ts`
- Modify: `vercel.json` (maxDuration)

**Interfaces:**
- Consumes: Task 8 (RPC/таблицы, типы после регенерации — Task 11 Step 1 можно выполнить раньше этой задачи), контракт воркера из Task 7 (`InspectRequest`/`InspectResponse`/`RejudgeRequest` — поля дословно).
- Produces (контракт для фронта, Task 11–13):
  - `POST /api/vision/check` — `Authorization: Bearer <jwt>`, body `{ inspectionId: string }` → `202 {status:'accepted'}` немедленного ответа НЕТ: функция синхронно доводит до финала и отвечает `200 {status:'done'|'failed', reason?}` (фронт всё равно живёт поллингом событий);
  - `GET /api/vision/checklist?product=<uuid>&level=consumer|transport` → `200 {profile, title, groups:[...], counters:{checkable,partial,notCheckable,noGold}}` | `404 {reason:'no_checklist'}`; `Cache-Control: public, s-maxage=300`;
  - `POST /api/vision/progress` — `X-Worker-Secret`, body `{inspection_id, stage, detail}` → insert события + `heartbeat_at=now()`;
  - `POST /api/vision/ruleset` — `X-Worker-Secret`, body fingerprint → upsert + снятие `is_current` с предыдущей;
  - `POST /api/vision/rejudge` — `Bearer <jwt>`, body `{inspectionId, overrides:[{slotId, payload, note}]}` → `200 {inspectionId: <новая ревизия>}`;
  - `api/_lib/vision.ts` экспортирует: `adminClient()`, `getUserFromRequest(req): Promise<{id: string} | null>`, `requireWorkerSecret(req): boolean`, `assertOwnPrefix(paths: string[], userId: string): boolean`, `bucketFor(kind: 'photo'|'master_pdf'): string`, `REFUNDABLE_REASONS`.

- [ ] **Step 1: Failing vitest на чистые хелперы**

`api/_lib/vision.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { assertOwnPrefix, bucketFor, REFUNDABLE_REASONS } from './vision.js'

describe('assertOwnPrefix', () => {
  const uid = '3f2b8c1d-0000-4000-8000-000000000001'
  it('свой префикс проходит', () => {
    expect(assertOwnPrefix([`${uid}/abc/0.jpg`], uid)).toBe(true)
  })
  it('чужой префикс и обход через ../ отклоняются', () => {
    expect(assertOwnPrefix(['other/abc/0.jpg'], uid)).toBe(false)
    expect(assertOwnPrefix([`${uid}/../other/0.jpg`], uid)).toBe(false)
    expect(assertOwnPrefix([], uid)).toBe(false)
  })
})

describe('bucketFor', () => {
  it('kind → бакет', () => {
    expect(bucketFor('master_pdf')).toBe('packaging-artwork')
    expect(bucketFor('photo')).toBe('packaging-photos')
  })
})

it('список возвратных причин закрыт и совпадает с миграцией', () => {
  expect([...REFUNDABLE_REASONS].sort()).toEqual([
    'dispatch_lost', 'ocr_unavailable', 'ruleset_drift',
    'vlm_unavailable', 'worker_timeout', 'worker_unreachable',
  ])
})
```

Run: `npm run test` → FAIL (модуля нет).

- [ ] **Step 2: `api/_lib/vision.ts`**

По образцу `api/calendar/[token].ts` (импорты с `.js`, `createClient<Database>`, env `SUPABASE_URL ?? VITE_SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`):

```ts
// Общий слой api/vision/*: админ-клиент, аутентификация, проверки путей.
// SUPABASE_SERVICE_ROLE_KEY живёт только в process.env на сервере (вне src/).
import type { VercelRequest } from '@vercel/node'
import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import type { Database } from '../../src/lib/database.types.js'

export const REFUNDABLE_REASONS = new Set([
  'worker_unreachable', 'worker_timeout', 'dispatch_lost',
  'ruleset_drift', 'ocr_unavailable', 'vlm_unavailable',
])

export function adminClient(): SupabaseClient<Database> {
  const url = process.env.SUPABASE_URL ?? process.env.VITE_SUPABASE_URL
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY
  if (!url || !key) throw new Error('missing SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY')
  return createClient<Database>(url, key, { auth: { persistSession: false } })
}

export async function getUserFromRequest(
  req: VercelRequest,
): Promise<{ id: string } | null> {
  const header = req.headers.authorization ?? ''
  const jwt = header.startsWith('Bearer ') ? header.slice(7) : ''
  if (!jwt) return null
  const { data, error } = await adminClient().auth.getUser(jwt)
  if (error || !data.user) return null
  return { id: data.user.id }
}

export function requireWorkerSecret(req: VercelRequest): boolean {
  const secret = process.env.VISION_WORKER_SECRET
  return Boolean(secret) && req.headers['x-worker-secret'] === secret
}

export function assertOwnPrefix(paths: string[], userId: string): boolean {
  if (paths.length === 0) return false
  return paths.every(
    (p) => p.startsWith(`${userId}/`) && !p.includes('..'),
  )
}

export function bucketFor(kind: 'photo' | 'master_pdf'): string {
  return kind === 'master_pdf' ? 'packaging-artwork' : 'packaging-photos'
}

export function workerUrl(): string {
  const url = process.env.VISION_WORKER_URL
  if (!url) throw new Error('missing VISION_WORKER_URL')
  return url.replace(/\/$/, '')
}
```

Run: `npm run test` → PASS (test-файл из Step 1).

- [ ] **Step 3: `api/vision/progress.ts` и `api/vision/ruleset.ts`** (простые, воркер-каналы)

`api/vision/progress.ts`:

```ts
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { adminClient, requireWorkerSecret } from '../_lib/vision.js'

const STAGES = new Set(['received', 'prepare', 'read', 'judge', 'render', 'done', 'failed'])

export default async function handler(req: VercelRequest, res: VercelResponse): Promise<void> {
  if (req.method !== 'POST') { res.status(405).json({ reason: 'method' }); return }
  if (!requireWorkerSecret(req)) { res.status(401).json({ reason: 'secret' }); return }
  const { inspection_id: inspectionId, stage, detail } = req.body ?? {}
  if (!inspectionId || !STAGES.has(stage)) { res.status(422).json({ reason: 'bad_body' }); return }
  const db = adminClient()
  const { error } = await db.from('photo_inspection_events').insert({
    inspection_id: inspectionId, stage, detail: detail ?? {},
  })
  if (error) { res.status(500).json({ reason: error.message }); return }
  // пульс для реперной джобы — на каждой стадии
  await db.from('photo_inspections')
    .update({ heartbeat_at: new Date().toISOString() })
    .eq('id', inspectionId)
  res.status(200).json({ ok: true })
}
```

`api/vision/ruleset.ts`:

```ts
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { adminClient, requireWorkerSecret } from '../_lib/vision.js'

export default async function handler(req: VercelRequest, res: VercelResponse): Promise<void> {
  if (req.method !== 'POST') { res.status(405).json({ reason: 'method' }); return }
  if (!requireWorkerSecret(req)) { res.status(401).json({ reason: 'secret' }); return }
  const { sha256, version, built_at: builtAt, packs, checks_count: checksCount } = req.body ?? {}
  if (typeof sha256 !== 'string' || sha256.length !== 64 || !version) {
    res.status(422).json({ reason: 'bad_fingerprint' }); return
  }
  const db = adminClient()
  // снять is_current с предыдущей, поднять новую — воркер передеплоился
  const { error: clearError } = await db.from('ruleset_versions')
    .update({ is_current: false }).eq('is_current', true).neq('sha256', sha256)
  if (clearError) { res.status(500).json({ reason: clearError.message }); return }
  const { error } = await db.from('ruleset_versions').upsert({
    sha256, version, built_at: builtAt ?? new Date().toISOString(),
    packs: packs ?? {}, checks_count: checksCount ?? 0, is_current: true,
  })
  if (error) { res.status(500).json({ reason: error.message }); return }
  res.status(200).json({ ok: true })
}
```

- [ ] **Step 4: `api/vision/check.ts` — оркестратор прогона**

```ts
// Синхронный мост: JWT → проверка владения → signed URLs → воркер →
// финализация ОДНОЙ транзакцией (RPC finalize_photo_inspection).
// maxDuration 120 задаётся в vercel.json.
import type { VercelRequest, VercelResponse } from '@vercel/node'
import {
  adminClient, bucketFor, getUserFromRequest, REFUNDABLE_REASONS, workerUrl,
} from '../_lib/vision.js'

const WORKER_TIMEOUT_MS = 90_000

export default async function handler(req: VercelRequest, res: VercelResponse): Promise<void> {
  if (req.method !== 'POST') { res.status(405).json({ reason: 'method' }); return }
  const user = await getUserFromRequest(req)
  if (!user) { res.status(401).json({ reason: 'auth' }); return }
  const inspectionId: string = req.body?.inspectionId ?? ''
  if (!inspectionId) { res.status(422).json({ reason: 'no_inspection_id' }); return }

  const db = adminClient()
  const { data: ins } = await db.from('photo_inspections')
    .select('*').eq('id', inspectionId).eq('user_id', user.id).maybeSingle()
  if (!ins) { res.status(404).json({ reason: 'not_found' }); return }
  if (ins.status !== 'queued') { res.status(409).json({ reason: `status_${ins.status}` }); return }

  const { data: assets } = await db.from('photo_assets')
    .select('idx, storage_path, kind').eq('inspection_id', inspectionId).order('idx')
  if (!assets?.length || assets.some((a) => !a.storage_path.startsWith(`${user.id}/`))) {
    res.status(422).json({ reason: 'bad_paths' }); return
  }

  const bucket = bucketFor(ins.source_kind as 'photo' | 'master_pdf')
  const { data: signed, error: signError } = await db.storage.from(bucket)
    .createSignedUrls(assets.map((a) => a.storage_path), 600)
  if (signError || !signed) { res.status(500).json({ reason: 'sign_failed' }); return }

  await db.from('photo_inspections').update({
    status: 'running', heartbeat_at: new Date().toISOString(), attempts: ins.attempts + 1,
  }).eq('id', inspectionId)

  // досъёмка/ревизия: прежние факты приезжают в воркер ТЕЛОМ запроса из photo_facts.
  // Родитель ревизии — строка, у которой superseded_by указывает на нас.
  let priorFacts: unknown[] = []
  if (ins.revision > 1) {
    const { data: parent } = await db.from('photo_inspections')
      .select('id, revision').eq('superseded_by', inspectionId).maybeSingle()
    if (parent) {
      priorFacts = (await db.from('photo_facts')
        .select('slot_id, payload, source, confidence, asset_idx, bbox')
        .eq('inspection_id', parent.id).eq('revision', parent.revision)).data ?? []
    }
  }

  const finalize = (outcome: 'done' | 'failed', reason: string | null, payload?: unknown) =>
    db.rpc('finalize_photo_inspection', {
      p_inspection_id: inspectionId, p_outcome: outcome,
      p_reason: reason, p_payload: (payload ?? null) as never,
    })

  let workerResponse: Response
  try {
    workerResponse = await fetch(`${workerUrl()}/internal/inspect`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Worker-Secret': process.env.VISION_WORKER_SECRET ?? '',
      },
      body: JSON.stringify({
        inspection_id: inspectionId,
        product: ins.product_key,
        level: ins.packaging_level,
        markets: ins.markets,
        evaluated_at: ins.created_at,
        ruleset_sha256: ins.ruleset_sha256,
        kind: ins.source_kind,
        asset_urls: signed.map((s) => s.signedUrl),
        faces: ins.source_kind === 'photo' ? assets.map((a) => a.face_name ?? 'unknown') : null,
        prior_facts: priorFacts.length ? priorFacts : null,
        reuse_facts: ins.revision > 1,
      }),
      signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
    })
  } catch (err) {
    const reason = err instanceof Error && err.name === 'TimeoutError'
      ? 'worker_timeout' : 'worker_unreachable'
    await finalize('failed', reason)
    res.status(200).json({ status: 'failed', reason }); return
  }

  if (workerResponse.status === 409) {
    await finalize('failed', 'ruleset_drift')
    res.status(200).json({ status: 'failed', reason: 'ruleset_drift' }); return
  }
  if (!workerResponse.ok) {
    const body = await workerResponse.json().catch(() => ({ reason: 'worker_error' }))
    const reason = typeof body.reason === 'string' ? body.reason : 'worker_error'
    // отказ по данным (no_text_layer и т.п.) квоту НЕ возвращает — список закрыт в RPC
    await finalize('failed', reason)
    res.status(200).json({ status: 'failed', reason }); return
  }

  const result = await workerResponse.json()

  // кропы-доказательства: base64 от воркера → бакет evidence-crops под service_role
  const findings = (result.findings ?? []) as Array<Record<string, unknown>>
  for (let i = 0; i < findings.length; i += 1) {
    const b64 = findings[i].evidence_crop_b64 as string | undefined
    if (!b64) continue
    const path = `${user.id}/${inspectionId}/${i}.jpg`
    const { error: upErr } = await db.storage.from('evidence-crops')
      .upload(path, Buffer.from(b64, 'base64'), { contentType: 'image/jpeg' })
    if (!upErr) findings[i].evidence_crop_path = path
    delete findings[i].evidence_crop_b64
  }

  const { error: finErr } = await finalize('done', null, { ...result, findings })
  if (finErr) { res.status(500).json({ reason: finErr.message }); return }
  res.status(200).json({ status: 'done', inspectionId })
}
```

(Замечание к `priorFacts`: выборка фактов предыдущей ревизии делается по id родителя. Родитель находится запросом `photo_inspections.superseded_by = inspectionId` — поправить выборку: `select id from photo_inspections where superseded_by = inspectionId`, затем факты по этому id с его `revision`. Реализовать честно при написании, тест на это — интеграционный в Задаче 13.)

- [ ] **Step 5: `api/vision/checklist.ts` и `api/vision/rejudge.ts`**

`checklist.ts` — прокси к воркеру с кэшем 5 минут и резолвером профиля:

```ts
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { adminClient, workerUrl } from '../_lib/vision.js'

export default async function handler(req: VercelRequest, res: VercelResponse): Promise<void> {
  if (req.method !== 'GET') { res.status(405).json({ reason: 'method' }); return }
  const productId = String(req.query.product ?? '')
  const level = String(req.query.level ?? 'consumer')
  if (!productId) { res.status(422).json({ reason: 'no_product' }); return }
  const db = adminClient()
  const { data: profile } = await db.rpc('photo_profile_for_product', {
    p_product_id: productId,
  })
  if (!profile) { res.status(404).json({ reason: 'no_checklist' }); return }
  const upstream = await fetch(
    `${workerUrl()}/api/checklist?product=${encodeURIComponent(profile)}&level=${encodeURIComponent(level)}`,
    { signal: AbortSignal.timeout(15_000) },
  ).catch(() => null)
  if (!upstream?.ok) { res.status(502).json({ reason: 'worker_unavailable' }); return }
  const body = await upstream.json()
  res.setHeader('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=60')
  res.status(200).json({ profile, ...body })
}
```

`rejudge.ts` — правка факта → пересуд без сети к извлечению → новая ревизия:

```ts
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { adminClient, getUserFromRequest, workerUrl } from '../_lib/vision.js'

export default async function handler(req: VercelRequest, res: VercelResponse): Promise<void> {
  if (req.method !== 'POST') { res.status(405).json({ reason: 'method' }); return }
  const user = await getUserFromRequest(req)
  if (!user) { res.status(401).json({ reason: 'auth' }); return }
  const { inspectionId, overrides } = req.body ?? {}
  if (!inspectionId || !Array.isArray(overrides) || overrides.length === 0) {
    res.status(422).json({ reason: 'bad_body' }); return
  }
  const db = adminClient()
  const { data: ins } = await db.from('photo_inspections').select('*')
    .eq('id', inspectionId).eq('user_id', user.id).eq('status', 'done').maybeSingle()
  if (!ins) { res.status(404).json({ reason: 'not_found' }); return }

  // 1. Записать правки (источник «человек» — высший приоритет)
  const overrideRows = overrides.map((o: { slotId: string; payload: unknown; note?: string }) => ({
    inspection_id: inspectionId, slot_id: o.slotId, payload: o.payload,
    author_user_id: user.id, note: o.note ?? '',
  }))
  const { error: ovErr } = await db.from('photo_fact_overrides').insert(overrideRows)
  if (ovErr) { res.status(500).json({ reason: ovErr.message }); return }

  // 2. Факты последней ревизии из БАЗЫ (не из кэша контейнера)
  const { data: facts } = await db.from('photo_facts')
    .select('slot_id, payload, source, confidence, asset_idx, bbox')
    .eq('inspection_id', inspectionId).eq('revision', ins.revision)

  // 3. Пересуд: ноль сетевых вызовов к моделям, ноль строк в photo_model_calls
  const upstream = await fetch(`${workerUrl()}/internal/rejudge`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Worker-Secret': process.env.VISION_WORKER_SECRET ?? '',
    },
    body: JSON.stringify({
      checklist_key: { product: ins.product_key, level: ins.packaging_level, markets: ins.markets },
      facts: facts ?? [],
      overrides: overrides.map((o: { slotId: string; payload: unknown; note?: string }) => ({
        slot_id: o.slotId, payload: o.payload, note: o.note ?? '',
      })),
    }),
    signal: AbortSignal.timeout(15_000),
  }).catch(() => null)
  if (!upstream?.ok) { res.status(502).json({ reason: 'worker_unavailable' }); return }
  const verdict = await upstream.json()

  // 4. Новая ревизия одной транзакцией; старая не переписывается никогда
  const { data: newId, error } = await db.rpc('create_photo_revision', {
    p_parent_id: inspectionId,
    p_payload: verdict as never,
  })
  if (error) { res.status(500).json({ reason: error.message }); return }
  res.status(200).json({ inspectionId: newId })
}
```

- [ ] **Step 6: vercel.json**

```json
{
  "functions": {
    "api/vision/check.ts": { "maxDuration": 120 }
  },
  "rewrites": [{ "source": "/((?!api/).*)", "destination": "/index.html" }]
}
```

- [ ] **Step 7: Run + commit**

```bash
npm run typecheck    # api/ теперь в tsc -b (ссылка добавлена Task 2)
npm run test
npm run lint
git add api vercel.json
git commit -m "feat(api): граница vision — check/checklist/progress/ruleset/rejudge, maxDuration 120"
```

### Task 11: Слой данных фронта: регенерация типов, src/data/vision.ts, хуки

**Files:**
- Create: `src/data/vision.ts`, `src/data/vision.test.ts`, `src/lib/image.ts`, `src/lib/image.test.ts`
- Modify: `src/lib/database.types.ts` (регенерация), `src/data/hooks.ts`, `src/data/index.ts`

**Interfaces:**
- Consumes: Task 8–10 (таблицы, RPC, эндпоинты).
- Produces (единственная дверь фронта к фотоконтролю; компоненты ходят ТОЛЬКО через hooks.ts):

```ts
// src/data/vision.ts
export interface ChecklistCounters { checkable: number; partial: number; notCheckable: number; noGold: number }
export interface PackagingChecklist { profile: string; counters: ChecklistCounters; groups: ChecklistGroup[] }
export interface InspectionBundle {
  inspection: PhotoInspectionRow          // строка photo_inspections (типы из database.types)
  findings: PhotoFindingRow[]
  notCheckable: PhotoNotCheckableRow[]
  assets: PhotoAssetRow[]
}
export async function fetchPackagingChecklist(productId: string, level: PackagingLevel): Promise<PackagingChecklist | null>
export async function buildIdempotencyKey(files: ArrayBuffer[], level: string, markets: string[]): Promise<string>
export async function uploadAndRequestInspection(input: {
  productId: string; level: PackagingLevel; sourceKind: 'photo' | 'master_pdf'
  files: File[]; faces?: string[]
}): Promise<string>                        // upload в бакет + rpc request_photo_inspection → inspectionId
export async function startInspection(inspectionId: string): Promise<{ status: string; reason?: string }>
export async function fetchInspectionBundle(id: string): Promise<InspectionBundle | null>
export async function fetchInspectionEvents(id: string): Promise<PhotoInspectionEventRow[]>
export async function submitFactOverride(inspectionId: string, overrides: { slotId: string; payload: unknown; note?: string }[]): Promise<string>  // → id новой ревизии
export async function requestRetake(inspectionId: string, files: File[], faces: string[]): Promise<string>
export async function submitFindingAction(findingId: string, action: 'fixed' | 'accepted_with_reason' | 'escalated', reason?: string): Promise<void>
export function groupRetakeBySurface(findings: PhotoFindingRow[]): { surface: string; findings: PhotoFindingRow[] }[]
export function reportCounters(bundle: InspectionBundle): { violations: number; decided: number; checked: number; needsHuman: number }
export function isPreliminary(bundle: InspectionBundle): boolean   // fail/critical без signed_by
```

```ts
// src/lib/image.ts
export function targetSize(w: number, h: number, maxSide?: number): { w: number; h: number }  // maxSide default 2048
export async function prepareImageForUpload(file: File): Promise<Blob>
// HEIC/EXIF: createImageBitmap(file, { imageOrientation: 'from-image' }) → canvas → JPEG 0.85, длинная сторона ≤ 2048
```

- Хуки в `src/data/hooks.ts` (паттерн существующих: `useQuery`/`useMutation`):
  `usePackagingChecklist(productId, level)`, `useRequestPackagingInspection()`, `useInspectionBundle(id)` (с `refetchInterval: 1500`, пока `status in (queued, running)`), `useInspectionEvents(id, enabled)`, `useFactOverride()`, `useRetake()`, `useFindingAction()`.

- [ ] **Step 1: Регенерация типов после миграций**

```bash
supabase db reset --local
supabase gen types typescript --local > src/lib/database.types.ts
npm run typecheck
git add src/lib/database.types.ts && git commit -m "chore(types): регенерация после миграций фотоконтроля"
```

- [ ] **Step 2: Failing vitest на чистые функции**

`src/data/vision.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { buildIdempotencyKey, groupRetakeBySurface } from './vision'

describe('buildIdempotencyKey', () => {
  const a = new TextEncoder().encode('file-a').buffer as ArrayBuffer
  const b = new TextEncoder().encode('file-b').buffer as ArrayBuffer
  it('детерминирован и не зависит от порядка файлов', async () => {
    const k1 = await buildIdempotencyKey([a, b], 'consumer', ['UZ'])
    const k2 = await buildIdempotencyKey([b, a], 'consumer', ['UZ'])
    expect(k1).toBe(k2)
    expect(k1).toMatch(/^[0-9a-f]{64}$/)
  })
  it('меняется от уровня и рынков', async () => {
    const k1 = await buildIdempotencyKey([a], 'consumer', ['UZ'])
    const k2 = await buildIdempotencyKey([a], 'transport', ['UZ'])
    const k3 = await buildIdempotencyKey([a], 'consumer', ['UZ', 'EAEU'])
    expect(new Set([k1, k2, k3]).size).toBe(3)
  })
})

describe('groupRetakeBySurface', () => {
  it('группирует по surface и сортирует по числу пунктов', () => {
    const f = (surface: string) => ({ surface, status: 'unreadable' }) as never
    const groups = groupRetakeBySurface([f('back_panel'), f('side_panel'), f('back_panel')])
    expect(groups[0]).toMatchObject({ surface: 'back_panel' })
    expect(groups[0].findings).toHaveLength(2)
  })
})
```

`src/lib/image.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { targetSize } from './image'

describe('targetSize', () => {
  it('длинная сторона ужимается до 2048, пропорции сохраняются', () => {
    expect(targetSize(4096, 2048)).toEqual({ w: 2048, h: 1024 })
    expect(targetSize(1000, 3000)).toEqual({ w: 682, h: 2048 })
  })
  it('маленький кадр не растягивается', () => {
    expect(targetSize(800, 600)).toEqual({ w: 800, h: 600 })
  })
})
```

Run: `npm run test` → FAIL (модулей нет).

- [ ] **Step 3: Реализация vision.ts и image.ts**

Ключевые куски (`idempotency_key` = sha256 отсортированных sha256 файлов + level + markets — состав из плана §4; хеш набора правил добавляет сервер через `ruleset_versions.is_current` в RPC):

```ts
async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', data)
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
}

export async function buildIdempotencyKey(
  files: ArrayBuffer[], level: string, markets: string[],
): Promise<string> {
  const hashes = await Promise.all(files.map(sha256Hex))
  const material = [...hashes].sort().join('|') + `|${level}|${[...markets].sort().join(',')}`
  return sha256Hex(new TextEncoder().encode(material).buffer as ArrayBuffer)
}

export async function uploadAndRequestInspection(input: { /* см. Interfaces */ }): Promise<string> {
  const { data: auth } = await supabase.auth.getUser()
  if (!auth.user) throw new Error('not_authenticated')
  const uid = auth.user.id
  const folder = crypto.randomUUID()
  const bucket = input.sourceKind === 'master_pdf' ? 'packaging-artwork' : 'packaging-photos'
  const paths: string[] = []
  const buffers: ArrayBuffer[] = []
  for (let i = 0; i < input.files.length; i += 1) {
    const blob = input.sourceKind === 'photo'
      ? await prepareImageForUpload(input.files[i])   // HEIC→JPEG, EXIF, ≤2048px
      : input.files[i]
    const ext = input.sourceKind === 'master_pdf' ? 'pdf' : 'jpg'
    const path = `${uid}/${folder}/${i}.${ext}`
    const { error } = await supabase.storage.from(bucket).upload(path, blob)
    if (error) throw error
    paths.push(path)
    buffers.push(await blob.arrayBuffer())
  }
  const key = await buildIdempotencyKey(buffers, input.level, ['UZ'])
  const { data, error } = await supabase.rpc('request_photo_inspection', {
    p_product_id: input.productId, p_level: input.level, p_markets: ['UZ'],
    p_source_kind: input.sourceKind, p_asset_paths: paths, p_idempotency_key: key,
  })
  if (error) throw error
  return data as string
}

export async function startInspection(inspectionId: string) {
  const { data: session } = await supabase.auth.getSession()
  const jwt = session.session?.access_token
  if (!jwt) throw new Error('not_authenticated')
  const res = await fetch('/api/vision/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${jwt}` },
    body: JSON.stringify({ inspectionId }),
  })
  return res.json()
}
```

`fetchInspectionBundle` — четыре запроса через `supabase.from(...)` (RLS own-read, паттерн `real.ts`: `{ data, error }`, `if (error) throw error`). `groupRetakeBySurface`, `reportCounters`, `isPreliminary` — чистые функции над строками. `image.ts` — `targetSize` (чистая) + `prepareImageForUpload` (`createImageBitmap(file, { imageOrientation: 'from-image' })`, canvas, `toBlob('image/jpeg', 0.85)`).

- [ ] **Step 4: Хуки + экспорт через index.ts**

В `hooks.ts` — по существующему паттерну; пример:

```ts
export function useInspectionBundle(inspectionId: string | undefined) {
  return useQuery({
    queryKey: ['photo-inspection', inspectionId],
    queryFn: () => fetchInspectionBundle(inspectionId!),
    enabled: Boolean(inspectionId),
    refetchInterval: (query) => {
      const status = query.state.data?.inspection.status
      return status === 'queued' || status === 'running' ? 1500 : false
    },
  })
}
```

В `index.ts` — реэкспорт публичных функций и типов `vision.ts` (композиция как у остальных доменов; моки не нужны — раздел живёт только на реальных данных).

- [ ] **Step 5: Run + commit**

```bash
npm run test && npm run typecheck && npm run lint
git add src/data/vision.ts src/data/vision.test.ts src/data/hooks.ts src/data/index.ts \
        src/lib/image.ts src/lib/image.test.ts
git commit -m "feat(data): слой данных фотоконтроля — загрузка, запуск, поллинг, пересуд"
```

---

### Task 12: Фронт: CPackagingCheckPage — выбор товара, чек-лист «Что проверим», загрузка

**Files:**
- Create: `src/pages/c/checks/CPackagingCheckPage.tsx`, `src/pages/c/checks/CPackagingUpload.tsx`
- Modify: `src/App.tsx:33` (маршрут), `src/pages/c/shell/nav.ts:48` (снять `soon: true` у packaging), `src/pages/c/shell/CProfileMenu.tsx:89` (снять `soon`), `src/pages/c/CSearch.tsx` (новый проп `onPick`), `src/i18n/ru.ts` (секция `ru.packagingCheck`)

**Interfaces:**
- Consumes: Task 11 (хуки), `useContentRequest` (существующий, `hooks.ts:650`), `CSearch` (`src/pages/c/CSearch.tsx:16`).
- Produces: маршрут `/checks/packaging` — рабочая страница (заглушка `CCheckAnnouncePage` остаётся только для `documents`); `CSearch` получает `onPick?: (hit: SearchHit) => boolean` (true → навигации нет, выбор остаётся на странице).

- [ ] **Step 1: Секция i18n — плоские ключи (failing vitest)**

`src/i18n/ru.test.ts` (новый):

```ts
import { describe, expect, it } from 'vitest'

import { ru } from './ru'

describe('ru.packagingCheck', () => {
  it('обязательные ключи раздела на месте', () => {
    const required = [
      'title', 'pickProduct', 'pickLevel', 'levelConsumer', 'levelTransport',
      'whatWeCheck', 'counterCheckable', 'counterPartial', 'counterNotCheckable',
      'counterNoGold', 'noChecklistTitle', 'noChecklistText', 'notifyCta',
      'uploadPdfTitle', 'uploadPdfHint', 'uploadPhotoTitle', 'needFourFrames',
      'startCheck', 'uploading',
    ] as const
    for (const key of required) expect(ru.packagingCheck).toHaveProperty(key)
  })
})
```

Run: `npm run test` → FAIL (`packagingCheck` нет).

- [ ] **Step 2: Добавить секцию в `src/i18n/ru.ts`** (после `ru.checks`, плоскими ключами; функции-шаблоны — стрелки, как в `ru.requirement`):

```ts
  packagingCheck: {
    title: 'Проверка упаковки',
    pickProduct: 'Найдите свой товар — тем же поиском, что и в каталоге',
    pickLevel: 'Уровень упаковки',
    levelConsumer: 'Потребительская (пачка)',
    levelTransport: 'Транспортная (короб)',
    whatWeCheck: 'Что проверим',
    counterCheckable: 'проверим',
    counterPartial: 'частично',
    counterNotCheckable: 'не проверяется по фото',
    counterNoGold: 'без эталонного примера',
    noChecklistTitle: 'Чек-лист для этого товара ещё не собран',
    noChecklistText: 'Пока поддержаны: табачная продукция, молочная продукция, бытовая электроника. Отсутствие чек-листа не означает, что требований нет.',
    notifyCta: 'Сообщить, когда появится',
    notifyDone: 'Заявка принята — напишем, когда появится.',
    uploadPdfTitle: 'Макет в PDF, до 50 МБ',
    uploadPdfHint: 'Один файл от типографии. Если текст переведён в кривые — скажем об этом до запуска проверки.',
    uploadPhotoTitle: 'Фотографии упаковки',
    needFourFrames: 'Нужно минимум четыре кадра: по одному кадру мы не сможем утверждать, что каких-то сведений на упаковке нет.',
    shootingHints: 'Сценарий съёмки',
    startCheck: 'Проверить',
    uploading: 'Загружаем…',
    quotaExhausted: 'Квота проверок на этот месяц исчерпана.',
    notSubscriber: 'Проверка упаковки доступна по подписке.',
    frameLabel: (i: number) => `Кадр ${i + 1}`,
  },
```

Run: `npm run test` → PASS.

- [ ] **Step 3: `CSearch` — проп `onPick`**

В `src/pages/c/CSearch.tsx`: сигнатура `export function CSearch({ autoFocus, onPick }: { autoFocus?: boolean; onPick?: (hit: SearchHit) => boolean })`; в обработчике выбора подсказки — первым делом `if (onPick?.(hit)) return` (существующая навигация `navigate(...)` остаётся поведением по умолчанию). `CCatalogPage` не меняется.

- [ ] **Step 4: Страница**

`CPackagingCheckPage.tsx` — машина из четырёх состояний в одном компоненте (`useState<Step>`): `pick` → `checklist` → `upload` → (навигация на отчёт). Скелет:

```tsx
type Step = { name: 'pick' } | { name: 'checklist'; hit: SearchHit } | { name: 'upload'; hit: SearchHit }

export function CPackagingCheckPage() {
  const t = ru.packagingCheck
  const [level, setLevel] = useState<'consumer' | 'transport'>('consumer')
  const [step, setStep] = useState<Step>({ name: 'pick' })
  const productId = step.name === 'pick' ? undefined : step.hit.id
  const checklist = usePackagingChecklist(productId, level)   // null → профиля нет
  const request = useContentRequest()
  // ...
}
```

- `pick`: `<CSearch onPick={(hit) => { if (hit.kind !== 'product') return false; setStep({ name: 'checklist', hit }); return true }} />` + переключатель уровня (`t.levelConsumer` / `t.levelTransport`).
- `checklist`: если `checklist.data === null` — экран `t.noChecklistTitle`/`t.noChecklistText` + кнопка `t.notifyCta` → `request.mutate({ kind: 'missing_section', queryText: 'Проверка упаковки: ' + step.hit.title, productId })`; кнопка «Проверить» заблокирована, квота не тратится. Иначе — 4 счётчика (`counters`) + группы пунктов + кнопка «Загрузить макет или фото» → `upload`. Экран бесплатен (без гейта подписки).
- `upload` → `CPackagingUpload` (Step 5).

- [ ] **Step 5: `CPackagingUpload.tsx`**

Два таба: PDF (один файл `accept="application/pdf"`) и фото (`accept="image/*,.heic,.heif"`, `multiple`, `capture` на мобильном). Правила из плана §2: кнопка `t.startCheck` активна для PDF сразу при выбранном файле, для фото — только при `files.length >= 4` (рядом `t.needFourFrames`); сценарий съёмки — `shootingHints` из `checklist.data.hints` (воркер отдаёт `profile.photo_hints(level)`); каждому кадру — селект грани (`front_panel`/`back_panel`/`side_panel`/`top`/`bottom`, подписи из `ru.packagingCheck`), карта граней уезжает в `faces`. Сабмит:

```tsx
const inspectionId = await uploadAndRequestInspection({
  productId, level, sourceKind, files, faces })
void startInspection(inspectionId)          // не ждём: экран ожидания живёт поллингом
navigate(`/checks/packaging/${inspectionId}`)
```

Ошибки RPC мапятся на строки: `quota_exhausted` → `t.quotaExhausted`, `not_subscriber` → `t.notSubscriber` (+ ссылка на `/pricing`).

- [ ] **Step 6: Маршрут и навигация**

- `src/App.tsx`: строку 33 заменить на `{ path: '/checks/packaging', element: <CPackagingCheckPage /> },` и добавить `{ path: '/checks/packaging/:inspectionId', element: <CPackagingReportPage /> },` (компонент появится в Задаче 13 — до неё поставить временный экспорт из того же файла, рендерящий «ожидание», чтобы typecheck был зелёным в пределах задачи; в Задаче 13 он заменяется полноценным).
- `nav.ts:48`: `{ to: '/checks/packaging', label: ru.nav.packaging, icon: Camera },` (без `soon`); строка 49 (`documents`) не меняется.
- `CProfileMenu.tsx:89`: `<MenuNavLink to="/checks/packaging" icon={Camera} onGo={close}>` (убрать `soon`). Нижние табы `CMobileNav.tsx` НЕ трогать (мобильный вход — меню профиля, решение плана §4).

- [ ] **Step 7: Run + визуальная проверка + commit**

```bash
npm run test && npm run typecheck && npm run lint
npm run dev &
node scripts/shot.mjs /checks/packaging packaging-check
```

Expected: скриншоты без консольных ошибок; light/dark × 1440/375.

```bash
git add src/pages/c/checks src/pages/c/CSearch.tsx src/pages/c/shell/nav.ts \
        src/pages/c/shell/CProfileMenu.tsx src/App.tsx src/i18n/ru.ts src/i18n/ru.test.ts
git commit -m "feat(front): страница проверки упаковки — выбор товара, чек-лист, загрузка, снят soon"
```

---

### Task 13: Фронт: ожидание с живыми стадиями и отчёт /checks/packaging/:inspectionId

**Files:**
- Create: `src/pages/c/checks/CPackagingReportPage.tsx`, `src/pages/c/checks/CPackagingWaiting.tsx`, `src/pages/c/checks/report-utils.ts`, `src/pages/c/checks/report-utils.test.ts`
- Modify: `src/i18n/ru.ts` (ключи отчёта в `ru.packagingCheck`), `src/App.tsx` (замена временного компонента)

**Interfaces:**
- Consumes: Task 11 (`useInspectionBundle`, `useInspectionEvents`, `useFactOverride`, `useRetake`, `useFindingAction`, `reportCounters`, `groupRetakeBySurface`, `isPreliminary`).
- Produces: постоянная ссылка отчёта; кнопки «Доснять» (revision+1, максимум 3) и «Поправить факт» (fact_override → rejudge → навигация на новую ревизию).

- [ ] **Step 1: Failing vitest на report-utils**

`src/pages/c/checks/report-utils.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { decidedByLabel, stageLabel, splitFindings } from './report-utils'

describe('splitFindings', () => {
  const f = (status: string, decided_by = 'pdf_text', suspected = false) =>
    ({ status, decided_by, suspected }) as never
  it('четыре списка §7: нарушения / досъёмка-человек / граница метода / без эталона', () => {
    const lists = splitFindings([f('fail'), f('pass'), f('unreadable')],
      [{ class: 'метод' }, { class: 'нет эталона' }] as never)
    expect(lists.violations).toHaveLength(1)
    expect(lists.needsHuman).toHaveLength(1)
    expect(lists.notCheckable).toHaveLength(1)
    expect(lists.noGold).toHaveLength(1)
  })
})

it('decided_by показывается словами, не кодом', () => {
  expect(decidedByLabel('pdf_text')).toBe('прочитано в макете')
  expect(decidedByLabel('zbar')).toBe('декодирован штрих-код')
  expect(decidedByLabel('ocr')).toBe('распознано OCR')
  expect(decidedByLabel('human')).toBe('подтверждено человеком')
})

it('стадии ожидания именованные', () => {
  expect(stageLabel('prepare', 'master_pdf')).toBe('разбираем макет')
  expect(stageLabel('read', 'photo')).toBe('читаем этикетку')
  expect(stageLabel('judge', 'photo')).toBe('сверяем с требованиями')
})
```

Run: `npm run test` → FAIL.

- [ ] **Step 2: `report-utils.ts`** — чистые функции + строки в `ru.packagingCheck`:

Дописать в `ru.packagingCheck`: `reportViolations: 'Нарушения'`, `reportNeedsHuman: 'Требует досъёмки или человека'`, `reportNotCheckable: 'По фотографии не проверяется — это граница метода, а не пробел'`, `reportNoGold: 'Правило есть, эталонного примера нет — вердикт не выносим'`, `retakeCta: 'Доснять'`, `fixFactCta: 'Поправить факт'`, `escalateCta: 'Эскалировать юристу'`, `acceptCta: 'Принять с обоснованием'`, `fixedCta: 'Исправлю'`, `preliminaryBadge: 'Предварительный — ждёт подписи юриста'`, `staleBadge: (date: string) => `Проверка устарела: норма изменилась ${date}` `, `auditTitle: 'Реквизиты проверки'`, `sourcePdf: 'макет PDF'`, `sourcePhoto: 'фотографии'`, `missingFace: (face: string, n: number) => `не хватает: ${face} — ${n} пунктов` `, стадии (`stageReceived`/`stagePrepare`/`stagePrepareArtwork`/`stageRead`/`stageJudge`/`stageRender`), словарь `decided_by` (`decidedPdf: 'прочитано в макете'`, `decidedZbar: 'декодирован штрих-код'`, `decidedOcr: 'распознано OCR'`, `decidedYolo: 'найдено детектором'`, `decidedGeometry: 'измерено по макету'`, `decidedHuman: 'подтверждено человеком'`), названия граней (`faceFront: 'лицевая'`, `faceBack: 'оборотная'`, `faceSide: 'торец'`, `faceTop: 'верх'`, `faceBottom: 'низ'`).

`splitFindings(findings, notCheckable)`: `violations` = `status === 'fail'`; `needsHuman` = `status === 'unreadable'` (включая `suspected` — «подозрения» VLM); `notCheckable` = строки `photo_not_checkable` c `class !== 'нет эталона'`; `noGold` = `class === 'нет эталона'`. `decidedByLabel`/`stageLabel` — словари поверх i18n.

- [ ] **Step 3: `CPackagingWaiting.tsx`** — используется отчётной страницей, пока `status in (queued, running)`: список пройденных стадий из `useInspectionEvents` (поллинг живёт в `useInspectionBundle`/`useInspectionEvents`), подписи `stageLabel(stage, sourceKind)`; миниатюры кадров — локальные превью из `sessionStorage` не тащим: показываем `photo_assets` (idx, face_name) списком. `failed` → текст причины (`last_error`) + для возвратных причин «квота возвращена, повторите»; `ruleset_drift`/`worker_timeout` и прочие — из словаря `ru.packagingCheck`.

- [ ] **Step 4: `CPackagingReportPage.tsx`** — план §7 дословно:

- Вверху 4 числа (`reportCounters`): «Нарушений: N», «Проверено пунктов: d из c», «Требует человека: k», «Источник: макет PDF (M страниц) | фотографии (покрытие: X граней из Y)» (`reader_coverage`). Процентной оценки НЕТ.
- Бейджи: `isPreliminary(bundle)` → `preliminaryBadge`; `inspection.stale_since` → `staleBadge(date)`; `inspection.superseded_by` → ссылка «есть новая ревизия».
- Четыре списка в порядке §7. Каждая находка: `message`, тяжесть, доказательство (`evidence_crop_path` → signed URL через `supabase.storage.from('evidence-crops').createSignedUrl` в слое данных; цитата из `evidence[].text` с кадром/страницей), `rule_ref` всегда; ссылка на карточку `/product/:productId?req=<requirement_id>` — только при ненулевом `requirement_id` (отсутствие ссылки показывается как отсутствие); `decidedByLabel` словами; три кнопки действий (`useFindingAction`): `fixedCta` / `acceptCta` (обязательный textarea ≥ 10 символов) / `escalateCta`.
- Список 2 агрегирован по граням: `groupRetakeBySurface` + `missingFace(faceLabel, n)`; кнопки «Доснять» («файл-инпут → `useRetake` → `startInspection(newId)` → навигация на новую ревизию»; при `revision >= 3` кнопка заблокирована с текстом «четвёртая досъёмка — новая проверка») и «Поправить факт» (модалка: слоты из `photo_facts` последней ревизии без `__*`-строк, инпут значения, `useFactOverride` → навигация на новую ревизию).
- Внизу «Реквизиты проверки» из `photo_inspections`: `evaluated_at`, `checked_at`, `ruleset_version` + `ruleset_sha256`, `policy_applied` (раскрывающийся `<details>`), `reader_coverage`, версии моделей, sha256 файлов (из `photo_assets`), `cost_usd`, `degraded_mode`, `signed_by`. Строка про редакцию нормы — дословно из плана §3: «Редакция акта на эту дату в реестре InspectorX не зафиксирована».

- [ ] **Step 5: Run + скриншоты + commit**

```bash
npm run test && npm run typecheck && npm run lint
node scripts/shot.mjs /checks/packaging packaging-report-empty
git add src/pages/c/checks src/i18n/ru.ts src/App.tsx
git commit -m "feat(front): ожидание с живыми стадиями и отчёт с четырьмя списками §7"
```

- [ ] **Step 6: Сквозная локальная проверка (Docker-воркер + локальный Supabase + vercel dev)** — выполняется при наличии `vercel` CLI; иначе переносится в «Приёмку Волны 1» без блокировки задачи:

```bash
docker run --rm -p 8010:8010 -e IXV_WORKER_SECRET=dev-secret ixvision:wave1 &
VISION_WORKER_URL=http://localhost:8010 VISION_WORKER_SECRET=dev-secret \
  SUPABASE_URL=$(supabase status -o json | jq -r .API_URL) \
  SUPABASE_SERVICE_ROLE_KEY=$(supabase status -o json | jq -r .SERVICE_ROLE_KEY) \
  npx vercel dev --listen 3000 &
# в браузере: /checks/packaging → выбрать табак → загрузить data/fixtures/mackets из vision → отчёт
```

---

### Task 14: Этап 5: очередь юриста по находкам, заключения, подпись

**Files:**
- Create: `supabase/migrations/20260810120000_photo_review_queue.sql`, `importer/tests/db/test_photo_reviews.py`
- Modify: `src/data/vision.ts` + `src/data/hooks.ts` (хуки юриста), `src/pages/c/CLawyerQueuePage.tsx` (секция фото-находок), `src/pages/c/checks/CPackagingReportPage.tsx` (кнопка подписи для юриста, показ заключений), `src/i18n/ru.ts`

**Interfaces:**
- Consumes: Task 8 (таблицы `photo_finding_actions`, `photo_finding_reviews`, RPC `record_finding_action`, `sign_photo_inspection`), Task 13 (отчёт).
- Produces: вью `public.photo_finding_queue` (только для verified-юристов); хуки `usePhotoReviewQueue()`, `useSubmitPhotoFindingReview()`, `useSignInspection()`; в отчёте — опубликованные заключения юриста при находке.

- [ ] **Step 1: Failing db-тест**

`importer/tests/db/test_photo_reviews.py` (маркеры как в Task 8; фикстуры `subscriber`, `service`, `current_ruleset`, `tobacco_product_id`):

```python
def _finished_inspection_with_finding(client, uid, service, product_id,
                                      requirement_id=None, key="rev-1"):
    """Хелпер живёт в conftest.py — его же переиспользует test_photo_lifecycle."""
    ins_id = client.rpc("request_photo_inspection", {
        "p_product_id": product_id, "p_level": "consumer", "p_markets": ["UZ"],
        "p_source_kind": "master_pdf",
        "p_asset_paths": [f"{uid}/{key}/0.pdf"], "p_idempotency_key": key}).execute().data
    service.rpc("finalize_photo_inspection", {
        "p_inspection_id": ins_id, "p_outcome": "done",
        "p_payload": {"overall": "fail", "decided": 1, "checked": 10,
                      "findings": [{"checkpoint_id": "uz.warning.text",
                                    "rule_ref": "tobacco.uz.warning",
                                    "requirement_id": requirement_id,
                                    "group_key": "warnings", "kind": "text_semantic",
                                    "severity": "critical", "status": "fail",
                                    "decided_by": "pdf_text",
                                    "confidence_class": "machine_read",
                                    "message": "нет предупреждения"}],
                      "not_checkable": [], "facts": [], "model_calls": [], "assets": []}}
    ).execute()
    fid = service.table("photo_findings").select("id").eq(
        "inspection_id", ins_id).execute().data[0]["id"]
    return ins_id, fid


def test_escalation_puts_finding_into_lawyer_queue(subscriber, service,
                                                   current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    client.rpc("record_finding_action",
               {"p_finding_id": fid, "p_action": "escalated"}).execute()
    rows = service.table("photo_finding_queue").select("*").execute().data
    assert any(r["finding_id"] == fid for r in rows)   # service видит без предиката юриста


def test_accept_requires_reason(subscriber, service, current_ruleset, tobacco_product_id):
    client, uid = subscriber
    _, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    import pytest as _pytest
    with _pytest.raises(Exception):
        client.rpc("record_finding_action",
                   {"p_finding_id": fid, "p_action": "accepted_with_reason"}).execute()


def test_sign_requires_verified_lawyer(subscriber, service, current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id, _ = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    import pytest as _pytest
    with _pytest.raises(Exception, match="not_a_verified_lawyer"):
        client.rpc("sign_photo_inspection", {"p_inspection_id": ins_id}).execute()
```

Run: `.venv-importer/bin/python -m pytest importer/tests/db/test_photo_reviews.py -q -m integration` → FAIL (`photo_finding_queue` не существует).

- [ ] **Step 2: Миграция `20260810120000_photo_review_queue.sql`**

```sql
-- Очередь юриста по находкам фотоконтроля — по образцу /lawyer/queue (ADR-0001,
-- поправка 5). security_invoker = off + предикат is_verified_lawyer() внутри:
-- клиенту-не-юристу вью отдаёт ноль строк, service_role видит всё.
create view public.photo_finding_queue
with (security_invoker = off) as
select f.id as finding_id,
       f.inspection_id,
       f.checkpoint_id,
       f.rule_ref,
       f.severity,
       f.status,
       f.message,
       i.product_key,
       i.packaging_level,
       a.created_at as escalated_at
from public.photo_findings f
join public.photo_inspections i on i.id = f.inspection_id
join public.photo_finding_actions a
  on a.finding_id = f.id and a.action = 'escalated'
where (public.is_verified_lawyer() or (select auth.uid()) is null)
  and not exists (
    select 1 from public.photo_finding_reviews r
    where r.finding_id = f.id and r.status = 'published');

grant select on public.photo_finding_queue to anon, authenticated;
```

- [ ] **Step 3: Накат + тесты**

```bash
supabase db reset --local
supabase gen types typescript --local > src/lib/database.types.ts
.venv-importer/bin/python -m pytest importer/tests/db -q -m integration
```

Expected: PASS.

- [ ] **Step 4: Фронт юриста**

- `vision.ts`: `fetchPhotoReviewQueue()` (select из `photo_finding_queue`), `submitPhotoFindingReview(findingId, verdict, commentText)` (insert в `photo_finding_reviews` — политика «verified lawyer insert», статус всегда default `pending`), `signInspection(inspectionId)` (rpc), `fetchFindingReviews(findingIds)` (published для отчёта).
- `hooks.ts`: `usePhotoReviewQueue(enabled)`, `useSubmitPhotoFindingReview()`, `useSignInspection()`, `useFindingReviews(findingIds)`.
- `CLawyerQueuePage.tsx`: вторая секция «Находки фотоконтроля» под существующей очередью требований — список из `usePhotoReviewQueue(verified)`, форма заключения (вердикт из enum `review_verdict` + текст ≥ 20 символов — те же правила, что у требований).
- `CPackagingReportPage.tsx`: если `useMyLawyerProfile().status === 'verified'` и вердикт с критичной находкой не подписан — кнопка «Подписать» (`useSignInspection`); опубликованные заключения юриста — под находкой (имя юриста из `lawyer_profiles` — публичное чтение verified уже есть).
- i18n: `lawyerPhotoQueueTitle: 'Находки фотоконтроля'`, `signCta: 'Подписать вердикт'`, `signedBy: (name: string, date: string) => `Подписано: ${name}, ${date}` `.

- [ ] **Step 5: Run + commit**

```bash
npm run test && npm run typecheck && npm run lint
git add supabase/migrations/20260810120000_photo_review_queue.sql importer/tests/db/test_photo_reviews.py \
        src/data src/pages/c src/i18n/ru.ts src/lib/database.types.ts
git commit -m "feat(reviews): очередь юриста по находкам, заключения и подпись вердикта"
```

---

### Task 15: Этап 6 (код без LLM): правила как данные — requirement_photo*, выгрузка YAML→БД, photo_checklist(), паритет, габариты

**Files:**
- vision — Create: `scripts/export_checks.py`, `scripts/bench_sql_parity.py`, `tests/test_export_checks.py`; Modify: `src/ixvision/cli.py` (команда `export`), `docs/DB_EXTENSION.sql` (пометка «черновик заменён миграцией витрины»)
- витрина — Create: `supabase/migrations/20260810130000_requirement_photo.sql`, `scripts/generate_photo_checks_migration.mjs`, `supabase/migrations/20260810140000_photo_checks_content.sql` (генерируется скриптом), `importer/tests/db/test_photo_checklist.py`

**Interfaces:**
- Consumes: Task 1 (YAML-пакеты + линтер), Task 3 (paths), Task 8 (photo_profiles, конфтест).
- Produces:
  - vision: `python -m ixvision export --out runs/checks_export.json` — JSON `{"ruleset_sha256": str, "schema": <PhotoCheckSpec.model_json_schema()>, "requirements": [{"rule_ref": "<pack>.<req_id>", "pack", "title_ru", "checkability": "checkable|partial|not_checkable", "packaging_level", "why", "markets": [...], "applicability": {"scope": "hs_prefix|all_products", "hs_prefixes": [...]}, "source": {"act_id", "clause", "quote_ru"}, "checks": [{"id", "kind", "severity", "group", "subject", "level", "target", "question_ru", "measure", "params", "hint_ru", "title_ru"}]}]}`;
  - витрина: таблицы `public.requirement_photo`, `public.requirement_photo_checks`, `public.requirement_photo_check_contents` (адаптация `docs/DB_EXTENSION.sql`: тавтологичный CHECK заменён constraint-триггером; `requirement_id` НУЛЕВОЙ с FK — заполняется мостом; канонический ключ `rule_ref` уникален; `params` валидируется `pg_jsonschema`); функция `public.photo_checklist(p_product_id uuid, p_level text, p_markets text[]) returns setof requirement_photo_checks` — объединение legacy-scope (hs_prefix/all_products из выгрузки) и `catalog.product_types` через `products.product_type_id`; таблица `public.photo_product_dimensions` (габариты SKU, RLS own read/write);
  - паритет: `scripts/bench_sql_parity.py --rows <json> --product tobacco --level consumer` — компилирует YAML-чек-лист и сверяет с SQL-строками цифра в цифру (множество `rule_ref`+`check id`, `kind`, `severity`, `params`); судья — чистая функция чек-листа и паспорта, поэтому равенство скомпилированных чек-листов ⇒ равенство бенчмарка.

- [ ] **Step 1: Failing test экспорта (vision)**

`tests/test_export_checks.py`:

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import export_checks


def test_export_covers_all_packs_and_checks(tmp_path):
    out = tmp_path / "checks.json"
    export_checks.main(["--out", str(out)])
    doc = json.loads(out.read_text())
    assert doc["ruleset_sha256"] and len(doc["ruleset_sha256"]) == 64
    assert doc["schema"]["title"] == "PhotoCheckSpec"
    reqs = doc["requirements"]
    assert len(reqs) == 204                    # все требования шести пакетов
    checks = [c for r in reqs for c in r["checks"]]
    assert len(checks) == 364                  # все машинные проверки
    assert all(r["rule_ref"].count(".") >= 1 for r in reqs)
    kinds = {c["kind"] for c in checks}
    assert kinds == {"presence", "text_semantic", "absence", "geometry"}
```

(Числа 204/364 — фиксация фактического состояния пакетов; если после чистки stage1 они сместились — снять фактические `python -c "...load_all_packs..."` и вписать точные, это константы приёмки.)

Run: `./ix test tests/test_export_checks.py -v` → FAIL.

- [ ] **Step 2: `scripts/export_checks.py` + команда CLI**

Скрипт обходит `load_all_packs()` (структуры `RequirementPack` → требования → `PhotoCheckSpec`), собирает JSON по контракту Interfaces, добавляет `ruleset.fingerprint()["sha256"]` и `PhotoCheckSpec.model_json_schema()`. Мост uuid: если существует `config/bridge/requirement_ids.csv` (колонки `rule_ref,requirement_id` — заполняет юрист, Волна 3 Б4), в строки требований добавляется `"requirement_id"`; файла нет → поле опущено (не выдумывается). В `cli.py` — сабкоманда `export` с `--out`.

Run: `./ix test tests/test_export_checks.py -v` → PASS. Commit:

```bash
git add scripts/export_checks.py src/ixvision/cli.py tests/test_export_checks.py
git commit -m "feat(export): односторонняя выгрузка YAML-пакетов в JSON для базы витрины"
```

- [ ] **Step 3: Миграция схемы (витрина) — failing db-тест**

`importer/tests/db/test_photo_checklist.py`:

```python
from __future__ import annotations

import pytest

from .conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


def test_photo_checklist_returns_rows_for_tobacco(service, tobacco_product_id):
    rows = service.rpc("photo_checklist", {
        "p_product_id": tobacco_product_id, "p_level": "consumer",
        "p_markets": ["UZ", "EAEU"]}).execute().data
    assert len(rows) >= 70            # у табака consumer ~79 пунктов (план §2А шаг 1)
    kinds = {r["kind"] for r in rows}
    assert kinds <= {"presence", "text_semantic", "absence", "geometry"}


def test_checkable_requirement_must_have_checks(service):
    """Починка тавтологичного CHECK из DB_EXTENSION.sql: checkable без единой
    проверки не проходит constraint-триггер."""
    with pytest.raises(Exception, match="checkable_needs_checks"):
        service.table("requirement_photo").insert({
            "rule_ref": "test.orphan", "title_ru": "сирота",
            "checkability": "checkable", "packaging_level": "consumer",
            "why": "тест"}).execute()


def test_params_json_schema_constraint(service):
    with pytest.raises(Exception):
        service.table("requirement_photo_checks").insert({
            "rule_ref": "test.orphan", "check_id": "bad", "kind": "geometry",
            "severity": "major", "group_key": "geometry", "subject": "x",
            "packaging_level": "both", "measure": "min_size_mm",
            "params": {"surface": "NOT_A_FACE"}}).execute()
```

`supabase/migrations/20260810130000_requirement_photo.sql` — ключевые решения (полный SQL пишется по ним):

```sql
-- Правила как данные (этап 6, код): адаптация docs/DB_EXTENSION.sql.
-- Отличия от черновика — названы, а не молчат:
--  1) requirement_id СТАЛ nullable: канонический ключ — rule_ref (пакет.требование),
--     uuid приезжает мостом requirement_ids.csv и честно отсутствует, пока моста нет;
--  2) тавтологичный CHECK (checkability <> 'checkable' or true) заменён
--     constraint-триггером requirement_photo_checkable_needs_checks (deferrable);
--  3) unique(requirement_id, kind, subject, measure) с NULL-ловушкой заменён на
--     unique (rule_ref, check_id);
--  4) params проверяется pg_jsonschema-схемой, сгенерированной из PhotoCheckSpec
--     (surface/language/min_mm и словари линтера params — теперь констрейнт).
-- ПРОД: расширение pg_jsonschema включается в Dashboard до мёржа (гейт А6 Волны 3).
create extension if not exists pg_jsonschema;

create type public.photo_check_kind as enum ('presence', 'text_semantic', 'absence', 'geometry');
create type public.photo_checkability as enum ('checkable', 'partial', 'not_checkable');
create type public.photo_severity as enum ('critical', 'major', 'minor', 'info');
create type public.photo_packaging_level as enum ('consumer', 'transport', 'both');

create table public.requirement_photo (
  rule_ref        text primary key,
  requirement_id  uuid references public.requirements(id) on delete set null,
  pack            text not null default '',
  title_ru        text not null default '',
  checkability    public.photo_checkability not null,
  packaging_level public.photo_packaging_level not null default 'consumer',
  why             text not null,
  markets         text[] not null default '{UZ}',
  scope           text not null default 'hs_prefix' check (scope in ('hs_prefix', 'all_products')),
  hs_prefixes     text[] not null default '{}',
  source          jsonb not null default '{}'::jsonb,
  ruleset_sha256  text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create table public.requirement_photo_checks (
  id              uuid primary key default gen_random_uuid(),
  rule_ref        text not null references public.requirement_photo(rule_ref) on delete cascade,
  check_id        text not null,
  ord             int not null default 0,
  kind            public.photo_check_kind not null,
  severity        public.photo_severity not null default 'major',
  group_key       text not null,
  subject         text not null default '',
  packaging_level public.photo_packaging_level not null default 'both',
  target          text,
  question_ru     text,
  measure         text,
  params          jsonb not null default '{}'::jsonb,
  hint_ru         text,
  title_ru        text,
  unique (rule_ref, check_id),
  constraint photo_check_target_for_presence
    check (kind <> 'presence' or target is not null),
  constraint photo_check_question_for_text
    check (kind not in ('text_semantic', 'absence') or question_ru is not null),
  constraint photo_check_measure_for_geometry
    check (kind <> 'geometry' or measure is not null),
  constraint photo_check_params_valid check (extensions.jsonb_matches_schema(
    '{"type":"object","properties":{
       "surface":{"enum":["front_panel","back_panel","side_panel","top_panel","bottom_panel","top","bottom","any_panel","all_panels","any"]},
       "language":{"type":"array","items":{"enum":["ru","uz","uz-cyrl","uz-latn","en","kk","hy","ky"]}},
       "min_mm":{"type":"number","exclusiveMinimum":0}
     }}'::json, params))
);

-- contents: язык-строки (ru сейчас, uz/en позже) — по образцу requirement_contents
create table public.requirement_photo_check_contents (
  check_id uuid not null references public.requirement_photo_checks(id) on delete cascade,
  lang     text not null check (lang in ('ru', 'uz', 'en')),
  question text,
  hint     text,
  title    text,
  primary key (check_id, lang)
);

-- «checkable ⇒ есть хотя бы одна проверка» — то, что CHECK одной таблицы не выразит
create or replace function public.requirement_photo_checkable_guard()
returns trigger language plpgsql as $$
begin
  if new.checkability = 'checkable' and not exists (
      select 1 from public.requirement_photo_checks c where c.rule_ref = new.rule_ref) then
    raise exception 'checkable_needs_checks: % объявлен checkable без единой проверки', new.rule_ref;
  end if;
  return new;
end;
$$;
create constraint trigger requirement_photo_checkable_needs_checks
  after insert or update on public.requirement_photo
  deferrable initially deferred
  for each row execute function public.requirement_photo_checkable_guard();

-- RLS: чтение всем (это каталог правил, не пользовательские данные), запись — service_role
alter table public.requirement_photo enable row level security;
alter table public.requirement_photo_checks enable row level security;
alter table public.requirement_photo_check_contents enable row level security;
create policy "public read" on public.requirement_photo for select to anon, authenticated using (true);
create policy "public read" on public.requirement_photo_checks for select to anon, authenticated using (true);
create policy "public read" on public.requirement_photo_check_contents for select to anon, authenticated using (true);
revoke insert, update, delete on public.requirement_photo,
  public.requirement_photo_checks, public.requirement_photo_check_contents
  from anon, authenticated;

-- Чек-лист из SQL: объединение legacy-scope и product_type (тест-инвариант этапа 6)
create or replace function public.photo_checklist(
  p_product_id uuid, p_level text, p_markets text[] default '{UZ}')
returns table (rule_ref text, check_id text, kind public.photo_check_kind,
               severity public.photo_severity, group_key text, subject text,
               target text, question_ru text, measure text, params jsonb,
               hint_ru text, title_ru text, requirement_id uuid)
language sql stable
as $$
  select c.rule_ref, c.check_id, c.kind, c.severity, c.group_key, c.subject,
         c.target, c.question_ru, c.measure, c.params, c.hint_ru,
         coalesce(c.title_ru, rp.title_ru), rp.requirement_id
  from public.requirement_photo_checks c
  join public.requirement_photo rp on rp.rule_ref = c.rule_ref
  join public.products p on p.id = p_product_id
  where rp.markets && p_markets
    and (c.packaging_level = 'both' or c.packaging_level::text = p_level)
    and (rp.packaging_level = 'both' or rp.packaging_level::text = p_level
         or rp.checkability <> 'not_checkable')
    and (rp.scope = 'all_products'
         or exists (select 1 from unnest(rp.hs_prefixes) pref
                    where p.hs_code like pref || '%')
         or exists (select 1 from catalog.product_types pt
                    where pt.id = p.product_type_id
                      and exists (select 1 from unnest(rp.hs_prefixes) pref
                                  where pt.hs6 like pref || '%')))
  order by c.group_key, c.severity, c.ord;
$$;
grant execute on function public.photo_checklist(uuid, text, text[]) to anon, authenticated;

-- Габариты упаковки: вводит пользователь один раз на свой SKU (развилка 4, этап 6)
create table public.photo_product_dimensions (
  user_id         uuid not null references auth.users(id) on delete cascade,
  product_id      uuid not null references public.products(id) on delete cascade,
  packaging_level text not null check (packaging_level in ('consumer', 'transport')),
  width_mm        numeric(7,1) not null check (width_mm > 0),
  height_mm       numeric(7,1) not null check (height_mm > 0),
  depth_mm        numeric(7,1) check (depth_mm > 0),
  updated_at      timestamptz not null default now(),
  primary key (user_id, product_id, packaging_level)
);
alter table public.photo_product_dimensions enable row level security;
create policy "own all" on public.photo_product_dimensions
  for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
```

(Точное имя колонки HS6 в `catalog.product_types` сверить по миграции каталога — `grep -n "hs6\|hs_code" supabase/migrations/*product_catalog*.sql supabase/migrations/*catalog*.sql`; подправить в функции.)

- [ ] **Step 4: Генератор контент-миграции и накат**

`scripts/generate_photo_checks_migration.mjs` (по образцу `scripts/generate_services_seed.mjs`): читает `runs/checks_export.json` (путь аргументом), печатает SQL: `delete from requirement_photo_checks; delete from requirement_photo;` не пишет — только `insert ... on conflict (rule_ref) do update` для requirement_photo и `on conflict (rule_ref, check_id) do update` для checks (выгрузка ОДНОсторонняя и идемпотентная; правки руками в базе запрещены и перетираются). Строки со спецсимволами — через dollar-quoting `$txt$...$txt$`.

```bash
cd /Users/abduraxmonturdiyev/inspectorx-vision && ./.venv/bin/python -m ixvision export --out runs/checks_export.json
cd /Users/abduraxmonturdiyev/inspector-x-final
node scripts/generate_photo_checks_migration.mjs \
  /Users/abduraxmonturdiyev/inspectorx-vision/runs/checks_export.json \
  > supabase/migrations/20260810140000_photo_checks_content.sql
supabase db reset --local
.venv-importer/bin/python -m pytest importer/tests/db/test_photo_checklist.py -q -m integration
```

Expected: PASS (включая падение checkable-без-проверок и params-схемы).

- [ ] **Step 5: Паритет SQL против YAML (vision)**

`scripts/bench_sql_parity.py`: вход `--rows <json>` (дамп `photo_checklist()`), `--product`, `--level`; компилирует YAML-чек-лист (`compile_by_id`), приводит обе стороны к множеству кортежей `(rule_ref, check_id, kind, severity, canonical_json(params))` и печатает диф; выход 0 только при пустом дифе. Дамп из локальной базы:

```bash
cd /Users/abduraxmonturdiyev/inspector-x-final
for combo in "tobacco consumer" "dairy consumer" "electronics consumer" "tobacco transport"; do :; done
supabase db query "select to_jsonb(array_agg(t)) from public.photo_checklist(
  (select id from products where hs_code like '2402%' limit 1), 'consumer', '{UZ,EAEU}') t" \
  --local -o json > /tmp/sql_checklist_tobacco_consumer.json
cd /Users/abduraxmonturdiyev/inspectorx-vision
./.venv/bin/python scripts/bench_sql_parity.py --rows /tmp/sql_checklist_tobacco_consumer.json \
  --product tobacco --level consumer
```

Expected: `exit 0`, вывод `паритет: N пунктов, диф пуст` — та же цифра, что даёт компилятор YAML. Расхождение хоть на один пункт — дефект выгрузки или функции, чинится до коммита. Судья (`rule_engine.evaluate`) — детерминированная функция чек-листа и паспорта, поэтому равенство чек-листов означает равенство `./ix bench` цифра в цифру.

- [ ] **Step 6: Габариты в прогоне фотопути**

- `api/vision/check.ts`: перед вызовом воркера — `select * from photo_product_dimensions where user_id/product_id/packaging_level` → `reference_dimensions_mm: {width_mm, height_mm}` в теле `InspectRequest` (поле уже в контракте Task 7);
- воркер `internal_inspect`: `profile = profile.model_copy(update={"reference_dimensions_mm": req.reference_dimensions_mm})` при наличии — `min_size_mm` на фотопути оживает (движок уже умеет `reference_dimensions_mm`);
- фронт: в `CPackagingUpload` для фотопути — два необязательных поля «ширина/высота упаковки, мм» (`useUpsertDimensions` — insert через RLS own all), подпись: без них `min_size_mm` уходит в «не проверяется: не знаем габариты вашей упаковки».

- [ ] **Step 7: Commit (оба репозитория)**

```bash
cd /Users/abduraxmonturdiyev/inspectorx-vision
git add scripts/bench_sql_parity.py && git commit -m "feat(export): паритет SQL-чек-листа против YAML цифра в цифру"
cd /Users/abduraxmonturdiyev/inspector-x-final
git add supabase/migrations/20260810130000_requirement_photo.sql \
        supabase/migrations/20260810140000_photo_checks_content.sql \
        scripts/generate_photo_checks_migration.mjs importer/tests/db/test_photo_checklist.py \
        api/vision/check.ts src/pages/c/checks src/data src/lib/database.types.ts
git commit -m "feat(rules): requirement_photo* с починенным CHECK, выгрузка YAML→БД, photo_checklist(), габариты SKU"
```

---

### Task 16: Этап 7 (код): устаревание вердиктов и уведомления checklist_version

**Files:**
- Create: `supabase/migrations/20260810150000_photo_lifecycle.sql`, `importer/tests/db/test_photo_lifecycle.py`
- Modify: `src/pages/c/shell/CNotificationCenter.tsx` (рендер `kind='checklist_version'`), `src/i18n/ru.ts`

**Interfaces:**
- Consumes: Task 8 (`photo_findings.requirement_id`, `photo_inspections.stale_since`), существующие `change_events` (c `effective_date`), `requirement_change_impacts`, `user_notifications` (kind `'checklist_version'` зарезервирован в `20260803180000_calendar_notifications.sql:50`).
- Produces: `public.flag_stale_photo_inspections() returns int` + pg_cron `photo-stale-flag` (`15 3 * * *`); уведомление пользователю; ни один вердикт не изменён (только `stale_since`).

- [ ] **Step 1: Failing db-тест**

`importer/tests/db/test_photo_lifecycle.py` (фикстуры Task 8; хелпер `_finished_inspection_with_finding` из Task 14 вынести в `conftest.py` при реализации Task 14 и переиспользовать здесь; в finalize-payload находки проставить `requirement_id` реального published-требования):

```python
def test_change_event_marks_exactly_affected_verdicts(subscriber, service,
                                                      current_ruleset, tobacco_product_id):
    client, uid = subscriber
    req_id = service.table("requirements").select("id").eq(
        "status", "published").limit(1).execute().data[0]["id"]
    ins_id, fid = _finished_inspection_with_finding(
        client, uid, service, tobacco_product_id, requirement_id=req_id)
    other_id, _ = _finished_inspection_with_finding(
        client, uid, service, tobacco_product_id, requirement_id=None, key="other")

    ev = service.table("change_events").insert({
        "event_type": "amended", "title": "тестовое изменение",
        "effective_date": "2026-08-01"}).execute().data[0]
    service.table("requirement_change_impacts").insert({
        "change_event_id": ev["id"], "requirement_id": req_id,
        "status": "confirmed"}).execute()

    service.rpc("flag_stale_photo_inspections", {}).execute()

    row = service.table("photo_inspections").select("stale_since").eq(
        "id", ins_id).execute().data[0]
    assert row["stale_since"] == "2026-08-01"
    other = service.table("photo_inspections").select("stale_since").eq(
        "id", other_id).execute().data[0]
    assert other["stale_since"] is None        # не затронутые не тронуты

    notes = service.table("user_notifications").select("*").eq(
        "user_id", uid).eq("kind", "checklist_version").execute().data
    assert len(notes) == 1
    # повторный прогон идемпотентен
    service.rpc("flag_stale_photo_inspections", {}).execute()
    notes = service.table("user_notifications").select("*").eq(
        "user_id", uid).eq("kind", "checklist_version").execute().data
    assert len(notes) == 1
    # вердикт не изменён: findings нетронуты
    f = service.table("photo_findings").select("status").eq("id", fid).execute().data[0]
    assert f["status"] == "fail"
```

Run → FAIL (функции нет).

- [ ] **Step 2: Миграция**

`supabase/migrations/20260810150000_photo_lifecycle.sql`:

```sql
-- Устаревание вердиктов при изменении нормы (план §2 шаг 7; этап 7, код).
-- До полного этапа 6 requirement_id заполнен у малой доли находок (мост) —
-- механизм честно покрывает только их; функция не продаётся до этапа 6 (риск 13).
create unique index if not exists user_notifications_checklist_version_uidx
  on public.user_notifications (user_id, requirement_id, ((payload ->> 'inspection')))
  where kind = 'checklist_version';

create or replace function public.flag_stale_photo_inspections()
returns int
language plpgsql security definer set search_path = public
as $$
declare
  n int;
begin
  with affected as (
    select distinct i.id as inspection_id, i.user_id, f.requirement_id,
           ce.effective_date
    from public.photo_findings f
    join public.photo_inspections i on i.id = f.inspection_id and i.status = 'done'
    join public.requirement_change_impacts imp
      on imp.requirement_id = f.requirement_id
     and imp.status in ('pending_review', 'confirmed')
    join public.change_events ce on ce.id = imp.change_event_id
    where f.requirement_id is not null
      and ce.effective_date is not null
      and i.stale_since is null
  ),
  marked as (
    update public.photo_inspections i
       set stale_since = a.effective_date
      from affected a
     where i.id = a.inspection_id
    returning i.id, i.user_id
  )
  insert into public.user_notifications (user_id, requirement_id, kind, payload)
  select a.user_id, a.requirement_id, 'checklist_version',
         jsonb_build_object('inspection', a.inspection_id::text,
                            'effective_date', a.effective_date)
  from affected a
  on conflict (user_id, requirement_id, ((payload ->> 'inspection')))
    where kind = 'checklist_version'
  do nothing;

  get diagnostics n = row_count;
  return n;
end;
$$;
revoke all on function public.flag_stale_photo_inspections() from public;
revoke all on function public.flag_stale_photo_inspections() from anon, authenticated;
grant execute on function public.flag_stale_photo_inspections() to service_role;

do $$
begin
  if not exists (select 1 from cron.job where jobname = 'photo-stale-flag') then
    perform cron.schedule('photo-stale-flag', '15 3 * * *',
      $cron$select public.flag_stale_photo_inspections()$cron$);
  end if;
end;
$$;
```

(Если `change_events.event_type` enum не содержит `'amended'` — взять первое реальное значение enum `change_event_type` из `20260711120000_initial_schema.sql`, поправить тест.)

- [ ] **Step 3: Накат + тест + колокольчик**

```bash
supabase db reset --local
.venv-importer/bin/python -m pytest importer/tests/db/test_photo_lifecycle.py -q -m integration
```

`CNotificationCenter.tsx`: ветка рендера `kind === 'checklist_version'` → текст `ru.packagingCheck.staleNotification(date)` (добавить ключ: `staleNotification: (date: string) => `Ваша проверка упаковки больше не актуальна: норма изменилась ${date}` `) со ссылкой на `/checks/packaging/<inspection>` из `payload.inspection`.

- [ ] **Step 4: Run + commit**

```bash
npm run test && npm run typecheck && npm run lint
.venv-importer/bin/python -m pytest importer/tests -q
git add supabase/migrations/20260810150000_photo_lifecycle.sql importer/tests/db/test_photo_lifecycle.py \
        src/pages/c/shell/CNotificationCenter.tsx src/i18n/ru.ts
git commit -m "feat(lifecycle): stale_since по изменению нормы и уведомление checklist_version"
```

## Приёмка Волны 1

Исполняемые проверки по мотивам приёмок этапов 2, 3, 5, 6 нормативного плана (§10). Все — локальные; пункты, требующие секретов/деплоя, помечены «(Волна 3)». Порядок важен: сначала vision, затем витрина, затем сквозные.

**1. Движок и гейты честности (vision):**

```bash
cd /Users/abduraxmonturdiyev/inspectorx-vision
./ix test
# Ожидание: 0 failed; ≥ 430 passed (399 main + ≥ 15 stage1 + новые задач 3–7, 15);
# skipped — только опциональные движки (easyocr/paddle/zbar).
./ix bench --assert missed_as_pass=0 --assert unsupported_decision=0 --assert false_pass=0
# Ожидание: exit 0. Это гейты §8 (метрики 1 и 2) — строго нули, не пороги.
./.venv/bin/python scripts/lint_params.py
# Ожидание: exit 0 (ratchet: ни одного нового нарушения params).
python3 -c "import json; t=json.load(open('runs/benchmark.json'))['totals']; \
  print('decisiveness master_pdf:', t['decisiveness_by_source_kind']['master_pdf']['decisiveness'])"
# Ожидание: не ниже 0.25 (baseline main после сшивки). Приёмка «≥ 70 % по текстовым
# пунктам на 5 демо-макетах» (этап 2) закрывается ПОСЛЕ разметки Б5 Волны 3.
```

**2. Пакетирование и запрет молчаливой деградации (vision):**

```bash
docker build -t ixvision:wave1 .
docker run --rm ixvision:wave1 python -c "from ixvision.vision.preprocess import warmup; warmup(); print('weights ok')"
# Ожидание: weights ok (веса в образе).
docker run --rm -e IXV_WEIGHTS=/nonexistent ixvision:wave1 \
  python -c "from ixvision.vision.preprocess import warmup; warmup()"; echo "exit=$?"
# Ожидание: exit != 0, в stderr — текст про IXV_ALLOW_NO_DETECTOR=1.
git lfs ls-files | grep best.pt
# Ожидание: models/best.pt под lfs.
```

**3. Контракт воркера (vision, без сети к моделям):**

```bash
./ix test tests/test_internal_api.py tests/test_ruleset.py -v
# Ожидание: PASS — inspect на эталонном макете, 409 при ruleset_drift,
# rejudge без единого сетевого вызова, 401 без X-Worker-Secret.
```

**4. Миграции, RLS, квота, репер, ретеншн (витрина, локальный Supabase):**

```bash
cd /Users/abduraxmonturdiyev/inspector-x-final
supabase db start && supabase db reset --local
supabase db lint                     # ожидание: без ошибок
.venv-importer/bin/python -m pytest importer/tests/db -q -m integration
# Ожидание: PASS все photo-тесты, в том числе:
#  - резерв квоты атомарен и идемпотентен (test_request_reserves_quota_and_is_idempotent);
#  - возврат ТОЛЬКО по закрытому списку причин, потолок 3 (test_refund_only_for_closed_reason_list_and_capped);
#  - «убитый» прогон: running без пульса → failed/worker_timeout с возвратом резерва
#    (test_reaper_kills_stale_running_with_refund — локальный эквивалент приёмки
#    этапа 2 «убийство контейнера на 20-й секунде»);
#  - чужой префикс бакета запечатан (test_foreign_prefix_is_sealed — риск 8);
#  - эскалация → очередь юриста; подпись только verified-юристом (test_photo_reviews);
#  - устаревание метит ровно затронутые вердикты и идемпотентно (test_photo_lifecycle).
.venv-importer/bin/python -m pytest importer/tests -q     # весь набор, ожидание: 0 failed
npm run lint && npm run typecheck && npm run test          # ожидание: 0 failed
```

**5. Ретеншн с подкрученной датой (приёмка этапа 2, локально):**

```bash
API_URL=$(supabase status -o json | jq -r .API_URL)
SRK=$(supabase status -o json | jq -r .SERVICE_ROLE_KEY)
supabase db query "select vault.create_secret('$API_URL','supabase_project_url','t'); \
  select vault.create_secret('$SRK','supabase_service_role_key','t');" --local
# создать проверку с файлом (любой интеграционный тест выше уже оставил строки), затем:
supabase db query "update public.photo_inspections set created_at = now() - interval '31 days';" --local
supabase db query "select public.purge_expired_photo_assets();" --local
supabase db query "select count(*) as unpurged from public.photo_assets \
  where purged_at is null and inspection_id in \
  (select id from public.photo_inspections where created_at < now() - interval '30 days');" --local
# Ожидание: unpurged = 0 — инвариант «нет photo_assets без purged_at старше 31 дня».
```

**6. Пересуд бесплатен и append-only (приёмка этапа 5):**

```bash
# Через сквозной локальный стенд (Task 13 Step 6) либо прямым вызовом:
# 1) снять count(*) из photo_model_calls; 2) POST /api/vision/rejudge с override;
# 3) убедиться: появилась НОВАЯ строка photo_inspections (revision+1, старая не изменена,
#    у старой заполнился superseded_by), photo_model_calls count НЕ вырос (ноль строк —
#    «не стоит ни цента»), photo_fact_overrides содержит правку с author_user_id.
supabase db query "select revision, status, superseded_by is not null as superseded \
  from public.photo_inspections order by created_at;" --local
```

**7. Паритет SQL-чек-листа против YAML (приёмка этапа 6, «цифра в цифру»):**

```bash
# по Task 15 Step 5 для трёх профилей × уровни:
./.venv/bin/python scripts/bench_sql_parity.py --rows /tmp/sql_checklist_tobacco_consumer.json --product tobacco --level consumer
./.venv/bin/python scripts/bench_sql_parity.py --rows /tmp/sql_checklist_dairy_consumer.json --product dairy --level consumer
./.venv/bin/python scripts/bench_sql_parity.py --rows /tmp/sql_checklist_electronics_consumer.json --product electronics --level consumer
# Ожидание: exit 0 у всех, диф пуст. Расхождение хоть на один пункт = потеря при переезде.
```

**8. Сквозной путь глазами (локальный стенд):** Task 13 Step 6 — загрузка эталонного макета через браузер до отчёта: стадии сменяются (строки в `photo_inspection_events`), отчёт открывается по постоянной ссылке, 4 числа сверху, 4 списка §7, `decided_by` словами, реквизиты внизу, «ни одного вердикта, сохранённого наполовину» (finalize — одна транзакция: `select status, decided is not null as has_verdict from photo_inspections` — нет строк `done` без findings).

**9. CI обоих репозиториев:** vision — локально зелёный `ruff check src tests scripts && python -m pytest tests -q && python scripts/lint_params.py` (репозиторий без remote — GitHub Actions появится вместе с remote, Волна 3); витрина — `gh run list --branch photocontrol-wave1 --limit 1` зелёный.

**10. Мёрж в main витрины** — только после: зелёных пунктов 1–9, включённых в Dashboard прода `pg_cron` и `pg_jsonschema` (гейт А6 Волны 3), заведённых Vault-секретов ретеншна (SQL из шапки миграции Task 8 Step 3, исполняет владелец) и явной команды владельца. Затем: `git checkout main && git merge --no-ff photocontrol-wave1 && git push origin main` — миграции уедут на прод автоматически, отката нет. Env-переменные Vercel (`VISION_WORKER_URL`, `VISION_WORKER_SECRET`) и деплой воркера на Railway — Волна 3 (А2–А4); до них прод-фронт показывает раздел, но запуск проверки отвечает 500 на `/api/vision/check` — поэтому мёрж в main разумно совмещать с закрытием А2–А4.

---

## Что осознанно НЕ в этом плане (границы Волны 1)

- **Живые VLM-вызовы, промпты, переспрос `vlm_reask`, калибровка** — Волна 2 (включается по приходу ключей; `photo_model_calls` и `degraded_mode='local'` уже готовы её принять).
- **Azure Document Intelligence** — Волна 3 (В1, due-diligence); self-host чтец (EasyOCR/PaddleOCR) уже стоит и является дефолтом.
- **Секреты, токены, Railway-аккаунт, env Vercel, включение расширений в Dashboard, мост requirement_ids.csv (юрист), фото-эталоны и разметка демо-макетов** — Волна 3 (задачи А1–А6, Б2–Б5).
- **Возвращение шага `rule` как генератора PR-кандидатов** (этап 6) — требует LLM, Волна 2+.
- **Sentry и события воронки** — по ADR-0002 решение 7 ставится «до анонса»; это задача Д3 Волны 3 (15 минут с DSN от владельца), в кодовую Волну 1 не входит.
- **uz-локализация отчёта и экспорт PDF** — этап 7 плана, после запуска беты.

## Самопроверка плана (выполнена при написании)

- **Spec coverage:** все 12 пунктов скоупа Волны 1 покрыты задачами: мёржи → 1–2; пакетирование → 3; эндпоинты → 6–7; миграции рантайма/storage → 8–9; Vercel → 10; фронт → 11–13; фотопуть → 4; self-host OCR → 5 (уже существующий EasyOCR-чтец переиспользован, добавлены PaddleOCR-бэкенд, привратник, язык); этап 5 → 7 (кропы), 8 (таблицы/RPC), 10 (rejudge), 13 (кнопки), 14 (очередь/подпись); этап 6 → 15; этап 7 → 16; CI-гейты — в Global Constraints и приёмке.
- **Верификация построенного:** план сверен с фактическим кодом на 06.08.2026 — правило двух ключей, макетный путь, растеризация, EasyOCR, переписанный бенчмарк и `decided_by` УЖЕ в main vision и повторно не строятся (раздел «Что уже построено»).
- **Отступления от нормативного плана — названы:** unique по `(user_id, idempotency_key)` вместо глобального; `source='system'` в `photo_facts` для служебных строк паспорта; insert-политика юриста на `photo_finding_reviews` (калька ADR-0001 против пункта «пишет только service_role» §4); `requirement_photo.requirement_id` nullable + канонический `rule_ref` (черновик DB_EXTENSION чинится, а не копируется).




