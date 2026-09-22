"""Apply accept / omit / correct to the stored meeting proposal."""

from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import HTTPException, status

from app.services.crm_providers.errors import AmbiguousPrimaryCRMError
from app.services.crm_providers.resolve import resolve_sync_connection_for_company
from app.services.meetings.crm_writer import writer_from_connection
from app.services.meetings.proposals import latest_proposal
from app.services.meetings.writes import MeetingWriteError, register_meeting

WriterFactory = Callable[[Optional[dict[str, Any]], dict[str, Any], dict[str, Any]], Any]

_DECISION_STORED = {
    "accept": "accepted",
    "omit": "omitted",
    "corrected": "corrected",
}


class _UnusedWriter:
    def create(self, *_args, **_kwargs):
        raise AssertionError("CRM create must not run")

    def reconcile(self, _operation_key: str):
        return None

    def change_stage(self, _mapping: str) -> None:
        return None


def operation_key(*, memo_id: str, proposal_id: str, input_revision: str) -> str:
    return f"{memo_id}:{proposal_id}:{input_revision}"


def reconcile_meeting_proposal(
    supabase,
    *,
    company_id: str,
    memo_id: str,
    proposal_id: str,
    writer_factory: WriterFactory | None = None,
) -> dict:
    memo_rows = supabase.table("memos").select("id,company_id,hubspot_contact_id,hubspot_deal_id,matched_deal_id").eq("id", memo_id).execute()
    memo = (memo_rows.data or [None])[0]
    if not memo or memo.get("company_id") != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo no encontrado")

    proposal_rows = (
        supabase.table("meeting_proposals")
        .select("*")
        .eq("memo_id", memo_id)
        .execute()
    ).data or []
    matches = [row for row in proposal_rows if row.get("proposal_id") == proposal_id]
    if not matches:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propuesta no encontrada")
    row = max(matches, key=lambda item: str(item.get("created_at") or item.get("input_revision") or ""))

    op_key = operation_key(memo_id=memo_id, proposal_id=proposal_id, input_revision=str(row["input_revision"]))
    write_rows = (
        supabase.table("meeting_writes")
        .select("*")
        .eq("operation_key", op_key)
        .limit(1)
        .execute()
    ).data or []
    existing_write = write_rows[0] if write_rows else None

    remote_id = (existing_write or row).get("remote_id")
    crm_status = (existing_write or row).get("crm_status") or "not_requested"
    replayed = False

    if remote_id:
        crm_status = "succeeded"
        replayed = True
    elif crm_status == "succeeded":
        replayed = True
    elif crm_status == "uncertain":
        connection = _resolve_connection(supabase, company_id)
        writer = _build_writer(writer_factory, connection, memo, row)
        if writer is None:
            crm_status = "uncertain"
            remote_id = None
        else:
            found = writer.reconcile(op_key)
            if found:
                crm_status = "succeeded"
                remote_id = found
                replayed = True
                _persist_write(
                    supabase,
                    operation_key=op_key,
                    memo_id=memo_id,
                    proposal_id=proposal_id,
                    result={"crm_status": crm_status, "remote_id": remote_id, "stage_changed": False},
                )
            else:
                crm_status = "uncertain"
                remote_id = None

    update = {"crm_status": crm_status, "remote_id": remote_id}
    (
        supabase.table("meeting_proposals")
        .update(update)
        .eq("memo_id", memo_id)
        .eq("proposal_id", proposal_id)
        .eq("input_revision", row["input_revision"])
        .execute()
    )

    row = {**row, **update}
    return {
        "proposal": latest_proposal([row]),
        "crm_status": crm_status,
        "remote_id": remote_id,
        "replayed": replayed,
    }


def accept_meeting_proposal(
    supabase,
    *,
    company_id: str,
    memo_id: str,
    decision: str,
    proposal_id: str,
    starts_at: str | None = None,
    writer_factory: WriterFactory | None = None,
) -> dict:
    memo_rows = supabase.table("memos").select("id,company_id,hubspot_contact_id,hubspot_deal_id,matched_deal_id").eq("id", memo_id).execute()
    memo = (memo_rows.data or [None])[0]
    if not memo or memo.get("company_id") != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memo no encontrado")

    proposal_rows = (
        supabase.table("meeting_proposals")
        .select("*")
        .eq("memo_id", memo_id)
        .execute()
    ).data or []
    matches = [row for row in proposal_rows if row.get("proposal_id") == proposal_id]
    if not matches:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propuesta no encontrada")
    row = max(matches, key=lambda item: str(item.get("created_at") or item.get("input_revision") or ""))

    op_key = operation_key(memo_id=memo_id, proposal_id=proposal_id, input_revision=str(row["input_revision"]))
    write_rows = (
        supabase.table("meeting_writes")
        .select("*")
        .eq("operation_key", op_key)
        .limit(1)
        .execute()
    ).data or []
    existing_write = write_rows[0] if write_rows else None
    existing = None
    if existing_write:
        existing = {
            "remote_id": existing_write.get("remote_id"),
            "crm_status": existing_write.get("crm_status"),
        }

    effective_starts = starts_at if decision == "corrected" else row.get("starts_at")
    proposal_payload = {
        "proposal_id": row.get("proposal_id"),
        "agreement": row.get("agreement"),
        "starts_at": effective_starts,
        "timezone": row.get("timezone"),
        "precision": row.get("precision"),
        "needs_review": row.get("agreement") != "agreed" or not effective_starts,
    }

    if decision == "omit":
        result = register_meeting(
            proposal=proposal_payload,
            decision="omit",
            operation_key=op_key,
            writer=_UnusedWriter(),
            stage_mapping=None,
            existing=existing,
        )
    else:
        connection = _resolve_connection(supabase, company_id)
        writer = _build_writer(writer_factory, connection, memo, row)
        if writer is None:
            try:
                _validate_decision(proposal_payload, decision=decision, starts_at=starts_at)
            except MeetingWriteError as exc:
                raise _http_from_write_error(exc) from exc
            result = {
                "crm_status": "not_requested",
                "remote_id": None,
                "stage_changed": False,
                "replayed": False,
            }
        else:
            try:
                result = register_meeting(
                    proposal=proposal_payload,
                    decision=decision,
                    operation_key=op_key,
                    writer=writer,
                    stage_mapping=None,
                    existing=existing,
                    starts_at=starts_at,
                )
            except MeetingWriteError as exc:
                raise _http_from_write_error(exc) from exc
            if decision in {"accept", "corrected"}:
                _persist_write(
                    supabase,
                    operation_key=op_key,
                    memo_id=memo_id,
                    proposal_id=proposal_id,
                    result=result,
                )

    stored_decision = _DECISION_STORED[decision]
    update = {
        "decision": stored_decision,
        "crm_status": result["crm_status"],
        "remote_id": result.get("remote_id"),
    }
    if decision == "corrected" and starts_at:
        update["starts_at"] = starts_at

    (
        supabase.table("meeting_proposals")
        .update(update)
        .eq("memo_id", memo_id)
        .eq("proposal_id", proposal_id)
        .eq("input_revision", row["input_revision"])
        .execute()
    )

    row = {**row, **update}
    view = latest_proposal([row])
    return {
        "proposal": view,
        "crm_status": result["crm_status"],
        "remote_id": result.get("remote_id"),
        "replayed": result.get("replayed", False),
    }


def _resolve_connection(supabase, company_id: str) -> Optional[dict[str, Any]]:
    try:
        return resolve_sync_connection_for_company(supabase, company_id)
    except AmbiguousPrimaryCRMError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _build_writer(
    writer_factory: WriterFactory | None,
    connection: Optional[dict[str, Any]],
    memo: dict[str, Any],
    proposal_row: dict[str, Any],
):
    if writer_factory is not None:
        return writer_factory(connection, memo, proposal_row)
    if not connection:
        return None
    deal_id = memo.get("hubspot_deal_id") or memo.get("matched_deal_id")
    contact_id = memo.get("hubspot_contact_id")
    person_id = contact_id if (connection.get("provider") or "").lower() == "pipedrive" else None
    return writer_from_connection(
        connection,
        contact_id=str(contact_id) if contact_id else None,
        deal_id=str(deal_id) if deal_id else None,
        person_id=str(person_id) if person_id else None,
    )


def _persist_write(supabase, *, operation_key: str, memo_id: str, proposal_id: str, result: dict) -> None:
    payload = {
        "operation_key": operation_key,
        "memo_id": memo_id,
        "proposal_id": proposal_id,
        "remote_id": result.get("remote_id"),
        "crm_status": result["crm_status"],
        "stage_changed": bool(result.get("stage_changed")),
    }
    supabase.table("meeting_writes").upsert(payload, on_conflict="operation_key").execute()


def _validate_decision(proposal: dict, *, decision: str, starts_at: str | None) -> None:
    if decision not in {"accept", "corrected"}:
        raise MeetingWriteError("invalid")
    if decision == "accept" and (
        proposal.get("needs_review")
        or proposal.get("precision") == "ambiguous"
        or not proposal.get("starts_at")
    ):
        raise MeetingWriteError("needs_correction")
    if decision == "corrected" and not starts_at:
        raise MeetingWriteError("needs_correction")


def _http_from_write_error(exc: MeetingWriteError) -> HTTPException:
    if exc.code == "needs_correction":
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La propuesta necesita corrección")
    if exc.code == "invalid":
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Decisión no válida")
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error al escribir en el CRM")
