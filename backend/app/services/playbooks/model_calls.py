"""Model calls: transcripts of calls the Head of Sales marks as a good example ("así se hace").

Vocify reads one and proposes two kinds of things, each with the passage it comes from:
  step_example      a real sentence of the salesperson for a step of the playbook (the step's `example`);
  objection_branch  how an objection was handled and in which situation that worked, as a branch of the answer
                    ("… Si lo comparan con algo gratis: …").
Nothing is applied until the Head of Sales picks it, and the model is never trusted with a fact: a proposal whose
passage (or example) is not literally in the transcript is dropped, texts are clipped to the editor's limits, and a
branch that does not fit in the answer is skipped, not truncated.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.playbooks.fill import FillError
from app.services.playbooks.structure import _ask, _client, _fold, _literal_in, _text, timeout_for
from app.services.playbooks.structured import (
    CUSTOM_CATEGORY,
    MAX_CUSTOM_OBJECTIONS,
    MAX_EXAMPLE,
    MAX_GUIDANCE,
    MAX_OBJECTION_LABEL,
    OBJECTION_CATEGORIES,
    clip_text,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "model_call_extract_v1"
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / f"{PROMPT_VERSION}.md"
MAX_TRANSCRIPT_CHARS = 60_000
MAX_WHEN = 120
MAX_ANSWER = 400
MAX_EXCERPT_TEXT = 400
_SPEAKERS = ("rep", "client")
_LABELED_LINE = re.compile(r"^\s*(?:SPEAKER:\s*)?([^\W\d_][\w ]{0,23}|S\d+)\s*:\s+\S", re.IGNORECASE | re.MULTILINE)


@lru_cache(maxsize=1)
def _prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def speaker_warning(transcript: str) -> bool:
    """True when the transcript does not tell two speakers apart (one label or none): who said what cannot be trusted,
    and the Head of Sales is asked to confirm it before keeping anything."""
    labels = set()
    for line in (transcript or "").splitlines():
        match = _LABELED_LINE.match(line)
        if match:
            labels.add(match.group(1).strip().casefold())
    bare = {m.casefold() for m in re.findall(r"^\s*SPEAKER:\s*(S\d+)\s*$", transcript or "", re.IGNORECASE | re.MULTILINE)}
    return len(labels | bare) < 2


def _excerpt(raw: Any, folded: str) -> list[dict]:
    """The passage, or [] when it is empty or any part of it is not in the transcript."""
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            return []
        text = clip_text(" ".join(str(item.get("text") or "").split()), MAX_EXCERPT_TEXT)
        if not text or not _literal_in(text, folded):
            return []
        speaker = str(item.get("speaker") or "").lower()
        out.append({"speaker": speaker if speaker in _SPEAKERS else "unknown", "text": text})
    return out


def shape_proposals(raw: Any, transcript: str, current: dict) -> list[dict]:
    folded = _fold(transcript)
    steps = current.get("steps") or []
    proposals: list[dict] = []

    def add(proposal: dict) -> None:
        proposals.append({"id": f"p{len(proposals) + 1}", **proposal})

    data = raw if isinstance(raw, dict) else {}
    for item in data.get("step_examples") if isinstance(data.get("step_examples"), list) else []:
        if not isinstance(item, dict):
            continue
        index = item.get("step_index")
        example = " ".join(str(item.get("example") or "").split())
        passage = _excerpt(item.get("excerpt"), folded)
        if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= len(steps):
            continue
        if not example or not _literal_in(example, folded) or not passage:
            continue
        add({"kind": "step_example", "step_index": index, "text": clip_text(example, MAX_EXAMPLE), "excerpt": passage})
    for item in data.get("objection_branches") if isinstance(data.get("objection_branches"), list) else []:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip().lower()
        label = _text(item, "label", MAX_OBJECTION_LABEL)
        when, answer = _text(item, "when", MAX_WHEN), _text(item, "answer", MAX_ANSWER)
        passage = _excerpt(item.get("excerpt"), folded)
        valid = category in OBJECTION_CATEGORIES or (category == CUSTOM_CATEGORY and label)
        if not valid or not when or not answer or not passage:
            continue
        proposal = {"kind": "objection_branch", "category": category, "when": when, "text": answer, "excerpt": passage}
        if category == CUSTOM_CATEGORY:
            proposal["label"] = label
        add(proposal)
    return proposals


def _messages(transcript: str, scope: dict, note: str, current: dict, lang: str) -> list[dict]:
    steps = [
        {"step_index": i, "label": s.get("label"), "criterion": s.get("criterion")}
        for i, s in enumerate(current.get("steps") or [], start=1)
    ]
    objections = [
        {key: o.get(key) for key in ("category", "label", "trigger", "guidance") if o.get(key)}
        for o in current.get("objections") or []
    ]
    if scope.get("kind") == "moment":
        looking = f'Look at this moment of the call (the rest is context):\n"""\n{str(scope.get("text") or "")[:2000]}\n"""'
    else:
        looking = "Look at the whole call."
    user = (
        f"Company language: {'English' if lang == 'en' else 'Spanish'}\n\n{looking}\n\n"
        f"Note from the Head of Sales: {(note or '').strip()[:1000] or '(none)'}\n\n"
        f"Playbook steps:\n{json.dumps(steps, ensure_ascii=False)}\n\n"
        f"Objections the playbook already answers:\n{json.dumps(objections, ensure_ascii=False)}\n\n"
        f'Transcript:\n"""\n{transcript}\n"""'
    )
    return [{"role": "system", "content": _prompt()}, {"role": "user", "content": user}]


async def propose(transcript: str, scope: dict, note: str, current: dict, lang: str, *, llm: Any = None) -> dict:
    """-> {proposals: [...], speaker_warning: bool}. ValueError `empty_transcript` / `transcript_too_long`;
    FillError when the model fails (nothing is kept)."""
    text = (transcript or "").strip()
    if not text:
        raise ValueError("empty_transcript")
    if len(text) > MAX_TRANSCRIPT_CHARS:
        raise ValueError("transcript_too_long")
    timeout = timeout_for(text)
    try:
        raw = await asyncio.wait_for(_ask(_client(llm), _messages(text, scope or {}, note, current, lang), timeout), timeout + 5)
    except Exception as exc:
        logger.warning("model call not read: %s", type(exc).__name__)
        raise FillError("model") from exc
    return {"proposals": shape_proposals(raw, text, current), "speaker_warning": speaker_warning(text)}


def _branch(when: str, text: str) -> str:
    when = re.sub(r"^\s*si\s+", "", when.strip(), flags=re.IGNORECASE).rstrip(" .:;,")
    text = text.strip()
    if text and text[-1].isalnum():
        text += "."
    return f"Si {when}: {text}"


def apply_proposals(current: dict, proposals: list[dict]) -> dict:
    """The editor content with the chosen proposals applied -> {steps, objections, qualification, applied: [ids],
    skipped: [{id, code}]}. A step example replaces the step's; a branch is added to the end of the answer of its
    objection (created when the playbook has none). Whatever does not fit is skipped and changes nothing."""
    steps = [dict(step) for step in current.get("steps") or []]
    objections = [dict(item) for item in current.get("objections") or []]
    applied: list[str] = []
    skipped: list[dict] = []
    for proposal in proposals:
        pid = str(proposal.get("id") or "")
        kind = proposal.get("kind")
        if kind == "step_example":
            index = proposal.get("step_index")
            if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= len(steps):
                skipped.append({"id": pid, "code": "step_not_found"})
                continue
            steps[index - 1]["example"] = clip_text(str(proposal.get("text") or ""), MAX_EXAMPLE)
            applied.append(pid)
        elif kind == "objection_branch":
            code = _add_branch(objections, proposal)
            (skipped.append({"id": pid, "code": code}) if code else applied.append(pid))
        else:
            skipped.append({"id": pid, "code": "unsupported"})
    return {
        "steps": steps, "objections": objections, "qualification": list(current.get("qualification") or []),
        "applied": applied, "skipped": skipped,
    }


def _add_branch(objections: list[dict], proposal: dict) -> str | None:
    category = str(proposal.get("category") or "").lower()
    label = str(proposal.get("label") or "").strip()
    branch = _branch(str(proposal.get("when") or ""), str(proposal.get("text") or ""))
    if category == CUSTOM_CATEGORY:
        target = next(
            (o for o in objections if o.get("category") == CUSTOM_CATEGORY and str(o.get("label") or "").strip().casefold() == label.casefold()),
            None,
        )
    else:
        target = next((o for o in objections if o.get("category") == category), None)
    if target is None:
        if category == CUSTOM_CATEGORY and (not label or sum(1 for o in objections if o.get("category") == CUSTOM_CATEGORY) >= MAX_CUSTOM_OBJECTIONS):
            return "too_many_custom_objections" if label else "unsupported"
        if category != CUSTOM_CATEGORY and category not in OBJECTION_CATEGORIES:
            return "unsupported"
        if len(branch) > MAX_GUIDANCE:
            return "guidance_too_long"
        created = {"category": category, "guidance": branch}
        if category == CUSTOM_CATEGORY:
            created.update({"label": label[:MAX_OBJECTION_LABEL], "trigger": ""})
        objections.append(created)
        return None
    existing = str(target.get("guidance") or "").strip()
    if branch in existing:
        return "already_there"
    merged = f"{existing} {branch}".strip()
    if len(merged) > MAX_GUIDANCE:
        return "guidance_too_long"
    target["guidance"] = merged
    return None
