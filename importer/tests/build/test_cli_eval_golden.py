"""CLI `build eval-golden`: baseline живого прогона не смешивается с
mock-baseline.

`run_eval` считает дельту против `baseline.json`, но числа mock-эвристики
(`HeuristicBaselineLLM` — только smoke-проверка проводки) и живых моделей
несопоставимы. Поэтому:

- `--llm live` читает и пишет ОТДЕЛЬНЫЙ файл `baseline-live.json` —
  `--save-baseline` живого прогона больше не затирает mock-baseline;
- если в прочитанном baseline поле `backend` не совпадает с текущим, дельта
  не считается (`baseline=None`) и печатается предупреждение.

LLM и Supabase в тестах не трогаются: `run_eval`, `ix_client`,
`SupabaseBuildStore`, `get_legalx_client` и `load_golden_set` —
monkeypatch'ы (тот же принцип, что и в `test_eval_models.py`).
"""
from __future__ import annotations

import json


class _FakeStore:
    def list_category_slugs(self):
        return []


class _FakeReport:
    markdown = ""

    def __init__(self, backend: str) -> None:
        self._backend = backend

    def to_json_dict(self) -> dict:
        return {"backend": self._backend, "retrieval_hit_rate": 1.0}


def _patch(monkeypatch) -> list[dict]:
    """Обвязка CLI -> дублёры; возвращает список kwargs каждого вызова run_eval."""
    import importer.cli

    calls: list[dict] = []

    def fake_run_eval(items, **kw):
        calls.append(kw)
        return _FakeReport(kw["backend"])

    monkeypatch.setattr("importer.cli.ix_client", lambda: object())
    monkeypatch.setattr("importer.cli.SupabaseBuildStore", lambda ix: _FakeStore())
    monkeypatch.setattr("importer.cli.get_legalx_client", lambda: object())
    monkeypatch.setattr("importer.cli.load_golden_set", lambda path: [])
    monkeypatch.setattr("importer.cli.run_eval", fake_run_eval)
    return calls


def _golden_dir(tmp_path):
    d = tmp_path / "importer" / "golden"
    d.mkdir(parents=True)
    return d


def test_live_save_baseline_writes_separate_file_and_keeps_mock_baseline(
    tmp_path, monkeypatch, capsys
):
    import importer.cli

    golden = _golden_dir(tmp_path)
    mock_baseline = {"backend": "mock", "retrieval_hit_rate": 0.23}
    (golden / "baseline.json").write_text(json.dumps(mock_baseline), encoding="utf-8")
    calls = _patch(monkeypatch)
    monkeypatch.chdir(tmp_path)

    importer.cli.main(["build", "eval-golden", "--llm", "live", "--save-baseline"])

    # mock-baseline не участвует в дельте живого прогона и не затёрт им
    assert calls[0]["baseline"] is None
    assert json.loads((golden / "baseline.json").read_text(encoding="utf-8")) == mock_baseline
    saved = json.loads((golden / "baseline-live.json").read_text(encoding="utf-8"))
    assert saved["backend"] == "live"
    assert "baseline-live.json" in capsys.readouterr().out


def test_baseline_from_other_backend_is_not_used_for_delta(tmp_path, monkeypatch, capsys):
    import importer.cli

    golden = _golden_dir(tmp_path)
    (golden / "baseline-live.json").write_text(
        json.dumps({"backend": "live:cheap-a__mid-b__expensive-c"}), encoding="utf-8")
    calls = _patch(monkeypatch)
    monkeypatch.chdir(tmp_path)

    importer.cli.main(["build", "eval-golden", "--llm", "live"])

    assert calls[0]["baseline"] is None
    assert "предупреждение" in capsys.readouterr().out


def test_mock_run_still_uses_mock_baseline(tmp_path, monkeypatch, capsys):
    import importer.cli

    golden = _golden_dir(tmp_path)
    baseline = {"backend": "mock", "retrieval_hit_rate": 0.23}
    (golden / "baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
    calls = _patch(monkeypatch)
    monkeypatch.chdir(tmp_path)

    importer.cli.main(["build", "eval-golden"])

    assert calls[0]["baseline"] == baseline
    assert calls[0]["backend"] == "mock"
