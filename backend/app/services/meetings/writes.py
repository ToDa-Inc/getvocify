"""Write one meeting activity. A repeat uses the same remote id. No stage change without a mapping."""

from __future__ import annotations


class MeetingWriteError(Exception):
    def __init__(self, code: str):
        self.code = code


def with_meeting(payload: dict, *, proposal_id: str, input_revision: str, decision: str, starts_at: str | None, timezone: str) -> dict:
    return {
        **payload,
        "meeting": {
            "proposal_id": proposal_id,
            "input_revision": input_revision,
            "decision": decision,
            "starts_at": starts_at,
            "timezone": timezone,
        },
    }


def register_meeting(
    *,
    proposal: dict,
    decision: str,
    operation_key: str,
    writer,
    stage_mapping: str | None,
    existing: dict | None,
    starts_at: str | None = None,
) -> dict:
    if decision == "omit":
        return _result("not_requested", None, False, replayed=False)
    if decision not in {"accept", "corrected"}:
        raise MeetingWriteError("invalid")
    if decision == "accept" and (proposal.get("needs_review") or proposal.get("precision") == "ambiguous" or not proposal.get("starts_at")):
        raise MeetingWriteError("needs_correction")
    if decision == "corrected" and not starts_at:
        raise MeetingWriteError("needs_correction")
    if existing and existing.get("remote_id"):
        return _result("succeeded", existing["remote_id"], False, replayed=True)
    if existing and existing.get("crm_status") == "uncertain":
        found = writer.reconcile(operation_key)
        if found:
            return _result("succeeded", found, False, replayed=True)
    try:
        remote_id = writer.create(operation_key, proposal)
    except TimeoutError:
        return _result("uncertain", None, False, replayed=False)
    except MeetingWriteError as exc:
        if exc.code in {"failed", "forbidden"}:
            return _result("failed", None, False, replayed=False)
        raise
    stage_changed = False
    if stage_mapping:
        writer.change_stage(stage_mapping)
        stage_changed = True
    return _result("succeeded", remote_id, stage_changed, replayed=False)


def _result(crm_status: str, remote_id: str | None, stage_changed: bool, *, replayed: bool) -> dict:
    return {
        "crm_status": crm_status,
        "remote_id": remote_id,
        "stage_changed": stage_changed,
        "closes_deal": False,
        "replayed": replayed,
    }


def insert_write_statement(*, operation_key: str, memo_id: str, proposal_id: str, remote_id: str, crm_status: str) -> str:
    return (
        "INSERT INTO meeting_writes (operation_key, memo_id, proposal_id, remote_id, crm_status, stage_changed) "
        f"VALUES ('{operation_key}', '{memo_id}', '{proposal_id}', '{remote_id}', '{crm_status}', FALSE) "
        "ON CONFLICT (operation_key) DO NOTHING;"
    )
