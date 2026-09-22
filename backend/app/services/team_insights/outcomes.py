"""Observed CRM outcomes. One deal counts once. Different currencies are not added."""

from __future__ import annotations

from decimal import Decimal


def observe_deal(
    *,
    connection_id: str,
    deal_id: str,
    status: str,
    owners: list[dict],
    amount: str | None,
    currency: str | None,
    closed_at: str | None,
    observed_at: str,
) -> dict:
    primaries = [owner for owner in owners if owner.get("primary")]
    if len(primaries) == 1:
        owner_user_id = primaries[0]["user_id"]
        attribution = "assigned"
    else:
        owner_user_id = None
        attribution = "unresolved"
    return {
        "connection_id": connection_id,
        "deal_id": deal_id,
        "status": status,
        "owner_user_id": owner_user_id,
        "attribution": attribution,
        "amount": amount,
        "currency": currency,
        "closed_at": closed_at,
        "observed_at": observed_at,
        "previous_status": None,
    }


def record_observation(history: list[dict], observation: dict, frozen_report: dict) -> list[dict]:
    """Append. Do not rewrite an older observation or a stored report."""
    history.append(dict(observation))
    frozen_report_copy = dict(frozen_report)
    if frozen_report_copy != frozen_report:
        raise RuntimeError("el informe persistido cambió")
    return history


def latest_observations(history: list[dict]) -> list[dict]:
    chosen: dict[tuple[str, str], dict] = {}
    for row in history:
        key = (row["connection_id"], row["deal_id"])
        current = chosen.get(key)
        if current is None or row["observed_at"] >= current["observed_at"]:
            chosen[key] = row
    return list(chosen.values())


def reconcile_wins(history: list[dict]) -> dict:
    rows = [row for row in latest_observations(history) if row["status"] == "won"]
    assigned = sum(1 for row in rows if row["attribution"] == "assigned")
    unresolved = sum(1 for row in rows if row["attribution"] == "unresolved")
    return {"won_deals": len(rows), "assigned": assigned, "unresolved": unresolved}


def amounts_by_currency(history: list[dict]) -> dict[str, str]:
    totals: dict[str, Decimal] = {}
    for row in latest_observations(history):
        if row["status"] != "won" or row.get("amount") is None or not row.get("currency"):
            continue
        totals[row["currency"]] = totals.get(row["currency"], Decimal("0")) + Decimal(row["amount"])
    return {currency: f"{amount:.2f}" for currency, amount in totals.items()}


def insert_observation_statement(*, company_id: str, observation: dict) -> str:
    owner = "NULL" if observation["owner_user_id"] is None else f"'{observation['owner_user_id']}'"
    amount = "NULL" if observation["amount"] is None else observation["amount"]
    currency = "NULL" if observation["currency"] is None else f"'{observation['currency']}'"
    closed = "NULL" if observation["closed_at"] is None else f"'{observation['closed_at']}'"
    return (
        "INSERT INTO team_outcome_observations "
        "(company_id, connection_id, deal_id, status, owner_user_id, attribution, amount, currency, closed_at, observed_at) "
        f"VALUES ('{company_id}', '{observation['connection_id']}', '{observation['deal_id']}', '{observation['status']}', "
        f"{owner}, '{observation['attribution']}', {amount}, {currency}, {closed}, '{observation['observed_at']}') "
        "ON CONFLICT (company_id, connection_id, deal_id, observed_at) DO NOTHING;"
    )
