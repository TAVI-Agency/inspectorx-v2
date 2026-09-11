"""Сравнение моделей на golden set (Задача 6, ночь 11.09.2026): `build
eval-models --set cheap=…,mid=…,expensive=…` (повторяемый флаг) прогоняет
`run_eval` (`eval_golden.py`) по каждому набору тиров и печатает markdown-
таблицу сравнения между наборами.

Почему выбор моделей делается по ДАННЫМ golden set, а не по прайсу
провайдера: `models.yaml: pricing` уже даёт стоимость запроса, но не даёт
качество — дешёвая модель, которая промахивается по retrieval или пропускает
verifier на подложном фрагменте, обходится дороже дорогой модели, если её
ошибки уходят в прод. `run_model_sets` поэтому просто гоняет ОДИН и тот же
`run_eval` по нескольким наборам тиров и оставляет решение человеку — эта
команда не выбирает «лучший» набор сама, только раскладывает метрики рядом.

LLM в тестах — только `monkeypatch` на `run_eval` (не живой вызов, не сеть,
тот же принцип, что и в `test_eval_golden.py`).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from importer.build.agents import ModelsConfig
from importer.build.eval_models import compare_table, parse_tier_set, run_model_sets, slug_for


def test_parse_tier_set_ok_and_missing():
    assert parse_tier_set("cheap=a,mid=b,expensive=c") == {"cheap": "a", "mid": "b", "expensive": "c"}
    with pytest.raises(ValueError, match="expensive"):
        parse_tier_set("cheap=a,mid=b")


def test_slug_for_sanitizes():
    assert slug_for({"cheap": "gemini/3.1", "mid": "b", "expensive": "c"}) == "cheap-gemini-3.1__mid-b__expensive-c"


def test_compare_table_has_rows_and_columns():
    md = compare_table({"s1": {"retrieval_hit_rate": 0.5, "category_accuracy": 0.9, "retrieval_errors": 1,
                               "verifier_errors": 0, "category_errors": 0, "lifecycle_errors": 0}})
    assert "| s1 |" in md and "0.50" in md and "0.90" in md and "| 1 |" in md


def test_run_model_sets_writes_report_per_set(tmp_path, monkeypatch):
    calls = []
    def fake_run_eval(items, **kw):
        calls.append(kw["models"].tiers)
        class R:
            def to_json_dict(self): return {"retrieval_hit_rate": 1.0, "backend": kw["backend"]}
            markdown = ""
        return R()
    monkeypatch.setattr("importer.build.eval_models.run_eval", fake_run_eval)
    base = ModelsConfig(tiers={"cheap": "x", "mid": "y", "expensive": "z"}, pricing={})
    out = run_model_sets([], sets=[{"cheap": "a", "mid": "b", "expensive": "c"}], base_config=base,
                         legalx=object(), llm=object(), valid_category_slugs=[], out_dir=tmp_path)
    assert list(out) == ["cheap-a__mid-b__expensive-c"]
    assert calls == [{"cheap": "a", "mid": "b", "expensive": "c"}]
    assert len(list(Path(tmp_path).glob("*-cheap-a__mid-b__expensive-c.json"))) == 1


def test_cli_eval_models_invalid_set_argument(monkeypatch, capsys):
    """Тест на красивую ошибку при неверном аргументе --set.

    `main(["build", "eval-models", "--set", "cheap=a,mid=b"])` (не хватает expensive)
    должен вывести читаемое сообщение об ошибке и выйти с кодом 1."""
    import importer.cli

    # Замонкипатчим ix_client и SupabaseBuildStore, чтобы не создавать реальный клиент
    def fake_ix():
        return object()

    class FakeStore:
        pass

    monkeypatch.setattr("importer.cli.ix_client", fake_ix)
    monkeypatch.setattr("importer.cli.SupabaseBuildStore", lambda x: FakeStore())

    with pytest.raises(SystemExit) as exc_info:
        importer.cli.main(["build", "eval-models", "--set", "cheap=a,mid=b"])

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out.startswith("ошибка:")
