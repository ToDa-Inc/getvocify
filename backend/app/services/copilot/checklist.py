"""Meeting playbook checklist from capture extraction — never from elapsed time or client guesses."""

from __future__ import annotations

import json
from typing import Any, Optional

from supabase import Client

from app.services.copilot.grounding import SuggestGrounding
from app.services.copilot.load_grounding import (
    load_company_suggest_grounding,
    load_owned_capture_memo,
    suggest_grounding_from_memo_row,
)

EMPTY_CHECKLIST: dict[str, Any] = {
    "playbook_version_id": None,
    "observed": 0,
    "applicable": 0,
    "steps": [],
}


def _empty_checklist() -> dict[str, Any]:
    return dict(EMPTY_CHECKLIST)


def _parse_extraction(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _playbook_observations_by_step(extraction: dict[str, Any]) -> dict[str, dict[str, Any]]:
    intel = extraction.get("intelligence")
    if not isinstance(intel, dict):
        intel = {}
    observations = intel.get("playbook_observations")
    if not isinstance(observations, list):
        fallback = extraction.get("playbook_observations")
        observations = fallback if isinstance(fallback, list) else []
    by_step: dict[str, dict[str, Any]] = {}
    for item in observations:
        if not isinstance(item, dict):
            continue
        step_id = str(item.get("step_id") or "").strip()
        if step_id:
            by_step[step_id] = item
    return by_step


def _non_empty_evidence_refs(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    refs: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            refs.append(text)
    return refs


def checklist_from_grounding(
    grounding: Optional[SuggestGrounding],
    *,
    extraction: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if grounding is None or not grounding.playbook_snapshot:
        return _empty_checklist()
    snapshot = grounding.playbook_snapshot
    version_id = str(grounding.playbook_version_id or snapshot.get("version_id") or "").strip() or None
    raw_steps = snapshot.get("steps") or []
    if not isinstance(raw_steps, list):
        raw_steps = []
    obs_by_step = _playbook_observations_by_step(extraction or {})
    steps_out: list[dict[str, Any]] = []
    observed = 0
    for step in raw_steps:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("step_id") or "").strip()
        if not step_id:
            continue
        label = str(step.get("label") or step_id).strip() or step_id
        observation = obs_by_step.get(step_id) or {}
        status_raw = str(observation.get("status") or "").strip().lower()
        evidence_refs = _non_empty_evidence_refs(observation.get("evidence_refs"))
        if status_raw == "met" and evidence_refs:
            status = "met"
            observed += 1
        else:
            status = "pending"
            evidence_refs = []
        steps_out.append(
            {
                "step_id": step_id,
                "label": label,
                "status": status,
                "evidence_refs": evidence_refs,
            }
        )
    return {
        "playbook_version_id": version_id,
        "observed": observed,
        "applicable": len(steps_out),
        "steps": steps_out,
    }


def build_meeting_checklist(
    supabase: Client,
    *,
    user_id: str,
    company_id: str,
    call_mode: str,
    capture_id: Optional[str] = None,
) -> dict[str, Any]:
    mode = (call_mode or "speakerphone").strip().lower()
    if mode != "meeting":
        return _empty_checklist()

    if capture_id:
        row = load_owned_capture_memo(
            supabase,
            user_id=user_id,
            company_id=company_id,
            capture_id=capture_id,
        )
        grounding = suggest_grounding_from_memo_row(supabase, company_id=company_id, row=row)
        extraction = _parse_extraction(row.get("extraction"))
        return checklist_from_grounding(grounding, extraction=extraction)

    grounding = load_company_suggest_grounding(
        supabase,
        company_id=company_id,
        call_mode="meeting",
    )
    return checklist_from_grounding(grounding, extraction={})
