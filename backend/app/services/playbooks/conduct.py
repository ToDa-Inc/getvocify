"""«Cómo trabajamos»: what a good outcome of a call type is and how the company conducts these calls (migration 087).

The playbook's steps, qualification and objections say WHAT to cover; this says how to decide. Written by the manager in
their own words, one per call type, not versioned (a change applies to the next call):

  conduct  {goal, also_good, stop_when, criteria: [text]}
    goal       what the call is for ("una demo con alguien que tenga una necesidad real")
    also_good  the other outcomes that count as a good call (find who decides, a follow-up tied to something, disqualify)
    stop_when  when to stop pursuing the goal (no need after exploring it, a clear no, no fit)
    criteria   up to MAX_CRITERIA lines, "cuando… → …"

The live card brain reads it as guidance next to the playbook, never as a SOURCE: a card cannot rest on it to state a
fact. Until the migration is applied the SQL store raises ConductUnavailable (`not_activated`) and the brain reads none.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MAX_GOAL = 200
MAX_OUTCOME = 300
MAX_CRITERION = 220
MAX_CRITERIA = 8
_MISSING_MARKERS = ("does not exist", "could not find", "pgrst204", "42703")


class ConductUnavailable(Exception):
    """The column of migration 087 is not in the database yet."""

    code = "not_activated"

    def __init__(self) -> None:
        super().__init__("not_activated")


class Conduct(BaseModel):
    goal: str = Field(default="", max_length=MAX_GOAL)
    also_good: str = Field(default="", max_length=MAX_OUTCOME)
    stop_when: str = Field(default="", max_length=MAX_OUTCOME)
    criteria: list[str] = Field(default_factory=list, max_length=MAX_CRITERIA)


def _line(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


def normalize(raw: Any) -> Optional[dict]:
    """The stored shape: trimmed, one line each, empty criteria dropped; None when nothing is written."""
    if not isinstance(raw, dict):
        return None
    criteria = [_line(item, MAX_CRITERION) for item in raw.get("criteria") or [] if _line(item, MAX_CRITERION)][:MAX_CRITERIA]
    conduct = {
        "goal": _line(raw.get("goal"), MAX_GOAL),
        "also_good": _line(raw.get("also_good"), MAX_OUTCOME),
        "stop_when": _line(raw.get("stop_when"), MAX_OUTCOME),
        "criteria": criteria,
    }
    return conduct if any(conduct.values()) else None


def empty() -> dict:
    return {"goal": "", "also_good": "", "stop_when": "", "criteria": []}


def brain_text(conduct: Optional[dict], usual_goal: Optional[str]) -> str:
    """What the live brain reads in place of the goal fixed in code: the company's goal with its other good outcomes and
    when to stop, then its criteria. "" when nothing is written (the brain keeps the usual goal)."""
    conduct = normalize(conduct)
    if not conduct:
        return ""
    goal = conduct["goal"] or usual_goal or ""
    lines = [f"- Main goal: {goal}" if goal else "",
             f"- Also good outcomes: {conduct['also_good']}" if conduct["also_good"] else "",
             f"- Stop pursuing the main goal when: {conduct['stop_when']}" if conduct["stop_when"] else ""]
    parts = []
    if any(lines):
        parts.append("COMPANY GOAL FOR THIS TYPE OF CALL (written by the company; the direction, not an order):\n"
                     + "\n".join(line for line in lines if line))
    if conduct["criteria"]:
        parts.append("HOW THIS COMPANY CONDUCTS THESE CALLS (written by the company; guidance on how to decide, never a "
                     "source of facts):\n" + "\n".join(f"{n}. {text}" for n, text in enumerate(conduct["criteria"], 1)))
    return "\n\n".join(parts)


def _is_missing_column(exc: Exception) -> bool:
    text = str(exc).lower()
    return "conduct" in text and any(marker in text for marker in _MISSING_MARKERS)


class ConductStore(Protocol):
    def get(self, company_id: str, key: str) -> Optional[dict]:
        """The type's conduct, None when nothing is written."""

    def set(self, company_id: str, key: str, conduct: Optional[dict]) -> None:
        """Stores it (None clears it); creates the type's playbook row when it has none."""


class InMemoryConductStore:
    """TEST FAKE."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], Optional[dict]] = {}

    def get(self, company_id, key):
        return self.rows.get((company_id, key))

    def set(self, company_id, key, conduct):
        self.rows[(company_id, key)] = conduct


class SqlConductStore:
    """Production: the `playbooks` row of the type, through the Supabase table API with the service role."""

    def __init__(self, supabase: Any) -> None:
        self.supabase = supabase

    def _run(self, build: Callable[[Any], Any]) -> list[dict]:
        try:
            result = build(self.supabase).execute()
        except Exception as exc:
            if _is_missing_column(exc):
                raise ConductUnavailable() from exc
            raise
        return list(getattr(result, "data", None) or [])

    def get(self, company_id, key):
        rows = self._run(lambda db: db.table("playbooks").select("conduct").eq("company_id", company_id)
                         .eq("sales_motion_key", key).limit(1))
        return normalize(rows[0].get("conduct")) if rows else None

    def set(self, company_id, key, conduct):
        # The column first: before migration 087 nothing is created for a type that had no playbook row.
        self._run(lambda db: db.table("playbooks").select("conduct").eq("company_id", company_id).limit(1))
        self.supabase.rpc("playbook_set_meta", {"p_company": company_id, "p_motion": key, "p_meta": {}}).execute()
        self._run(lambda db: db.table("playbooks").update({"conduct": conduct}).eq("company_id", company_id)
                  .eq("sales_motion_key", key))


_current: Optional[ConductStore] = None


def set_conduct_store(store: Optional[ConductStore]) -> None:
    """Tests install their own store; None goes back to the SQL one."""
    global _current
    _current = store


def get_conduct_store(supabase: Any) -> ConductStore:
    return _current if _current is not None else SqlConductStore(supabase)


def read_for_brain(supabase: Any, company_id: str, key: Optional[str]) -> Optional[dict]:
    """The conduct a live reading uses: None when the type has none, the migration is not applied or the read fails
    (a card is never blocked by it)."""
    if not key:
        return None
    try:
        return get_conduct_store(supabase).get(company_id, key)
    except ConductUnavailable:
        return None
    except Exception:
        logger.warning("live help: reading the playbook's conduct failed", extra={"company_id": company_id}, exc_info=True)
        return None
