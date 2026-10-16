"""Storage of the playbook assistant (migration 081): the assistant's sessions, the model calls a Head of Sales
imports, the improvement queue and the verdict of each live-help suggestion.

One contract, two implementations: `InMemoryAssistantStore` for tests, `SqlAssistantStore` over the Supabase table
API for production. Until the migration is applied the SQL store raises `AssistantUnavailable` (`not_activated`),
which the API turns into a calm 503; any other database error is not hidden.

Plain dicts, company-scoped: every method takes the company id and never returns another company's row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol

SESSIONS = "playbook_assistant_sessions"
MODEL_CALLS = "playbook_model_calls"
MOMENTS = "playbook_review_moments"
OUTCOMES = "playbook_suggestion_outcomes"

_CLOSED_MOMENT = frozenset({"kept", "corrected", "dismissed"})
_MISSING_TABLE_MARKERS = ("does not exist", "could not find the table", "pgrst205", "42p01")


class AssistantUnavailable(Exception):
    """The assistant's tables are not in the database yet (migration 081 not applied)."""

    code = "not_activated"

    def __init__(self) -> None:
        super().__init__("not_activated")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _is_missing_table(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _MISSING_TABLE_MARKERS)


def _moment_changes(fields: dict) -> dict:
    """A moment that leaves "open" records when it was closed, unless the caller says when."""
    changes = dict(fields)
    if changes.get("status") in _CLOSED_MOMENT and "resolved_at" not in changes:
        changes["resolved_at"] = _now()
    return changes


class AssistantStore(Protocol):
    """Shapes:
      session   {id, company_id, user_id, kind: gaps|trial, state, status: open|done, created_at, updated_at}
      model call {id, company_id, user_id, sales_motion_key, name, transcript, scope, note, proposals,
                  status: proposed|applied|dismissed, created_at}
      moment    {id, company_id, source: trial|real, sales_motion_key, entry_id, objection_type, client_text,
                 suggestion_text, rep_text, outcome, status: open|kept|corrected|dismissed, created_at, resolved_at}
      outcome   {event_id, company_id, observed_at, capture_id, sales_motion_key, entry_id, source_id,
                 objection_type, used, resolved, resolved_by, client_text, suggestion_text, rep_text, judged_at}
    """

    def create_session(self, company_id: str, user_id: str, kind: str, state: dict) -> dict: ...

    def get_session(self, company_id: str, session_id: str) -> Optional[dict]: ...

    def latest_open_session(self, company_id: str, kind: str) -> Optional[dict]: ...

    def save_session(self, company_id: str, session_id: str, *, state: dict, status: Optional[str] = None) -> dict:
        """Replaces the state; the status only changes when one is given. LookupError for an unknown session."""

    def add_model_call(self, company_id: str, user_id: str, row: dict) -> dict: ...

    def get_model_call(self, company_id: str, model_call_id: str) -> Optional[dict]: ...

    def update_model_call(self, company_id: str, model_call_id: str, **fields: Any) -> dict: ...

    def add_moment(self, company_id: str, row: dict) -> dict: ...

    def get_moment(self, company_id: str, moment_id: str) -> Optional[dict]: ...

    def list_moments(self, company_id: str, *, status: Optional[str] = None) -> list[dict]: ...

    def update_moment(self, company_id: str, moment_id: str, **fields: Any) -> dict: ...

    def upsert_outcome(self, company_id: str, row: dict) -> dict:
        """One outcome per live-help event (`event_id`): a second call updates it."""

    def get_outcome(self, company_id: str, event_id: str) -> Optional[dict]: ...

    def list_outcomes(self, company_id: str, *, since: str) -> list[dict]:
        """Outcomes observed at or after `since` (an ISO timestamp)."""

    def judged_event_ids(self, company_id: str, event_ids: list[str]) -> set[str]: ...


def _session_row(company_id: str, user_id: str, kind: str, state: dict) -> dict:
    now = _now()
    return {
        "id": _new_id(), "company_id": company_id, "user_id": user_id, "kind": kind, "state": state,
        "status": "open", "created_at": now, "updated_at": now,
    }


def _model_call_row(company_id: str, user_id: str, row: dict) -> dict:
    return {
        "proposals": [], "status": "proposed", "note": None, "scope": {"kind": "whole"},
        **row, "id": _new_id(), "company_id": company_id, "user_id": user_id, "created_at": _now(),
    }


def _moment_row(company_id: str, row: dict) -> dict:
    return {
        "outcome": {}, "status": "open", "resolved_at": None,
        **row, "id": _new_id(), "company_id": company_id, "created_at": _now(),
    }


def _outcome_row(company_id: str, row: dict) -> dict:
    return {"judged_at": _now(), **row, "company_id": company_id}


class InMemoryAssistantStore:
    def __init__(self) -> None:
        self.sessions: list[dict] = []
        self.model_calls: list[dict] = []
        self.moments: list[dict] = []
        self.outcomes: dict[str, dict] = {}

    @staticmethod
    def _find(rows: list[dict], company_id: str, row_id: str) -> Optional[dict]:
        return next((r for r in rows if r["id"] == row_id and r["company_id"] == company_id), None)

    def create_session(self, company_id, user_id, kind, state):
        row = _session_row(company_id, user_id, kind, state)
        self.sessions.append(row)
        return dict(row)

    def get_session(self, company_id, session_id):
        row = self._find(self.sessions, company_id, session_id)
        return dict(row) if row else None

    def latest_open_session(self, company_id, kind):
        open_rows = [r for r in self.sessions if r["company_id"] == company_id and r["kind"] == kind and r["status"] == "open"]
        return dict(max(open_rows, key=lambda r: r["updated_at"])) if open_rows else None

    def save_session(self, company_id, session_id, *, state, status=None):
        row = self._find(self.sessions, company_id, session_id)
        if row is None:
            raise LookupError("session")
        row["state"] = state
        if status is not None:
            row["status"] = status
        row["updated_at"] = _now()
        return dict(row)

    def add_model_call(self, company_id, user_id, row):
        made = _model_call_row(company_id, user_id, row)
        self.model_calls.append(made)
        return dict(made)

    def get_model_call(self, company_id, model_call_id):
        row = self._find(self.model_calls, company_id, model_call_id)
        return dict(row) if row else None

    def update_model_call(self, company_id, model_call_id, **fields):
        row = self._find(self.model_calls, company_id, model_call_id)
        if row is None:
            raise LookupError("model_call")
        row.update(fields)
        return dict(row)

    def add_moment(self, company_id, row):
        made = _moment_row(company_id, row)
        self.moments.append(made)
        return dict(made)

    def get_moment(self, company_id, moment_id):
        row = self._find(self.moments, company_id, moment_id)
        return dict(row) if row else None

    def list_moments(self, company_id, *, status=None):
        return [
            dict(r) for r in self.moments
            if r["company_id"] == company_id and (status is None or r["status"] == status)
        ]

    def update_moment(self, company_id, moment_id, **fields):
        row = self._find(self.moments, company_id, moment_id)
        if row is None:
            raise LookupError("moment")
        row.update(_moment_changes(fields))
        return dict(row)

    def upsert_outcome(self, company_id, row):
        event_id = str(row["event_id"])
        merged = {**self.outcomes.get(event_id, {}), **_outcome_row(company_id, row)}
        self.outcomes[event_id] = merged
        return dict(merged)

    def get_outcome(self, company_id, event_id):
        row = self.outcomes.get(str(event_id))
        return dict(row) if row and row["company_id"] == company_id else None

    def list_outcomes(self, company_id, *, since):
        return [
            dict(r) for r in self.outcomes.values()
            if r["company_id"] == company_id and str(r.get("observed_at") or "") >= since
        ]

    def judged_event_ids(self, company_id, event_ids):
        return {
            str(e) for e in event_ids
            if str(e) in self.outcomes and self.outcomes[str(e)]["company_id"] == company_id
        }


class SqlAssistantStore:
    """Production: the Supabase table API with the service role (the tables allow nobody else)."""

    def __init__(self, supabase: Any) -> None:
        self.supabase = supabase

    def _run(self, build: Callable[[Any], Any]) -> list[dict]:
        try:
            result = build(self.supabase).execute()
        except Exception as exc:
            if _is_missing_table(exc):
                raise AssistantUnavailable() from exc
            raise
        return list(getattr(result, "data", None) or [])

    def _one(self, build: Callable[[Any], Any]) -> Optional[dict]:
        rows = self._run(build)
        return rows[0] if rows else None

    def create_session(self, company_id, user_id, kind, state):
        row = _session_row(company_id, user_id, kind, state)
        self._run(lambda db: db.table(SESSIONS).insert(row))
        return row

    def get_session(self, company_id, session_id):
        return self._one(lambda db: db.table(SESSIONS).select("*").eq("company_id", company_id).eq("id", session_id).limit(1))

    def latest_open_session(self, company_id, kind):
        return self._one(
            lambda db: db.table(SESSIONS).select("*").eq("company_id", company_id).eq("kind", kind)
            .eq("status", "open").order("updated_at", desc=True).limit(1)
        )

    def save_session(self, company_id, session_id, *, state, status=None):
        changes: dict = {"state": state, "updated_at": _now()}
        if status is not None:
            changes["status"] = status
        row = self._one(lambda db: db.table(SESSIONS).update(changes).eq("company_id", company_id).eq("id", session_id))
        if row is None:
            raise LookupError("session")
        return row

    def add_model_call(self, company_id, user_id, row):
        made = _model_call_row(company_id, user_id, row)
        self._run(lambda db: db.table(MODEL_CALLS).insert(made))
        return made

    def get_model_call(self, company_id, model_call_id):
        return self._one(lambda db: db.table(MODEL_CALLS).select("*").eq("company_id", company_id).eq("id", model_call_id).limit(1))

    def update_model_call(self, company_id, model_call_id, **fields):
        row = self._one(lambda db: db.table(MODEL_CALLS).update(fields).eq("company_id", company_id).eq("id", model_call_id))
        if row is None:
            raise LookupError("model_call")
        return row

    def add_moment(self, company_id, row):
        made = _moment_row(company_id, row)
        self._run(lambda db: db.table(MOMENTS).insert(made))
        return made

    def get_moment(self, company_id, moment_id):
        return self._one(lambda db: db.table(MOMENTS).select("*").eq("company_id", company_id).eq("id", moment_id).limit(1))

    def list_moments(self, company_id, *, status=None):
        def build(db):
            query = db.table(MOMENTS).select("*").eq("company_id", company_id)
            return query.eq("status", status) if status is not None else query

        return self._run(build)

    def update_moment(self, company_id, moment_id, **fields):
        changes = _moment_changes(fields)
        row = self._one(lambda db: db.table(MOMENTS).update(changes).eq("company_id", company_id).eq("id", moment_id))
        if row is None:
            raise LookupError("moment")
        return row

    def upsert_outcome(self, company_id, row):
        made = _outcome_row(company_id, row)
        self._run(lambda db: db.table(OUTCOMES).upsert(made, on_conflict="event_id"))
        return made

    def get_outcome(self, company_id, event_id):
        return self._one(lambda db: db.table(OUTCOMES).select("*").eq("company_id", company_id).eq("event_id", str(event_id)).limit(1))

    def list_outcomes(self, company_id, *, since):
        return self._run(lambda db: db.table(OUTCOMES).select("*").eq("company_id", company_id).gte("observed_at", since))

    def judged_event_ids(self, company_id, event_ids):
        ids = [str(e) for e in event_ids]
        if not ids:
            return set()
        rows = self._run(lambda db: db.table(OUTCOMES).select("event_id").eq("company_id", company_id).in_("event_id", ids))
        return {str(r["event_id"]) for r in rows}


_current: Optional[AssistantStore] = None


def set_assistant_store(store: Optional[AssistantStore]) -> None:
    """Tests install their own store; None goes back to the SQL one."""
    global _current
    _current = store


def get_assistant_store(supabase: Any) -> AssistantStore:
    return _current if _current is not None else SqlAssistantStore(supabase)
