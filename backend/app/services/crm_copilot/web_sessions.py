"""Web Ask turns. Repeating a client turn id does not run the operation twice."""

from __future__ import annotations


class TurnConflict(Exception):
    pass


class UncertainOperation(Exception):
    pass


def accept_turn(store: dict, *, conversation_id: str, client_turn_id: str, text: str) -> dict:
    key = (conversation_id, client_turn_id)
    existing = store.get(key)
    if existing:
        return {**existing, "replayed": True}
    turn = {
        "conversation_id": conversation_id,
        "turn_id": f"turn-{len(store) + 1}",
        "status": "pending",
        "client_turn_id": client_turn_id,
        "text": text,
        "replayed": False,
    }
    store[key] = turn
    return turn


def confirm_operation(
    operation: dict,
    *,
    operation_id: str,
    revision: int,
    contact_id: str,
) -> dict:
    if operation.get("status") == "uncertain":
        raise UncertainOperation("reconciliar antes de repetir")
    if operation.get("operation_id") != operation_id or operation.get("revision") != revision:
        raise TurnConflict("operación o revisión distinta")
    if operation.get("contact_id") != contact_id:
        raise TurnConflict("el contacto cambió")
    if operation.get("applied"):
        return {**operation, "replayed": True}
    return {**operation, "applied": True, "status": "succeeded", "replayed": False}
