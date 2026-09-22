"""Meeting suggest grounding. Server validates evidence; clients never self-assert."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from app.services.playbooks.versions import get_published_playbook


@dataclass(frozen=True)
class SuggestGrounding:
    interaction_kind: str
    playbook_version_id: Optional[str]
    evidence_ids: frozenset[str]
    playbook_snapshot: Optional[dict] = None


def evidence_ids_from_memo_row(row: dict) -> frozenset[str]:
    extraction = row.get("extraction")
    if isinstance(extraction, str):
        try:
            extraction = json.loads(extraction)
        except json.JSONDecodeError:
            extraction = {}
    if not isinstance(extraction, dict):
        extraction = {}
    intel = extraction.get("intelligence")
    if not isinstance(intel, dict):
        intel = row.get("intelligence") if isinstance(row.get("intelligence"), dict) else {}
    ids: set[str] = set()
    for item in intel.get("evidence") or []:
        if isinstance(item, dict):
            ref = str(item.get("id") or "").strip()
            if ref:
                ids.add(ref)
    return frozenset(ids)


def resolve_suggest_grounding(
    row: dict,
    *,
    playbook: Optional[dict] = None,
    versions: Optional[list[dict]] = None,
) -> Optional[SuggestGrounding]:
    kind = str(row.get("interaction_kind") or "").strip().lower()
    if kind != "meeting":
        return SuggestGrounding(
            interaction_kind=kind or "call",
            playbook_version_id=None,
            evidence_ids=evidence_ids_from_memo_row(row),
            playbook_snapshot=None,
        )
    version_id = str(row.get("playbook_version_id") or "").strip() or None
    snapshot = None
    if playbook and versions and version_id:
        snapshot = get_published_playbook(playbook, versions, version_id=version_id)
        if snapshot is None:
            version_id = None
    elif version_id and not (playbook and versions):
        snapshot = {"version_id": version_id}
    return SuggestGrounding(
        interaction_kind="meeting",
        playbook_version_id=version_id if snapshot else None,
        evidence_ids=evidence_ids_from_memo_row(row),
        playbook_snapshot=snapshot,
    )


def _cited_evidence_refs(suggestion: dict[str, Any]) -> list[str]:
    raw = suggestion.get("evidence_refs")
    if not isinstance(raw, list):
        return []
    refs: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            refs.append(text)
    return refs


def _strip_advice(suggestion: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(suggestion)
    cleaned["say_this"] = ""
    cleaned["why_it_works"] = ""
    cleaned["next_question"] = ""
    cleaned["dont_say"] = ""
    return cleaned


def finalize_suggest_result(
    *,
    call_mode: str,
    suggestion: dict[str, Any],
    grounding: Optional[SuggestGrounding] = None,
) -> dict[str, Any]:
    """
    Attach playbook_ready / evidence_refs to a suggest result.
    Non-meeting modes never ship advice-looking card text for live assist.
    """
    mode = (call_mode or "speakerphone").strip().lower()
    cited = _cited_evidence_refs(suggestion)

    if mode != "meeting":
        return {
            "suggestion": _strip_advice(suggestion),
            "playbook_ready": False,
            "evidence_refs": [],
            "grounded": False,
            "playbook_version_id": None,
        }

    if grounding is None:
        return {
            "suggestion": dict(suggestion),
            "playbook_ready": False,
            "evidence_refs": [],
            "grounded": False,
            "playbook_version_id": None,
        }

    allowed = grounding.evidence_ids
    evidence_refs = [ref for ref in cited if ref in allowed]
    used_playbook = bool(grounding.playbook_version_id and grounding.playbook_snapshot)
    playbook_ready = used_playbook and bool(evidence_refs)

    if not playbook_ready:
        return {
            "suggestion": _strip_advice(suggestion),
            "playbook_ready": False,
            "evidence_refs": [],
            "grounded": False,
            "playbook_version_id": None,
        }

    out = dict(suggestion)
    source_id = str(out.get("source_id") or "").strip() or None
    entries = grounding.playbook_snapshot.get("entries") or []
    if entries and source_id:
        entry_ids = {str(entry.get("entry_id") or "").strip() for entry in entries if isinstance(entry, dict)}
        if source_id not in entry_ids:
            return {
                "suggestion": _strip_advice(suggestion),
                "playbook_ready": False,
                "evidence_refs": [],
                "grounded": False,
                "playbook_version_id": None,
            }

    return {
        "suggestion": out,
        "playbook_ready": True,
        "evidence_refs": evidence_refs,
        "grounded": True,
        "playbook_version_id": grounding.playbook_version_id,
    }
