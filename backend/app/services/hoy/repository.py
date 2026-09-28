"""SQL for action_signals. Conflict does nothing, so two workers leave one row."""

from __future__ import annotations

import json

from app.services.hoy.signals import Signal


def _literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (dict, list)):
        return "'" + json.dumps(value, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    return "'" + str(value).replace("'", "''") + "'"


def insert_signal_statement(*, company_id: str, user_id: str, signal: Signal) -> str:
    payload = dict(signal.payload)
    return (
        "INSERT INTO action_signals "
        "(company_id, user_id, connection_id, contact_id, deal_id, memo_id, type, dedupe_key, payload, status) "
        "VALUES ("
        + ", ".join([
            _literal(company_id),
            _literal(user_id),
            _literal(signal.connection_id or ""),
            _literal(signal.contact_id),
            _literal(signal.deal_id),
            _literal(signal.source_memo_id),
            _literal(signal.type),
            _literal(signal.dedupe_key),
            _literal(payload),
            _literal("pending"),
        ])
        + ") ON CONFLICT (company_id, user_id, connection_id, dedupe_key) DO NOTHING;"
    )


def reopen_statement(*, company_id: str, user_id: str, connection_id: str, change: dict) -> str:
    return (
        "UPDATE action_signals SET status = 'pending', previous_status = 'snoozed', "
        f"version = {int(change['version'])}, payload = {_literal(change['payload'])}, updated_at = now() "
        f"WHERE company_id = {_literal(company_id)} AND user_id = {_literal(user_id)} "
        f"AND connection_id = {_literal(connection_id)} AND dedupe_key = {_literal(change['dedupe_key'])} "
        f"AND status = 'snoozed' AND version = {int(change['expected_version'])};"
    )


def transition_statement(
    *,
    signal_id: str,
    company_id: str,
    user_id: str,
    expected_version: int,
    request_id: str,
    status: str,
) -> str:
    return (
        "UPDATE action_signals SET "
        f"previous_status = status, status = {_literal(status)}, version = version + 1, "
        f"last_action_request_id = {_literal(request_id)}, "
        "last_action_at = now(), undo_deadline = now() + interval '5 seconds', updated_at = now() "
        f"WHERE id = {_literal(signal_id)} AND company_id = {_literal(company_id)} "
        f"AND user_id = {_literal(user_id)} AND version = {int(expected_version)};"
    )
