"""Coverage checker + автопубликация (Задача 27, ADR-0003 «Блок 2», финал).

Сценарии из брифа Задачи 27:
- `coverage_report`: карта vs факт — 4 категории (closed/no_norm/
  needs_attention/pending), markdown в `.markdown`, расхождение карты и
  факта (число айтемов) отмечается отдельно;
- `coverage_report(..., manager=...)`: для КАЖДОГО needs_attention-пробела
  спрашивает менеджера, кладёт совет в `CoverageGap.manager_suggestion` и в
  markdown — коуверidge ничего не перезапускает и не публикует сама;
- `publish_ready`: публикует ТОЛЬКО `draft_loaded`-айтемы, у которых ВСЕ
  сохранённые вердикты `passed=True` (пустой список вердиктов — вакуально
  «все pass»); хотя бы один непройденный вердикт — требование остаётся
  `draft`, айтем эскалируется в `needs_attention`; airtems других статусов
  (`published`/`no_norm`/`needs_attention`/`pending`) не трогаются;
  дедуп-дубль (`draft_loaded` без `requirement_id`) — публикуется как айтем
  (терминальная отметка), но `publish_requirement` не вызывается (нечего
  публиковать).

`InMemoryStore` — тот же единый тестовый дублёр, что и в
`test_orchestrator.py`/`test_cartographer.py`/`test_steps_load.py`.
"""
from __future__ import annotations

from importer.build.agents import Verdict
from importer.build.coverage import coverage_report, publish_ready
from importer.tests.build.stores import InMemoryStore

# ── тестовые хелперы ──────────────────────────────────────────────────────


def _seed_run(store: InMemoryStore, *, group_ref="2203", jurisdiction="UZ", payload=None, item_count=None):
    if payload is None:
        n = item_count if item_count is not None else 4
        payload = [{"expected_item": f"требование {i}"} for i in range(n)]
    map_id = store.save_map(group_ref, jurisdiction, payload)
    store.set_map_status(map_id, "approved", approved_by="owner")
    run_id = store.create_run(map_id)
    items = store.create_items(run_id, payload)
    return map_id, run_id, items


def _minimal_card(title: str = "Заголовок") -> dict:
    return {
        "requirement": {
            "status": "draft", "jurisdiction": "UZ", "category_slug": "marking",
            "deontic": "obligation", "addressee_roles": ["importer"],
            "authority_name": None, "operation": "product", "origin": "ai_pipeline",
            "effective_from": None, "transition_until": None, "valid_to": None,
            "repealed_by_ref": None,
        },
        "contents": {"ru": {"title": title, "sanction_summary": "штраф", "translation_origin": None}},
        "details": {"ru": {
            "description": None, "how_to_comply": [], "documents": [], "sanctions": [],
            "court_cases": None, "templates": None, "lawyer_instruction": None,
            "status_note": None, "translation_origin": None,
        }},
        "applicability": {"scope": "all_products", "product_type_id": None},
        "rules": [],
        "citations": [],
    }


# ══════════════════════════════════════════════════════════════════════════
# coverage_report: 4 категории
# ══════════════════════════════════════════════════════════════════════════


def test_coverage_report_classifies_all_four_categories():
    store = InMemoryStore()
    map_id, run_id, items = _seed_run(store, item_count=5)
    published_item, draft_loaded_item, no_norm_item, needs_attention_item, pending_item = items

    store.update_item_status(published_item.id, "published")
    store.update_item_status(draft_loaded_item.id, "draft_loaded")
    store.update_item_status(no_norm_item.id, "no_norm")
    store.update_item_status(needs_attention_item.id, "needs_attention", last_error="verifier failed")
    # pending_item остаётся как есть (create_items — дефолт 'pending')

    report = coverage_report(store, run_id)

    assert report.run_id == run_id
    assert report.map_id == map_id
    assert report.total_expected == 5
    assert report.total_actual == 5
    assert report.closed == 2  # published + draft_loaded
    assert report.no_norm == 1
    assert report.needs_attention == 1
    assert report.pending == 1
    assert len(report.gaps) == 1
    assert report.gaps[0].item_id == needs_attention_item.id
    assert report.gaps[0].last_error == "verifier failed"


def test_coverage_report_markdown_contains_table_and_gap():
    store = InMemoryStore()
    map_id, run_id, items = _seed_run(
        store, payload=[{"expected_item": "проблемное требование про маркировку"}]
    )
    item = items[0]
    store.update_item_status(item.id, "needs_attention", last_error="норма не найдена")

    report = coverage_report(store, run_id)

    assert f"Coverage-отчёт по прогону {run_id}" in report.markdown
    assert "needs_attention" in report.markdown
    assert "проблемное требование про маркировку" in report.markdown
    assert "норма не найдена" in report.markdown


def test_coverage_report_flags_map_vs_actual_item_count_mismatch():
    store = InMemoryStore()
    payload = [{"expected_item": "айтем A"}, {"expected_item": "айтем B"}]
    map_id = store.save_map("2203", "UZ", payload)
    store.set_map_status(map_id, "approved", approved_by="owner")
    run_id = store.create_run(map_id)
    store.create_items(run_id, payload[:1])  # только 1 из 2 — имитация обрыва прогона

    report = coverage_report(store, run_id)

    assert report.total_expected == 2
    assert report.total_actual == 1
    assert "Расхождение" in report.markdown


def test_coverage_report_empty_run_has_zero_everywhere():
    store = InMemoryStore()
    map_id = store.save_map("2203", "UZ", [])
    store.set_map_status(map_id, "approved", approved_by="owner")
    run_id = store.create_run(map_id)
    store.create_items(run_id, [])

    report = coverage_report(store, run_id)

    assert report.total_expected == 0
    assert report.total_actual == 0
    assert report.closed == report.no_norm == report.needs_attention == report.pending == 0
    assert report.gaps == []


# ══════════════════════════════════════════════════════════════════════════
# coverage_report: менеджер исключений советует по пробелам
# ══════════════════════════════════════════════════════════════════════════


class _RecordingManager:
    def __init__(self, decision: dict):
        self._decision = decision
        self.calls: list[tuple[str, list[str]]] = []

    def review(self, item, history):
        self.calls.append((item.id, list(history)))
        return self._decision


def test_coverage_report_asks_manager_for_each_needs_attention_gap():
    store = InMemoryStore()
    map_id, run_id, items = _seed_run(
        store, payload=[
            {"expected_item": "проблемный айтем 1"},
            {"expected_item": "проблемный айтем 2"},
            {"expected_item": "чистый айтем"},
        ],
    )
    bad1, bad2, clean = items
    store.update_item_status(bad1.id, "needs_attention", last_error="norm not found")
    store.update_item_status(bad2.id, "needs_attention", last_error="verifier failed")
    store.update_item_status(clean.id, "published")

    manager = _RecordingManager({"action": "retry_reformulated", "note": "попробуй ещё раз"})
    report = coverage_report(store, run_id, manager=manager)

    # менеджер спрошен РОВНО по needs_attention-пробелам, не по closed-айтему
    assert {call[0] for call in manager.calls} == {bad1.id, bad2.id}
    assert len(manager.calls) == 2
    for gap in report.gaps:
        assert gap.manager_suggestion == {"action": "retry_reformulated", "note": "попробуй ещё раз"}
    assert "retry_reformulated" in report.markdown


def test_coverage_report_without_manager_leaves_suggestion_none():
    store = InMemoryStore()
    map_id, run_id, items = _seed_run(store, payload=[{"expected_item": "проблемный айтем"}])
    store.update_item_status(items[0].id, "needs_attention", last_error="x")

    report = coverage_report(store, run_id)  # manager не передан

    assert report.gaps[0].manager_suggestion is None


# ══════════════════════════════════════════════════════════════════════════
# publish_ready: публикует только чистые draft_loaded-айтемы
# ══════════════════════════════════════════════════════════════════════════


def test_publish_ready_blocks_item_with_no_verdicts_at_all():
    """План фотоконтроля §3 («вакуальный pass»): `all(...)` над ПУСТЫМ словарём
    вердиктов — True, и айтем без единой верификации публиковался как готовый.
    Айтем без вердиктов — это непроверенный айтем: needs_attention, не витрина."""
    store = InMemoryStore()
    map_id, run_id, items = _seed_run(store, payload=[{"expected_item": "непроверенный айтем"}])
    item = items[0]
    requirement_id = store.save_requirement_draft(_minimal_card(), item_id=item.id)
    store.update_item_status(item.id, "draft_loaded", requirement_id=requirement_id)

    count = publish_ready(store, run_id)

    assert count == 0
    assert store.requirements[requirement_id]["status"] == "draft"
    assert store.items[item.id].status == "needs_attention"
    assert "нет ни одного вердикта" in store.items[item.id].last_error


def test_publish_ready_publishes_item_with_all_passing_verdicts():
    store = InMemoryStore()
    map_id, run_id, items = _seed_run(store, payload=[{"expected_item": "проверенный айтем"}])
    item = items[0]
    requirement_id = store.save_requirement_draft(_minimal_card(), item_id=item.id)
    store.update_item_status(item.id, "draft_loaded", requirement_id=requirement_id)
    store.save_verdicts(item.id, "norm", [Verdict(passed=True, reason="ок", model="gpt-5")])
    store.save_verdicts(item.id, "category", [Verdict(passed=True, reason="ок", model="gpt-5-mini")])

    count = publish_ready(store, run_id)

    assert count == 1
    assert store.requirements[requirement_id]["status"] == "published"
    assert store.items[item.id].status == "published"


def test_publish_ready_publishes_item_whose_step_failed_then_passed_on_retry():
    """Фикс-раунд ревью Задачи 27 (Important №1): «нерешённый fail» — это
    ПОСЛЕДНИЙ по времени вердикт ДАННОГО ШАГА, не любой исторический.
    Обычный, штатный путь `Orchestrator._run_from` — шаг провалился первой
    попыткой (verdict fail), прошёл ретраем (verdict pass) — этот АЙТЕМ
    ОБЯЗАН публиковаться: провалившийся вердикт первой попытки остаётся в
    `pipeline.verdicts` НАВСЕГДА (append-only), но он больше не «последний»
    для шага 'norm'."""
    store = InMemoryStore()
    map_id, run_id, items = _seed_run(store, payload=[{"expected_item": "починенный ретраем айтем"}])
    item = items[0]
    requirement_id = store.save_requirement_draft(_minimal_card(), item_id=item.id)
    store.update_item_status(item.id, "draft_loaded", requirement_id=requirement_id)
    store.save_verdicts(item.id, "norm", [Verdict(passed=False, reason="не подтвердил", model="gpt-5-high-reasoning")])
    store.save_verdicts(item.id, "norm", [Verdict(passed=True, reason="ок со второй попытки", model="gpt-5-high-reasoning")])

    count = publish_ready(store, run_id)

    assert count == 1
    assert store.requirements[requirement_id]["status"] == "published"
    assert store.items[item.id].status == "published"


def test_publish_ready_blocks_item_whose_last_verdict_of_some_step_is_fail():
    """Симметричный случай предыдущего теста: ПОСЛЕДНИЙ вердикт шага
    'category' — fail (даже если у другого шага 'norm' всё pass) — блок."""
    store = InMemoryStore()
    map_id, run_id, items = _seed_run(store, payload=[{"expected_item": "спорный айтем"}])
    item = items[0]
    requirement_id = store.save_requirement_draft(_minimal_card(), item_id=item.id)
    store.update_item_status(item.id, "draft_loaded", requirement_id=requirement_id)
    store.save_verdicts(item.id, "norm", [Verdict(passed=True, reason="ок", model="gpt-5-high-reasoning")])
    store.save_verdicts(item.id, "category", [Verdict(passed=True, reason="первая попытка ок", model="gpt-5")])
    store.save_verdicts(item.id, "category", [Verdict(passed=False, reason="повторная проверка не прошла", model="gpt-5")])

    count = publish_ready(store, run_id)

    assert count == 0
    assert store.requirements[requirement_id]["status"] == "draft"
    assert store.items[item.id].status == "needs_attention"
    assert "последний вердикт" in store.items[item.id].last_error


def test_publish_ready_only_touches_draft_loaded_items():
    store = InMemoryStore()
    map_id, run_id, items = _seed_run(store, item_count=4)
    published_item, no_norm_item, needs_attention_item, pending_item = items
    store.update_item_status(published_item.id, "published")
    store.update_item_status(no_norm_item.id, "no_norm")
    store.update_item_status(needs_attention_item.id, "needs_attention", last_error="x")
    # pending_item остаётся 'pending'

    count = publish_ready(store, run_id)

    assert count == 0
    assert store.items[published_item.id].status == "published"
    assert store.items[no_norm_item.id].status == "no_norm"
    assert store.items[needs_attention_item.id].status == "needs_attention"
    assert store.items[pending_item.id].status == "pending"


def test_publish_ready_marks_dedup_duplicate_item_published_without_requirement():
    store = InMemoryStore()
    map_id, run_id, items = _seed_run(store, payload=[{"expected_item": "дубль"}])
    item = items[0]
    store.set_item_note(item.id, "duplicate_of=item-original")
    store.update_item_status(item.id, "draft_loaded")  # requirement_id остаётся None

    count = publish_ready(store, run_id)

    assert count == 1
    assert store.items[item.id].status == "published"
    assert store.requirements == {}  # ничего не публиковалось — публиковать нечего


def test_publish_ready_returns_zero_for_run_with_no_draft_loaded_items():
    store = InMemoryStore()
    map_id, run_id, items = _seed_run(store, payload=[{"expected_item": "ещё pending"}])

    count = publish_ready(store, run_id)

    assert count == 0
    assert store.items[items[0].id].status == "pending"
