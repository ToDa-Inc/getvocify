"""An in-memory Supabase with the query shapes the MCP server uses. Never touches a real database."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


class _Result:
    def __init__(self, data):
        self.data = data


def _text(value) -> str:
    return "" if value is None else str(value)


class _Query:
    def __init__(self, db: "FakeDB", name: str):
        self._db = db
        self._name = name
        self._filters: list = []
        self._order = None
        self._desc = False
        self._limit = None
        self._single = False
        self._write = None  # ("update", payload) | ("insert", rows) | ("upsert", rows, keys) | ("delete",)

    # reads
    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append(lambda r, c=column, v=value: _text(r.get(c)) == _text(v) if v is not None else r.get(c) is None)
        return self

    def in_(self, column, values):
        allowed = {_text(v) for v in values}
        self._filters.append(lambda r, c=column: _text(r.get(c)) in allowed)
        return self

    def gte(self, column, value):
        self._filters.append(lambda r, c=column, v=_text(value): r.get(c) is not None and _text(r.get(c)) >= v)
        return self

    def lt(self, column, value):
        self._filters.append(lambda r, c=column, v=_text(value): r.get(c) is not None and _text(r.get(c)) < v)
        return self

    def lte(self, column, value):
        self._filters.append(lambda r, c=column, v=_text(value): r.get(c) is not None and _text(r.get(c)) <= v)
        return self

    def like(self, column, pattern):
        prefix = pattern.rstrip("%")
        self._filters.append(lambda r, c=column: _text(r.get(c)).startswith(prefix))
        return self

    def or_(self, expression):
        parts = [part.split(".", 2) for part in expression.split(",")]

        def keep(row):
            for column, op, value in parts:
                if op == "eq" and _text(row.get(column)) == value:
                    return True
                if op == "is" and value == "null" and row.get(column) is None:
                    return True
            return False

        self._filters.append(keep)
        return self

    def order(self, column, desc=False):
        self._order, self._desc = column, desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        self._single = True
        return self

    # writes
    def update(self, payload):
        self._write = ("update", dict(payload))
        return self

    def insert(self, rows):
        self._write = ("insert", rows if isinstance(rows, list) else [rows])
        return self

    def upsert(self, rows, on_conflict=None):
        keys = [k.strip() for k in (on_conflict or "id").split(",")]
        self._write = ("upsert", rows if isinstance(rows, list) else [rows], keys)
        return self

    def delete(self):
        self._write = ("delete",)
        return self

    def _matching(self, rows):
        return [r for r in rows if all(f(r) for f in self._filters)]

    def execute(self):
        table = self._db.tables.setdefault(self._name, [])
        self._db.calls.append(self._name)
        if self._write:
            kind = self._write[0]
            if kind == "insert":
                for row in self._write[1]:
                    table.append(dict(row))
                return _Result([dict(r) for r in self._write[1]])
            if kind == "upsert":
                _, rows, keys = self._write
                for row in rows:
                    hit = next((r for r in table if all(_text(r.get(k)) == _text(row.get(k)) for k in keys)), None)
                    if hit is None:
                        table.append(dict(row))
                    else:
                        hit.update(row)
                return _Result([dict(r) for r in rows])
            hits = self._matching(table)
            if kind == "update":
                for row in hits:
                    row.update(self._write[1])
                return _Result([dict(r) for r in hits])
            self._db.tables[self._name] = [r for r in table if r not in hits]
            return _Result([])
        rows = [dict(r) for r in self._matching(table)]
        if self._order:
            rows.sort(key=lambda r: _text(r.get(self._order)), reverse=self._desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._single:
            return _Result(rows[0] if rows else None)
        return _Result(rows)


class _Rpc:
    def __init__(self, db: "FakeDB", name: str, params: dict):
        self._db, self._name, self._params = db, name, params

    def execute(self):
        if self._name != "save_ask_turn":
            raise NotImplementedError(self._name)
        p = self._params
        turns = self._db.tables.setdefault("copilot_web_turns", [])
        for row in turns:
            if (row["user_id"], row["conversation_id"], row["client_turn_id"]) == (p["p_user"], p["p_conversation"], p["p_client_turn"]):
                return _Result([{"turn_id": row["id"], "body": row["body"], "replayed": True}])
        row = {
            "id": str(uuid.uuid4()),
            "company_id": p["p_company"],
            "user_id": p["p_user"],
            "conversation_id": p["p_conversation"],
            "client_turn_id": p["p_client_turn"],
            "status": "pending",
            "body": p["p_text"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        turns.append(row)
        return _Result([{"turn_id": row["id"], "body": row["body"], "replayed": False}])


class FakeDB:
    def __init__(self, **tables):
        self.tables: dict[str, list[dict]] = {name: [dict(r) for r in rows] for name, rows in tables.items()}
        self.calls: list[str] = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        return _Rpc(self, name, params)
