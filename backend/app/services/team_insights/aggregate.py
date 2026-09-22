"""Team metrics. Members get nothing. Adherence is the sum of counts, not the average of rates."""

from __future__ import annotations

from app.services.coaching.metrics import aggregate_adherence

_TEAM_ROLES = frozenset({"owner", "admin"})


class TeamAccessError(Exception):
    pass


def assert_team_reader(role: str) -> None:
    if role not in _TEAM_ROLES:
        raise TeamAccessError("equipo denegado")


def authorized_scope(*, role: str, requested_user_id: str | None, instruction: str) -> dict:
    """Free text never widens the scope. The role is the server's."""
    del instruction
    assert_team_reader(role)
    if requested_user_id:
        return {"scope": "user", "user_id": requested_user_id}
    return {"scope": "team", "user_id": None}


def team_adherence(*, role: str, parts: list[dict], playbook_present: bool, sample_size: int) -> dict:
    assert_team_reader(role)
    if not playbook_present or sample_size < 1:
        return {
            "met_steps": 0,
            "applicable_steps": 0,
            "unknown_steps": 0,
            "adherence": None,
            "coverage": None,
            "conclusion": None,
        }
    metrics = aggregate_adherence(parts)
    conclusion = None
    if sample_size < 5:
        conclusion = None
    return {
        "met_steps": metrics["met_steps"],
        "applicable_steps": metrics["applicable_steps"],
        "unknown_steps": metrics["unknown_steps"],
        "adherence": metrics["adherence"],
        "coverage": metrics["coverage"],
        "conclusion": conclusion,
    }
