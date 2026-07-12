import json
from importer.models import ActRef
from importer.resolver import ensure_paragraph, resolve_act


class FakeTable:
    """Мини-фейк supabase table: select().eq()/ilike().limit().execute() и insert()."""
    def __init__(self, store, name):
        self.store, self.name, self._filters = store, name, []

    def select(self, *_): return self
    def limit(self, *_): return self

    def eq(self, col, val):
        self._filters.append(lambda r: r.get(col) == val); return self

    def ilike(self, col, pattern):
        needle = pattern.strip("%")
        self._filters.append(lambda r: needle in (r.get(col) or "")); return self

    def execute(self):
        rows = [r for r in self.store.get(self.name, [])
                if all(f(r) for f in self._filters)]
        self._filters = []
        return type("R", (), {"data": rows})()

    def insert(self, row):
        row = {"id": f"id-{len(self.store.get(self.name, []))}", **row}
        self.store.setdefault(self.name, []).append(row)
        store_row = row
        return type("Q", (), {"execute": lambda self_: type("R", (), {"data": [store_row]})()})()


class FakeClient:
    def __init__(self, store): self.store = store
    def table(self, name): return FakeTable(self.store, name)


ACT = ActRef(name="ЗРУ-819", number="819", date="2023-04-05",
             lexuz_url="https://lex.uz/docs/-6445145")


def test_resolve_act_not_in_jb_queues_and_inserts(tmp_path):
    jb, ix = FakeClient({"acts": []}), FakeClient({"acts": []})
    q = tmp_path / "act_queue.jsonl"
    row = resolve_act(ACT, "6445145", jb, ix, q)
    assert row["id"].startswith("id-")
    assert ix.store["acts"][0]["url"] == "https://lex.uz/ru/docs/-6445145"
    queued = [json.loads(l) for l in q.read_text().splitlines()]
    assert queued[0]["doc_id"] == "6445145"
    # повторный резолв: без дублей в acts и в очереди
    row2 = resolve_act(ACT, "6445145", jb, ix, q)
    assert row2["id"] == row["id"]
    assert len(ix.store["acts"]) == 1
    assert len(q.read_text().splitlines()) == 1


def test_ensure_paragraph_idempotent(tmp_path):
    ix = FakeClient({"act_paragraphs": []})
    act_row = {"id": "act-1"}
    p1 = ensure_paragraph(ix, act_row, "art.14", "цитата", "6445145")
    p2 = ensure_paragraph(ix, act_row, "art.14", "другая", "6445145")
    assert p1["id"] == p2["id"]
    assert len(ix.store["act_paragraphs"]) == 1
