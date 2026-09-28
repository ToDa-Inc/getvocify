"""In-memory stand-in for the supabase-py query builder used by the reporting tests."""

from __future__ import annotations

from types import SimpleNamespace


def _matches_or(row: dict, clause: str) -> bool:
    for part in clause.split(","):
        column, op, value = part.split(".", 2)
        if op == "eq" and str(row.get(column)) == value:
            return True
        if op == "is" and value == "null" and row.get(column) is None:
            return True
    return False


class _Query:
    def __init__(self, db: "FakeDB", table: str):
        self.db = db
        self.table = table
        self.filters: list = []
        self.payload = None
        self.mode = "select"
        self.on_conflict: str | None = None
        self.ignore_duplicates = False
        self._limit: int | None = None
        self._order: tuple[str, bool] | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.filters.append(lambda row: str(row.get(column)) == str(value))
        return self

    def neq(self, column, value):
        self.filters.append(lambda row: str(row.get(column)) != str(value))
        return self

    def in_(self, column, values):
        allowed = {str(v) for v in values}
        self.filters.append(lambda row: str(row.get(column)) in allowed)
        return self

    def gte(self, column, value):
        self.filters.append(lambda row: row.get(column) is not None and str(row.get(column)) >= str(value))
        return self

    def lt(self, column, value):
        self.filters.append(lambda row: row.get(column) is not None and str(row.get(column)) < str(value))
        return self

    def or_(self, clause):
        self.filters.append(lambda row: _matches_or(row, clause))
        return self

    def order(self, column, desc=False):
        self._order = (column, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload):
        self.mode, self.payload = "insert", payload
        return self

    def upsert(self, payload, on_conflict=None, ignore_duplicates=False):
        self.mode, self.payload = "upsert", payload
        self.on_conflict = on_conflict
        self.ignore_duplicates = ignore_duplicates
        return self

    def update(self, payload):
        self.mode, self.payload = "update", payload
        return self

    def execute(self):
        self.db.calls.append((self.table, self.mode))
        if self.table in self.db.fail_tables:
            raise RuntimeError(f"{self.table} unavailable")
        rows = self.db.tables.setdefault(self.table, [])
        if self.mode == "insert":
            added = self.payload if isinstance(self.payload, list) else [self.payload]
            rows.extend(dict(row) for row in added)
            return SimpleNamespace(data=[dict(row) for row in added])
        if self.mode == "upsert":
            keys = [key for key in (self.on_conflict or "id").split(",") if key]
            payload = dict(self.payload)
            for row in rows:
                if all(str(row.get(key)) == str(payload.get(key)) for key in keys):
                    if self.ignore_duplicates:
                        return SimpleNamespace(data=[])
                    row.update(payload)
                    return SimpleNamespace(data=[dict(row)])
            rows.append(payload)
            return SimpleNamespace(data=[dict(payload)])
        kept = [row for row in rows if all(check(row) for check in self.filters)]
        if self.mode == "update":
            for row in kept:
                row.update(self.payload)
            return SimpleNamespace(data=[dict(row) for row in kept])
        if self._order:
            column, desc = self._order
            kept = sorted(kept, key=lambda row: str(row.get(column) or ""), reverse=desc)
        if self._limit is not None:
            kept = kept[: self._limit]
        return SimpleNamespace(data=[dict(row) for row in kept])


class _AuthUsers:
    def __init__(self, db: "FakeDB"):
        self.db = db
        self.ids: list[str] = []

    def select(self, *_args):
        return self

    def in_(self, _column, values):
        self.ids = [str(v) for v in values]
        return self

    def execute(self):
        return SimpleNamespace(data=[
            {"id": uid, "email": email}
            for uid, email in self.db.emails.items()
            if uid in self.ids
        ])


class FakeDB:
    def __init__(self, tables: dict | None = None, *, emails: dict | None = None, fail_tables=()):
        self.tables: dict[str, list[dict]] = {name: list(rows) for name, rows in (tables or {}).items()}
        self.emails = dict(emails or {})
        self.fail_tables = set(fail_tables)
        self.calls: list[tuple[str, str]] = []

    def table(self, name: str):
        return _Query(self, name)

    @property
    def postgrest(self):
        return self

    def schema(self, _name: str):
        return self

    def from_(self, _name: str):
        return _AuthUsers(self)
