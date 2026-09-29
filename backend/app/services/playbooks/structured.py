"""A playbook as steps and objection answers, edited directly by the Head of Sales.

Every coaching surface reads a published version's `steps` ({step_id, label, criterion})
and `entries` ({category, guidance}): C04 labels each step met/missed, scoring and the
post-call brief name the missed steps, the pre-call brief and Team read the answer for an
objection category, the live checklist lists the steps. A pasted text used to become a
single step holding the whole document, so none of that could work from the UI. This
module is the one place that turns an edited playbook into that shape, deterministically
(no model call, nothing to eval).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Optional

# The objection categories C04 extracts (prompts/intelligence_v3.md). An answer keyed by
# anything else would never match an objection, so it is rejected, not silently kept.
OBJECTION_CATEGORIES: tuple[str, ...] = (
    "price", "timing", "authority", "competitor", "status_quo", "trust", "other",
)

MAX_STEPS = 15
MAX_LABEL = 80
MAX_CRITERION = 400
MAX_EXAMPLE = 300
MAX_GUIDANCE = 600

_STEP_ID = re.compile(r"^[a-z0-9_]{1,40}$")


class PlaybookDraftError(ValueError):
    """code: no_steps | too_many_steps | empty_label | label_too_long | criterion_too_long |
    example_too_long | bad_step_id | duplicate_step_id | bad_category | guidance_too_long |
    duplicate_category."""

    def __init__(self, code: str, *, index: Optional[int] = None):
        self.code = code
        self.index = index
        super().__init__(code if index is None else f"{code}@{index}")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def slug(label: str) -> str:
    """"Descubrir el dolor" -> "descubrir_el_dolor" (ASCII, <=40 chars)."""
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return (text or "step")[:40].strip("_") or "step"


def normalize_steps(steps: Iterable[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for index, raw in enumerate(list(steps or [])):
        raw = raw if isinstance(raw, dict) else {}
        label = _clean(raw.get("label"))
        criterion = " ".join(str(raw.get("criterion") or "").split())
        example = " ".join(str(raw.get("example") or "").split())
        if not label:
            raise PlaybookDraftError("empty_label", index=index)
        if len(label) > MAX_LABEL:
            raise PlaybookDraftError("label_too_long", index=index)
        if len(criterion) > MAX_CRITERION:
            raise PlaybookDraftError("criterion_too_long", index=index)
        if len(example) > MAX_EXAMPLE:
            raise PlaybookDraftError("example_too_long", index=index)
        given = str(raw.get("step_id") or "").strip()
        if given and not _STEP_ID.match(given):
            raise PlaybookDraftError("bad_step_id", index=index)
        if given and given in seen:
            raise PlaybookDraftError("duplicate_step_id", index=index)
        step_id = given or slug(label)
        if not given:
            base, n = step_id, 2
            while step_id in seen:
                suffix = f"_{n}"
                step_id = f"{base[: 40 - len(suffix)]}{suffix}"
                n += 1
        seen.add(step_id)
        step = {"step_id": step_id, "label": label, "criterion": criterion or label}
        if example:
            step["example"] = example
        out.append(step)
    if not out:
        raise PlaybookDraftError("no_steps")
    if len(out) > MAX_STEPS:
        raise PlaybookDraftError("too_many_steps")
    return out


def normalize_objections(objections: Iterable[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for index, raw in enumerate(list(objections or [])):
        raw = raw if isinstance(raw, dict) else {}
        category = str(raw.get("category") or "").strip().lower()
        guidance = " ".join(str(raw.get("guidance") or "").split())
        if not guidance:
            continue  # an empty answer is "not written yet", not an error
        if category not in OBJECTION_CATEGORIES:
            raise PlaybookDraftError("bad_category", index=index)
        if category in seen:
            raise PlaybookDraftError("duplicate_category", index=index)
        if len(guidance) > MAX_GUIDANCE:
            raise PlaybookDraftError("guidance_too_long", index=index)
        seen.add(category)
        out.append({
            "entry_id": f"objection:{category}",
            "category": category,
            "guidance": guidance,
            "source_ref": "editor",
        })
    return out


def clip_text(value: Any, limit: int) -> str:
    """Whitespace-tidied text cut to `limit` characters at a word boundary. The AI flow
    clips what the model wrote instead of rejecting it: a 90-character label is still a
    usable label, an error is not."""
    text = _clean(value)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space >= limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:-—–")


# Port of parsePlaybookText (src/lib/playbook-editor.ts): the deterministic parser the
# structuring flow falls back to when the model is down. Keep both in step.
_MARKER = re.compile(r"^\s*(?:(?:paso|step)\s*)?(?:\d{1,2}[.)\-:]|[-•*·]|#{1,4})\s+", re.IGNORECASE)
_SPLIT = re.compile(r"\s*(?::|—|–|\s-\s)\s*")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _step_from_line(line: str) -> dict:
    body = _MARKER.sub("", line, count=1).strip()
    match = _SPLIT.search(body)
    if match and 0 < match.start() <= MAX_LABEL:
        label = _clean(body[: match.start()])
        criterion = _clean(body[match.end():])
        return {"label": label, "criterion": criterion or label}
    sentence = _SENTENCE_END.split(body)[0] if body else body
    label = re.sub(r"[.!?]+$", "", _clean(sentence))[:MAX_LABEL].strip()
    return {"label": label, "criterion": _clean(body)}


def parse_playbook_text(text: str) -> list[dict]:
    """Pasted process text -> [{label, criterion}]. Numbered, bulleted or heading lines
    start a step ("1. Apertura: se presenta…", "- Cualificar — quién decide"); lines under
    one are added to its description. Without any marker, each paragraph is a step. Never
    more than MAX_STEPS. Same behaviour as parsePlaybookText in the frontend."""
    source = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    steps: list[dict] = []
    if any(_MARKER.match(line) for line in lines):
        for raw in lines:
            line = raw.strip()
            if not line:
                continue
            if _MARKER.match(raw):
                steps.append(_step_from_line(line))
            elif steps:
                last = steps[-1]
                previous = "" if last["criterion"] == last["label"] else last["criterion"]
                last["criterion"] = _clean(f"{previous} {line}")
    else:
        for paragraph in re.split(r"\n\s*\n", source):
            if paragraph.strip():
                steps.append(_step_from_line(paragraph.strip()))
    return [step for step in steps if step["label"]][:MAX_STEPS]


def render_text(steps: list[dict], entries: list[dict]) -> str:
    """Plain-text copy kept with the draft's import row (audit, and the old draft.text)."""
    lines = [f"{i}. {step['label']}: {step['criterion']}" for i, step in enumerate(steps, start=1)]
    for entry in entries:
        lines.append(f"- {entry['category']}: {entry['guidance']}")
    return "\n".join(lines)


def editor_view(version: Optional[dict]) -> dict:
    """A stored version as the editor shows it. Entries outside the objection categories
    (the legacy whole-document "process" entry) are not objection answers, so they are
    not shown as one."""
    if not version:
        return {"steps": [], "objections": []}
    steps = []
    for step in version.get("steps") or []:
        if not isinstance(step, dict) or not step.get("step_id"):
            continue
        item = {
            "step_id": str(step["step_id"]),
            "label": str(step.get("label") or step["step_id"]),
            "criterion": str(step.get("criterion") or ""),
        }
        if step.get("example"):
            item["example"] = str(step["example"])
        steps.append(item)
    objections = [
        {"category": str(entry.get("category")), "guidance": str(entry.get("guidance") or "")}
        for entry in version.get("entries") or []
        if isinstance(entry, dict) and str(entry.get("category") or "").lower() in OBJECTION_CATEGORIES
    ]
    return {"steps": steps, "objections": objections}
