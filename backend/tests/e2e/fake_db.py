"""In-memory stand-in for the Supabase client, close enough to PostgREST for the harmony test.

Only the database is faked here. It keeps the parts of PostgREST that change what the app sees:
`select` returns only the requested columns, a column the table does not have is an error,
`or_`/`order`/`limit` filter and sort, upserts respect the table's unique key, and timestamptz
columns come back in UTC with DB-default `created_at`.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from tests.playbooks.live_double import TablesWithLiveView

ABSENT_COLUMNS = {"memos": frozenset({"connection_id"})}

UNIQUE_KEYS = {
    "action_signals": ("company_id", "user_id", "connection_id", "dedupe_key"),
    "memo_scores": ("memo_id", "input_revision"),
    "post_interaction_briefs": ("memo_id", "input_revision"),
    "interaction_patterns": ("memo_id", "pattern_id", "input_revision"),
    "meeting_proposals": ("memo_id", "proposal_id", "input_revision"),
    "meeting_writes": ("operation_key",),
    "memo_jobs": ("memo_id", "kind", "input_revision"),
    "brief_preferences": ("user_id",),
}

TIMESTAMPTZ = frozenset({
    "created_at", "starts_at", "capture_started_at", "approved_at", "processed_at",
    "processing_started_at", "followup_run_started_at", "pipeline_run_started_at",
    "undo_deadline", "observed_at", "updated_at",
})

_DEFAULTS = {
    "action_signals": {"status": "pending", "version": 1},
    "interaction_patterns": {"superseded": False, "evidence_refs": []},
    "meeting_proposals": {"decision": "pending", "crm_status": "not_requested"},
}


class APIError(Exception):
    """What postgrest-py raises for a bad query."""


def _utc(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return value
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _normalize(row: dict) -> dict:
    return {key: (_utc(value) if key in TIMESTAMPTZ else value) for key, value in row.items()}


def _cell(row: dict, column: str):
    if "->>" in column:
        base, key = column.split("->>", 1)
        value = (row.get(base) or {}).get(key)
        return None if value is None else str(value).lower() if isinstance(value, bool) else str(value)
    if "." in column:
        base, key = column.split(".", 1)
        nested = row.get(base)
        if isinstance(nested, list):
            return [item.get(key) for item in nested if isinstance(item, dict)]
    return row.get(column)


def _compare(row: dict, column: str, op: str, value) -> bool:
    cell = _cell(row, column)
    if isinstance(cell, list):
        return any(_compare({"v": item}, "v", op, value) for item in cell)
    if op == "is":
        return cell is None if str(value).lower() == "null" else cell == value
    if op == "eq":
        if column in TIMESTAMPTZ:
            return _utc(cell) == _utc(value)
        return cell == value or (cell is not None and str(cell) == str(value) and "->>" in column)
    if op == "neq":
        return cell != value
    if cell is None:
        return False
    left, right = (_utc(cell), _utc(value)) if column in TIMESTAMPTZ else (cell, value)
    return {
        "lt": lambda: left < right,
        "lte": lambda: left <= right,
        "gt": lambda: left > right,
        "gte": lambda: left >= right,
    }[op]()


def _or_clause(expr: str):
    clauses = []
    for part in expr.split(","):
        column, op, value = part.split(".", 2)
        clauses.append((column, op, value))
    return clauses


class _Query:
    def __init__(self, db: "FakeDB", name: str):
        self._db = db
        self._name = name
        self._columns: list[str] | None = None
        self._filters: list[tuple[str, str, Any]] = []
        self._ors: list[list[tuple[str, str, Any]]] = []
        self._order: list[tuple[str, bool]] = []
        self._limit: int | None = None
        self._range: tuple[int, int] | None = None
        self._single = False
        self._op: str | None = None
        self._payload = None
        self._on_conflict: tuple[str, ...] | None = None
        self._ignore_duplicates = False

    def select(self, *cols, **_kwargs):
        raw = ",".join(cols) if cols else "*"
        columns = [c.strip() for c in raw.split(",") if c.strip()]
        absent = ABSENT_COLUMNS.get(self._name, frozenset()) & set(columns)
        if absent:
            raise APIError(f"column {self._name}.{sorted(absent)[0]} does not exist")
        self._columns = None if "*" in columns else columns
        return self

    def eq(self, column, value):
        self._filters.append((column, "eq", value))
        return self

    def neq(self, column, value):
        self._filters.append((column, "neq", value))
        return self

    def gt(self, column, value):
        self._filters.append((column, "gt", value))
        return self

    def gte(self, column, value):
        self._filters.append((column, "gte", value))
        return self

    def lt(self, column, value):
        self._filters.append((column, "lt", value))
        return self

    def lte(self, column, value):
        self._filters.append((column, "lte", value))
        return self

    def is_(self, column, value):
        self._filters.append((column, "is", value))
        return self

    def in_(self, column, values):
        self._filters.append((column, "in", [str(v) for v in values]))
        return self

    def or_(self, expr):
        self._ors.append(_or_clause(expr))
        return self

    def order(self, column, desc=False, **_kwargs):
        self._order.append((column, bool(desc)))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, start, end):
        """PostgREST-style inclusive [start, end] page."""
        self._range = (start, end)
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._single = True
        return self

    def insert(self, payload, **_kwargs):
        self._op, self._payload = "insert", payload
        return self

    def upsert(self, payload, on_conflict: str | None = None, ignore_duplicates: bool = False, **_kwargs):
        self._op, self._payload = "upsert", payload
        if on_conflict:
            self._on_conflict = tuple(c.strip() for c in on_conflict.split(","))
        self._ignore_duplicates = ignore_duplicates
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def _matches(self, row: dict) -> bool:
        for column, op, value in self._filters:
            if op == "in":
                if str(_cell(row, column) or "") not in value:
                    return False
            elif not _compare(row, column, op, value):
                return False
        for clauses in self._ors:
            if not any(_compare(row, c, op, v) for c, op, v in clauses):
                return False
        return True

    def _project(self, row: dict) -> dict:
        if self._columns is None:
            return copy.deepcopy(row)
        out = {}
        for column in self._columns:
            name = column.split("!", 1)[0].split("(", 1)[0].strip()
            if name in row:
                out[name] = copy.deepcopy(row[name])
        return out

    def _new_row(self, payload: dict) -> dict:
        row = {**_DEFAULTS.get(self._name, {}), **copy.deepcopy(payload)}
        row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("created_at", self._db.clock.isoformat())
        return _normalize(row)

    def _result(self, rows: list[dict]):
        data = [self._project(row) for row in rows]
        if self._single:
            return SimpleNamespace(data=data[0] if data else None)
        return SimpleNamespace(data=data)

    def execute(self):
        self._db.calls.append((self._name, self._op or "select"))
        table = self._db.tables.setdefault(self._name, [])
        if self._op in ("insert", "upsert"):
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            written = []
            key = self._on_conflict or UNIQUE_KEYS.get(self._name)
            for payload in payloads:
                incoming = _normalize(copy.deepcopy(payload))
                match = None
                if key and all(c in incoming for c in key):
                    match = next((r for r in table if all(r.get(c) == incoming.get(c) for c in key)), None)
                if match is not None and self._op == "insert":
                    raise APIError(f"duplicate key value violates unique constraint on {self._name}")
                if match is not None:
                    if not self._ignore_duplicates:
                        match.update(incoming)
                        written.append(match)
                    continue
                row = self._new_row(payload)
                table.append(row)
                written.append(row)
            return SimpleNamespace(data=[copy.deepcopy(r) for r in written])
        rows = [row for row in table if self._matches(row)]
        if self._op == "update":
            for row in rows:
                row.update(_normalize(copy.deepcopy(self._payload)))
            return SimpleNamespace(data=[copy.deepcopy(r) for r in rows])
        if self._op == "delete":
            self._db.tables[self._name] = [row for row in table if row not in rows]
            return SimpleNamespace(data=[copy.deepcopy(r) for r in rows])
        for column, desc in reversed(self._order):
            rows.sort(key=lambda r: (r.get(column) is None, str(r.get(column) or "")), reverse=desc)
        if self._range is not None:
            rows = rows[self._range[0] : self._range[1] + 1]
        if self._limit is not None:
            rows = rows[: self._limit]
        return self._result(rows)


class _Admin:
    def __init__(self, emails: dict[str, str]):
        self._emails = emails

    def get_user_by_id(self, uid):
        return SimpleNamespace(user=SimpleNamespace(email=self._emails.get(str(uid), "")))


class FakeDB:
    """tables[name] -> rows. `clock` is the database's now() for created_at defaults."""

    def __init__(self, *, clock: datetime, emails: dict[str, str] | None = None, **tables):
        self.clock = clock
        self.tables: dict[str, list[dict]] = TablesWithLiveView({name: [_normalize(r) for r in rows] for name, rows in tables.items()})
        self.calls: list[tuple[str, str]] = []
        self.auth = SimpleNamespace(admin=_Admin(emails or {}))

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def rows(self, name: str, **where) -> list[dict]:
        return [r for r in self.tables.get(name, []) if all(r.get(k) == v for k, v in where.items())]
