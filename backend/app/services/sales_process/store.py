"""Storage of a company's own sales process and of the interaction types each member runs (migration 084).

One contract, two implementations (the pattern of the playbook assistant's store): `InMemorySalesProcessStore` for tests and
`SqlSalesProcessStore` over the Supabase table API for production. Until the migration is applied the SQL store raises
`SalesProcessUnavailable` (`not_activated`); any other database error is not hidden. Company-scoped plain dicts.

  process row  {company_id, sales_motion_key, position, stage, goal}  one per type of the company's process
  member row   {id, company_id, user_id | invitation_id, types}        `types` None = every type of the process
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Optional, Protocol

PROCESS = "company_sales_process"
MEMBERS = "member_interaction_types"
_MISSING_TABLE_MARKERS = ("does not exist", "could not find the table", "pgrst205", "42p01")


class SalesProcessUnavailable(Exception):
    """The tables of migration 084 are not in the database yet."""

    code = "not_activated"

    def __init__(self) -> None:
        super().__init__("not_activated")


def _is_missing_table(exc: Exception) -> bool:
    return any(marker in str(exc).lower() for marker in _MISSING_TABLE_MARKERS)


def _clean(types: Optional[list[str]]) -> Optional[list[str]]:
    kept = list(dict.fromkeys(str(t) for t in types or [] if str(t).strip()))
    return kept or None


def _public_row(row: dict) -> dict:
    return {"key": row["sales_motion_key"], "position": row["position"], "stage": row["stage"], "goal": row.get("goal") or None}


def _stored_row(company_id: str, row: dict) -> dict:
    return {"company_id": company_id, "sales_motion_key": row["key"], "position": row["position"], "stage": row["stage"], "goal": row.get("goal") or None}


def _listed(rows: list[dict]) -> dict:
    return {
        "members": {str(r["user_id"]): (list(r["types"]) if r.get("types") else None) for r in rows if r.get("user_id")},
        "invitations": {str(r["invitation_id"]): (list(r["types"]) if r.get("types") else None) for r in rows if r.get("invitation_id")},
    }


def _who(user_id: Optional[str], invitation_id: Optional[str]) -> tuple[str, str]:
    if bool(user_id) == bool(invitation_id):
        raise ValueError("a member row needs a user or an invitation")
    return ("user_id", str(user_id)) if user_id else ("invitation_id", str(invitation_id))


class SalesProcessStore(Protocol):
    def list_process(self, company_id: str) -> list[dict]:
        """[{key, position, stage, goal}] in process order (`goal` None when none was given)."""

    def replace_process(self, company_id: str, rows: list[dict]) -> None:
        """The process becomes exactly `rows` ([{key, position, stage, goal?}])."""

    def get_member_types(self, company_id: str, *, user_id: Optional[str] = None, invitation_id: Optional[str] = None) -> Optional[list[str]]: ...

    def set_member_types(
        self, company_id: str, types: Optional[list[str]], *, user_id: Optional[str] = None, invitation_id: Optional[str] = None,
    ) -> None:
        """None or an empty list = every type. ValueError unless exactly one of user_id / invitation_id is given."""

    def list_member_types(self, company_id: str) -> dict:
        """{members: {user_id: types | None}, invitations: {invitation_id: types | None}} of everything stored."""

    def drop_type(self, company_id: str, key: str) -> None:
        """Takes the type out of the process and out of every member's and invitation's list (an empty list becomes None)."""


class InMemorySalesProcessStore:
    def __init__(self) -> None:
        self.process: list[dict] = []
        self.members: list[dict] = []

    def list_process(self, company_id):
        rows = [r for r in self.process if r["company_id"] == company_id]
        return [_public_row(r) for r in sorted(rows, key=lambda r: r["position"])]

    def replace_process(self, company_id, rows):
        self.process = [r for r in self.process if r["company_id"] != company_id]
        self.process += [_stored_row(company_id, r) for r in rows]

    def _member(self, company_id, column, value):
        return next((m for m in self.members if m["company_id"] == company_id and m.get(column) == value), None)

    def get_member_types(self, company_id, *, user_id=None, invitation_id=None):
        row = self._member(company_id, *_who(user_id, invitation_id))
        return list(row["types"]) if row and row["types"] else None

    def set_member_types(self, company_id, types, *, user_id=None, invitation_id=None):
        column, value = _who(user_id, invitation_id)
        row = self._member(company_id, column, value)
        if row is None:
            row = {"id": str(uuid.uuid4()), "company_id": company_id, "user_id": None, "invitation_id": None, column: value}
            self.members.append(row)
        row["types"] = _clean(types)

    def list_member_types(self, company_id):
        return _listed([m for m in self.members if m["company_id"] == company_id])

    def drop_type(self, company_id, key):
        self.process = [r for r in self.process if not (r["company_id"] == company_id and r["sales_motion_key"] == key)]
        for row in self.members:
            if row["company_id"] == company_id and row["types"]:
                row["types"] = _clean([t for t in row["types"] if t != key])


class SqlSalesProcessStore:
    """Production: the Supabase table API with the service role (the tables allow nobody else)."""

    def __init__(self, supabase: Any) -> None:
        self.supabase = supabase

    def _run(self, build: Callable[[Any], Any]) -> list[dict]:
        try:
            result = build(self.supabase).execute()
        except Exception as exc:
            if _is_missing_table(exc):
                raise SalesProcessUnavailable() from exc
            raise
        return list(getattr(result, "data", None) or [])

    def list_process(self, company_id):
        rows = self._run(lambda db: db.table(PROCESS).select("*").eq("company_id", company_id))
        return [_public_row(r) for r in sorted(rows, key=lambda r: r["position"])]

    def replace_process(self, company_id, rows):
        self._run(lambda db: db.table(PROCESS).delete().eq("company_id", company_id))
        for r in rows:
            made = _stored_row(company_id, r)
            self._run(lambda db, made=made: db.table(PROCESS).insert(made))

    def _member(self, company_id, column, value):
        rows = self._run(lambda db: db.table(MEMBERS).select("*").eq("company_id", company_id).eq(column, value).limit(1))
        return rows[0] if rows else None

    def get_member_types(self, company_id, *, user_id=None, invitation_id=None):
        row = self._member(company_id, *_who(user_id, invitation_id))
        return list(row["types"]) if row and row.get("types") else None

    def set_member_types(self, company_id, types, *, user_id=None, invitation_id=None):
        column, value = _who(user_id, invitation_id)
        kept = _clean(types)
        if self._member(company_id, column, value) is None:
            self._run(lambda db: db.table(MEMBERS).insert({"company_id": company_id, column: value, "types": kept}))
        else:
            self._run(lambda db: db.table(MEMBERS).update({"types": kept}).eq("company_id", company_id).eq(column, value))

    def list_member_types(self, company_id):
        return _listed(self._run(lambda db: db.table(MEMBERS).select("*").eq("company_id", company_id)))

    def drop_type(self, company_id, key):
        self._run(lambda db: db.table(PROCESS).delete().eq("company_id", company_id).eq("sales_motion_key", key))
        for row in self._run(lambda db: db.table(MEMBERS).select("*").eq("company_id", company_id)):
            if row.get("types") and key in row["types"]:
                left = _clean([t for t in row["types"] if t != key])
                column = "user_id" if row.get("user_id") else "invitation_id"
                self._run(lambda db, row=row, left=left, column=column: db.table(MEMBERS).update({"types": left}).eq("company_id", company_id).eq(column, row[column]))


_current: Optional[SalesProcessStore] = None


def set_sales_process_store(store: Optional[SalesProcessStore]) -> None:
    """Tests install their own store; None goes back to the SQL one."""
    global _current
    _current = store


def get_sales_process_store(supabase: Any) -> SalesProcessStore:
    return _current if _current is not None else SqlSalesProcessStore(supabase)
