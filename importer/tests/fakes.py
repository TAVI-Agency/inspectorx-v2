"""Мини-фейки supabase-py для юнит-тестов импортёра (без сети и без БД).

Поддерживают цепочки в стиле supabase:
  table(name).select("*").eq(col, val).ilike(col, "%x%").limit(n).execute() -> .data
  table(name).insert(row).execute() -> .data (с автогенерённым id)
  table(name).update(patch).eq(...).execute() -> патч по отфильтрованным строкам
  table(name).delete().eq(...).execute() -> удаление отфильтрованных строк
"""


def _result(rows):
    return type("R", (), {"data": rows})()


class FakeTable:
    def __init__(self, store, name):
        self.store = store
        self.name = name
        self._filters = []
        self._op = "select"
        self._patch = None

    def select(self, *_):
        self._op = "select"
        return self

    def limit(self, *_):
        return self

    def eq(self, col, val):
        self._filters.append(lambda r: r.get(col) == val)
        return self

    def ilike(self, col, pattern):
        needle = pattern.strip("%")
        self._filters.append(lambda r: needle in (r.get(col) or ""))
        return self

    def insert(self, row):
        row = {"id": f"id-{len(self.store.get(self.name, []))}", **row}
        self.store.setdefault(self.name, []).append(row)
        store_row = row
        return type("Q", (), {"execute": lambda self_: _result([store_row])})()

    def update(self, patch):
        self._op = "update"
        self._patch = patch
        return self

    def delete(self):
        self._op = "delete"
        return self

    def execute(self):
        rows = self.store.get(self.name, [])
        matched = [r for r in rows if all(f(r) for f in self._filters)]
        if self._op == "update":
            for r in matched:
                r.update(self._patch)
            result = matched
        elif self._op == "delete":
            matched_ids = {id(r) for r in matched}
            self.store[self.name] = [r for r in rows if id(r) not in matched_ids]
            result = matched
        else:
            result = matched
        self._filters = []
        self._op = "select"
        self._patch = None
        return _result(result)


class FakeClient:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return FakeTable(self.store, name)
