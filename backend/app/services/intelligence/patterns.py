"""Interaction patterns. A human note is evidence, not the prospect's words. An old revision does not count twice."""

from __future__ import annotations

CATEGORIES = {"price", "timing", "authority", "competitor", "status_quo", "trust", "other"}
KINDS = {"objection", "obstacle", "unknown"}
RESOLUTIONS = {"resolved", "open", "unknown"}


def pattern_from_situation(
    *,
    pattern_id: str,
    memo_id: str,
    input_revision: str,
    category: str,
    commercial_objection: bool | None,
    resolution: str | None,
    response: str | None = None,
    evidence_refs: list[str] | None = None,
) -> dict:
    if category not in CATEGORIES:
        category = "other"
    if commercial_objection is False:
        kind = "obstacle"
    elif commercial_objection is True:
        kind = "objection"
    else:
        kind = "unknown"
    if resolution not in RESOLUTIONS:
        resolution = "unknown"
    return {
        "pattern_id": pattern_id,
        "memo_id": memo_id,
        "input_revision": input_revision,
        "category": category,
        "kind": kind,
        "resolution": resolution,
        "response": response,
        "evidence_refs": list(evidence_refs or []),
        "superseded": False,
    }


def attribute_evidence(*, transcript_quotes: list[dict], note: dict | None, sources: dict[str, str]) -> dict:
    """A note can support the pattern. Its words are never a prospect quote."""
    refs = []
    prospect_quotes = []
    for item in transcript_quotes:
        source_id = item.get("source_id")
        quote = (item.get("quote") or "").strip()
        text = sources.get(source_id)
        if not quote or text is None or quote not in text:
            continue
        if item.get("source_type") == "human_note":
            continue
        refs.append(item["id"])
        prospect_quotes.append(quote)
    if note:
        refs.append(note["id"])
    return {"evidence_refs": refs, "prospect_quotes": prospect_quotes}


def apply_projection(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """The new revision replaces the previous frequency. Both rows stay."""
    incoming_revision = {(row["memo_id"], row["pattern_id"]): row["input_revision"] for row in incoming}
    kept = []
    for row in existing:
        key = (row["memo_id"], row["pattern_id"])
        if key in incoming_revision and row["input_revision"] != incoming_revision[key]:
            kept.append({**row, "superseded": True})
        else:
            kept.append(row)
    return kept + [{**row, "superseded": False} for row in incoming]


def frequency(rows: list[dict]) -> int:
    return sum(1 for row in rows if not row.get("superseded"))


def objection_view(*, notes: list[dict], patterns: list[dict], readable: bool) -> dict:
    """A failed read is not an empty analysis. A superseded row is not a current objection."""
    if not readable:
        return {"coverage": "unavailable", "patterns": [], "notes": []}
    active = [row for row in patterns if not row.get("superseded")]
    return {
        "coverage": "complete" if patterns else "unavailable",
        "patterns": [
            {
                "pattern_id": row["pattern_id"],
                "category": row.get("category"),
                "kind": row.get("kind"),
                "resolution": row.get("resolution"),
                "response": row.get("response"),
                "prospect_quotes": list(row.get("prospect_quotes") or []),
            }
            for row in active
        ],
        "notes": [
            {
                "annotation_id": row["annotation_id"],
                "text": row.get("text") or "",
                "offset_ms": row.get("offset_ms") or 0,
                "author_id": row.get("author_id"),
                "turn_id": row.get("turn_id"),
            }
            for row in notes
        ],
    }


def supersede_statement(*, memo_id: str, pattern_id: str, input_revision: str) -> str:
    return (
        "UPDATE interaction_patterns SET superseded = TRUE "
        f"WHERE memo_id = '{memo_id}' AND pattern_id = '{pattern_id}' "
        f"AND input_revision <> '{input_revision}';"
    )
