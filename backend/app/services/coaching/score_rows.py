"""The one current score of a call. No I/O.

memo_scores keeps a row per transcript revision (memo_id, input_revision). Every reader takes the
same one: the highest revision_seq, then the latest written (a re-read of the same conversation,
e.g. a newer C04 prompt), then input_revision, so the choice never depends on the order the rows
came back in. Readers select memo_id, revision_seq, created_at and input_revision."""

from __future__ import annotations

from typing import Iterable


def score_rank(row: dict) -> tuple[int, str, str]:
    return (int(row.get("revision_seq") or 0), str(row.get("created_at") or ""), str(row.get("input_revision") or ""))


def current_score(rows: Iterable[dict]) -> dict | None:
    rows = [row for row in rows or [] if isinstance(row, dict)]
    return max(rows, key=score_rank) if rows else None


def current_scores(rows: Iterable[dict]) -> dict[str, dict]:
    """{memo_id: its current row}."""
    latest: dict[str, dict] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("memo_id"))
        held = latest.get(key)
        if held is None or score_rank(row) > score_rank(held):
            latest[key] = row
    return latest
