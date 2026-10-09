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

from app.services.playbooks.outcome_steps import STEP_OUTCOMES

import re
import unicodedata
from typing import Any, Iterable, Optional

# The objection categories C04 extracts (prompts/intelligence_v3.md). An answer keyed by
# anything else would never match an objection, so it is rejected, not silently kept.
OBJECTION_CATEGORIES: tuple[str, ...] = (
    "price", "timing", "authority", "competitor", "status_quo", "trust", "other",
)
# The company's own objections (three-layer model, section 15): `custom`, identified by a slug of
# their label (entry_id "objection:custom:<slug>"), with how the prospect says it in `trigger`.
CUSTOM_CATEGORY = "custom"
ENTRY_CATEGORIES: tuple[str, ...] = OBJECTION_CATEGORIES + (CUSTOM_CATEGORY,)

MAX_STEPS = 15
MAX_LABEL = 80
MAX_CRITERION = 400
MAX_EXAMPLE = 300
MAX_GUIDANCE = 600
MAX_CUSTOM_OBJECTIONS = 12
MAX_OBJECTION_LABEL = 60
MAX_TRIGGER = 200
MAX_CRITERIA = 8
MAX_CRITERION_LABEL = 60
MAX_CRITERION_TEXT = 200

_STEP_ID = re.compile(r"^[a-z0-9_]{1,40}$")


class PlaybookDraftError(ValueError):
    """code: no_steps | too_many_steps | empty_label | label_too_long | criterion_too_long |
    example_too_long | bad_step_id | duplicate_step_id | bad_category | guidance_too_long |
    duplicate_category | too_many_custom_objections | custom_objection_label_empty |
    too_many_criteria | criterion_label_empty | criterion_label_too_long | field_too_long.
    `field` names the offending field for field_too_long."""

    def __init__(self, code: str, *, index: Optional[int] = None, field: Optional[str] = None):
        self.code = code
        self.index = index
        self.field = field
        super().__init__(code if index is None else f"{code}@{index}")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def slug(label: str, default: str = "step") -> str:
    """"Descubrir el dolor" -> "descubrir_el_dolor" (ASCII, <=40 chars)."""
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return (text or default)[:40].strip("_") or default


def _unique_id(base: str, seen: set[str]) -> str:
    """`base`, or `base_2`, `base_3`... (still <= 40 chars) when it is taken."""
    candidate, n = base, 2
    while candidate in seen:
        suffix = f"_{n}"
        candidate = f"{base[: 40 - len(suffix)]}{suffix}"
        n += 1
    return candidate


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
        outcome = str(raw.get("outcome") or "").strip()
        if outcome in STEP_OUTCOMES:
            step["outcome"] = outcome
        out.append(step)
    if not out:
        raise PlaybookDraftError("no_steps")
    if len(out) > MAX_STEPS:
        raise PlaybookDraftError("too_many_steps")
    return out


def _entry_id_slug(entry_id: Any) -> str:
    """"objection:custom:pide_descuento" -> "pide_descuento" (the `id` the editor shows)."""
    parts = str(entry_id or "").split(":", 2)
    return parts[2] if len(parts) == 3 and parts[1] == CUSTOM_CATEGORY else ""


def normalize_objections(objections: Iterable[dict]) -> list[dict]:
    """The objection answers as stored entries. A fixed category keeps one entry (an empty
    answer is "not written yet", not an error) with an optional trigger (how the prospect says it).
    Anything else sent with it (the old meaning / question / proof) is dropped: an objection is what
    the prospect says, its kind and the answer. A
    `custom` one is the company's own objection: `label` required, `trigger` is how the
    prospect says it, and it is kept without an answer (Vocify can detect it before anyone
    wrote how to answer); at most MAX_CUSTOM_OBJECTIONS, its entry_id is a slug of the label
    (or of the `id` the editor sent back, so a renamed label keeps its identity), suffixed
    when two collide."""
    items = list(objections or [])
    if sum(1 for raw in items if isinstance(raw, dict) and str(raw.get("category") or "").strip().lower() == CUSTOM_CATEGORY) > MAX_CUSTOM_OBJECTIONS:
        raise PlaybookDraftError("too_many_custom_objections")
    out: list[dict] = []
    seen: set[str] = set()
    used_ids: set[str] = set()
    for index, raw in enumerate(items):
        raw = raw if isinstance(raw, dict) else {}
        category = str(raw.get("category") or "").strip().lower()
        guidance = _clean(raw.get("guidance"))
        if category == CUSTOM_CATEGORY:
            label = _clean(raw.get("label"))
            trigger = _clean(raw.get("trigger"))
            if not label:
                raise PlaybookDraftError("custom_objection_label_empty", index=index)
            for name, value, limit in (("label", label, MAX_OBJECTION_LABEL), ("trigger", trigger, MAX_TRIGGER)):
                if len(value) > limit:
                    raise PlaybookDraftError("field_too_long", index=index, field=name)
        else:
            if not guidance:
                continue  # an empty answer is "not written yet", not an error
            if category not in OBJECTION_CATEGORIES:
                raise PlaybookDraftError("bad_category", index=index)
            if category in seen:
                raise PlaybookDraftError("duplicate_category", index=index)
            # How the prospect says it ("Es muy caro para nosotros"), optional for a fixed category.
            trigger = _clean(raw.get("trigger"))
            if len(trigger) > MAX_TRIGGER:
                raise PlaybookDraftError("field_too_long", index=index, field="trigger")
        if len(guidance) > MAX_GUIDANCE:
            raise PlaybookDraftError("guidance_too_long", index=index)
        if category == CUSTOM_CATEGORY:
            given = str(raw.get("id") or "").strip()
            base = given if _STEP_ID.match(given) else slug(label, "custom")
            entry_id_slug = _unique_id(base, used_ids)
            used_ids.add(entry_id_slug)
            entry = {
                "entry_id": f"objection:{CUSTOM_CATEGORY}:{entry_id_slug}",
                "category": category,
                "label": label,
                "trigger": trigger,
                "guidance": guidance,
            }
        else:
            seen.add(category)
            entry = {"entry_id": f"objection:{category}", "category": category, "guidance": guidance}
            if trigger:
                entry["trigger"] = trigger
        entry["source_ref"] = "editor"
        out.append(entry)
    return out


def normalize_qualification(criteria: Optional[Iterable[dict]]) -> list[dict]:
    """"What has to come out of the call": [{criterion_id, label, good?}], at most
    MAX_CRITERIA. `criterion_id` is a stable slug (the one the editor sent back, else a slug of
    the label, suffixed when two collide), like a step's `step_id`. An empty list is valid."""
    items = list(criteria or [])
    if len(items) > MAX_CRITERIA:
        raise PlaybookDraftError("too_many_criteria")
    out: list[dict] = []
    used: set[str] = set()
    for index, raw in enumerate(items):
        raw = raw if isinstance(raw, dict) else {}
        label = _clean(raw.get("label"))
        if not label:
            raise PlaybookDraftError("criterion_label_empty", index=index)
        if len(label) > MAX_CRITERION_LABEL:
            raise PlaybookDraftError("criterion_label_too_long", index=index)
        # A criterion is what to find out and how a good answer sounds; older why / bad are dropped.
        texts = {"good": _clean(raw.get("good"))}
        for name, value in texts.items():
            if len(value) > MAX_CRITERION_TEXT:
                raise PlaybookDraftError("field_too_long", index=index, field=name)
        given = str(raw.get("criterion_id") or "").strip()
        base = given if _STEP_ID.match(given) else slug(label, "criterion")
        criterion_id = _unique_id(base, used)
        used.add(criterion_id)
        item = {"criterion_id": criterion_id, "label": label}
        item.update({name: value for name, value in texts.items() if value})
        out.append(item)
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
_MARKER = re.compile(r"^\s*(?:(?:paso|step)\s*)?(?:\d{1,2}[.)\-:]|[-•*·]|#{1,6})\s+", re.IGNORECASE)
_HEADING = re.compile(r"^\s*#{1,6}\s+")
_NUMBER = re.compile(r"^\s*(?:(?:paso|step)\s*)?\d{1,2}[.)\-:]\s+", re.IGNORECASE)
_BULLET = re.compile(r"^\s*[-•*·]\s+")
_SPLIT = re.compile(r"\s*(?::|—|–|\s-\s)\s*")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_EMPHASIS = re.compile(r"\*\*|__|`")
SHORT_LABEL = 60
# Words a cut label must not end on ("…equipo comercial activo y").
_DANGLING = frozenset(
    "y o e u de del con en a al para por que la el los las un una sin "
    "and or of with to for in on the a an that".split()
)


def strip_markdown(value: Any) -> str:
    """Bold and code marks a document (or a model copying it) carries: never shown in a step."""
    return _EMPHASIS.sub("", str(value or ""))


def _plain(line: str) -> str:
    return strip_markdown(line).lstrip("> ").rstrip()


def short_label(text: str) -> str:
    """The name of a step from a sentence: the first clause when the sentence is long, cut
    at a word boundary, never mid-word ("Priorizar startups B2B con SDRs")."""
    sentence = _SENTENCE_END.split(_clean(text))[0] if text else ""
    sentence = re.sub(r"[.!?:]+$", "", sentence).strip()
    if len(sentence) <= SHORT_LABEL:
        return sentence
    for mark in (", ", " (", "; ", " — ", " – "):
        at = sentence.find(mark)
        if 12 <= at <= SHORT_LABEL:
            return sentence[:at].strip()
    words = clip_text(sentence, SHORT_LABEL).split(" ")
    while len(words) > 1 and words[-1].casefold() in _DANGLING:
        words.pop()
    return " ".join(words)


def _clip_sentences(text: str, limit: int) -> str:
    """A long description keeps whole sentences when it has to be cut."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end >= limit * 0.5 else clip_text(text, limit)


def _step_from_line(line: str) -> dict:
    body = _clean(_MARKER.sub("", line, count=1))
    match = _SPLIT.search(body)
    if match and 0 < match.start() <= MAX_LABEL:
        label = _clean(body[: match.start()])
        criterion = _clean(body[match.end():])
        return {"label": label, "criterion": criterion or label}
    return {"label": short_label(body), "criterion": body}


def _join(previous: str, piece: str, item: bool) -> str:
    """Lines under a step become its description; each list item reads as its own sentence."""
    if not previous:
        return piece
    if item and not re.search(r"[.!?:;]$", previous):
        previous += "."
    return f"{previous} {piece}"


def _outline_steps(lines: list[str]) -> Optional[list[dict]]:
    """A document with an outline ("### 1. Elegir la cuenta" and bullets under it): the
    numbered headings are the steps and everything under one is its description. Headings
    without a number ("## Objetivo del rol") are context, not steps. None when the text has
    no outline, so the flat rules apply."""
    kinds = []
    for line in lines:
        heading = bool(_HEADING.match(line))
        body = _HEADING.sub("", line, count=1)
        numbered = bool(_NUMBER.match(body))
        kinds.append((heading, numbered, _clean(_NUMBER.sub("", body, count=1) if numbered else body)))

    def follows(index: int) -> bool:
        nxt = next((k for k in kinds[index + 1:] if k[2]), None)
        return nxt is not None and not nxt[1] and not nxt[0]

    if any(h and n for h, n, _ in kinds):
        is_step = lambda k: k[0] and k[1]  # noqa: E731
        closes = lambda k: k[0]  # noqa: E731
    elif sum(1 for h, _, b in kinds if h and b) >= 2 and any(not h and b for h, _, b in kinds):
        is_step = closes = lambda k: k[0]  # noqa: E731
    elif any(n and not h and b and not _SPLIT.search(b) and len(b) <= SHORT_LABEL and follows(i)
             for i, (h, n, b) in enumerate(kinds)):
        is_step = lambda k: k[1] and not k[0]  # noqa: E731
        closes = lambda k: k[0]  # noqa: E731
    else:
        return None

    steps: list[dict] = []
    current: Optional[dict] = None
    for raw, kind in zip(lines, kinds):
        if not kind[2]:
            continue
        if is_step(kind):
            label = re.sub(r"[:.]+$", "", kind[2]).strip()
            current = {"label": label if len(label) <= MAX_LABEL else short_label(label), "criterion": ""}
            steps.append(current)
        elif closes(kind):
            current = None
        elif current is not None:
            item = bool(_BULLET.match(raw) or _NUMBER.match(raw))
            piece = _clean(_MARKER.sub("", raw, count=1)) if item else kind[2]
            current["criterion"] = _join(current["criterion"], piece, item)
    # A title heading with nothing under it is not a step.
    steps = [s for s in steps if s["criterion"] or len(steps) == 1 or s is not steps[0]]
    for step in steps:
        step["criterion"] = _clip_sentences(step["criterion"], MAX_CRITERION) or step["label"]
    return steps


def parse_playbook_text(text: str) -> list[dict]:
    """Pasted process text -> [{label, criterion}]. An outline (numbered headings with lines
    under them) gives one step per heading. Otherwise numbered, bulleted or heading lines
    start a step ("1. Apertura: se presenta…", "- Cualificar — quién decide") and lines under
    one are added to its description; without any marker, each paragraph is a step. Markdown
    is dropped and long sentences get a short name. Never more than MAX_STEPS. Same behaviour
    as parsePlaybookText in the frontend."""
    source = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [_plain(line) for line in source.split("\n")]
    outline = _outline_steps(lines)
    if outline is not None:
        return [step for step in outline if step["label"]][:MAX_STEPS]
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
        for paragraph in re.split(r"\n\s*\n", "\n".join(lines)):
            if paragraph.strip():
                steps.append(_step_from_line(paragraph.strip()))
    return [step for step in steps if step["label"]][:MAX_STEPS]


def render_text(steps: list[dict], entries: list[dict], qualification: Optional[list[dict]] = None) -> str:
    """Plain-text copy kept with the draft's import row (audit, and the old draft.text)."""
    lines = [f"{i}. {step['label']}: {step['criterion']}" for i, step in enumerate(steps, start=1)]
    for entry in qualification or []:
        line = f"? {entry['label']}"
        if entry.get("good"):
            line += f" | good: {entry['good']}"
        lines.append(line)
    for entry in entries:
        if entry.get("category") == CUSTOM_CATEGORY:
            head = f"- custom \"{entry.get('label', '')}\""
            if entry.get("trigger"):
                head += f" ({entry['trigger']})"
            line = f"{head}: {entry['guidance']}" if entry.get("guidance") else head
        else:
            line = f"- {entry['category']}: {entry['guidance']}"
        lines.append(line)
    return "\n".join(lines)


def objection_view(entry: dict) -> dict:
    """A stored objection entry as the editor (and the AI flow) carries it: {category, guidance}
    plus `trigger` when set; a custom one also has `id` (its slug), `label` and always `trigger`.
    Older entries' meaning / question / proof are not carried, so the next save drops them."""
    category = str(entry.get("category")).lower()
    item: dict = {"category": category, "guidance": str(entry.get("guidance") or "")}
    if category == CUSTOM_CATEGORY:
        item["id"] = _entry_id_slug(entry.get("entry_id")) or slug(str(entry.get("label") or ""), "custom")
        item["label"] = str(entry.get("label") or "")
        item["trigger"] = str(entry.get("trigger") or "")
    elif entry.get("trigger"):
        item["trigger"] = str(entry["trigger"])
    return item


def qualification_view(items: Any) -> list[dict]:
    out = []
    for raw in items if isinstance(items, list) else []:
        if not isinstance(raw, dict) or not raw.get("criterion_id"):
            continue
        item = {"criterion_id": str(raw["criterion_id"]), "label": str(raw.get("label") or raw["criterion_id"])}
        if raw.get("good"):
            item["good"] = str(raw["good"])
        out.append(item)
    return out


def editor_view(version: Optional[dict]) -> dict:
    """A stored version as the editor shows it. Entries outside the objection categories
    (the legacy whole-document "process" entry) are not objection answers, so they are
    not shown as one."""
    if not version:
        return {"steps": [], "objections": [], "qualification": []}
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
        objection_view(entry)
        for entry in version.get("entries") or []
        if isinstance(entry, dict) and str(entry.get("category") or "").lower() in ENTRY_CATEGORIES
    ]
    return {"steps": steps, "objections": objections, "qualification": qualification_view(version.get("qualification"))}
