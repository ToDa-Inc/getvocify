"""The live call assistant's wire shape (spec 2026-10-16-live-call-assistant-design.md, "Backend: one brain").

The renderer holds the state and sends the part each producer needs; the producers are stateless. The same shape,
in the same snake_case names, is `shared/live-call/state.js`, which also merges results into the state. A change
here is a change there (`shared/live-call/example.json` is read by a test on each side).
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

# "deepen": an opportunity to go deeper on something important they said (say view only).
Kind = Literal["question", "objection", "deepen"]
Decision = Literal["responder", "reconducir", "aplazar", "cerrar"]
# How a point ends. "open" is not an end; "dismissed" is the rep's X and only the client writes it.
Outcome = Literal["open", "answered", "promised", "unanswered", "gone", "dismissed"]
# Why a reading happens: the checkpoint, or the rep asking.
# "rewrite": the same point from another angle of its source; "ask_step": a question for one pending step or data item.
Reason = Literal["turn_end", "long_turn", "rep_turn", "responder", "preguntar", "resumen", "rewrite", "ask_step"]
ASKED = frozenset({"responder", "preguntar", "resumen", "rewrite", "ask_step"})

MAX_TURNS = 400
MAX_POINTS = 24


class LiveTurn(BaseModel):
    id: str = Field(..., max_length=40)
    # "them" is the other side (on a meeting there may be several people: `name` says who), "you" is the rep.
    who: Literal["them", "you"]
    name: Optional[str] = Field(default=None, max_length=80)
    text: str = Field(..., max_length=4000)
    # Seconds into the call when the turn started.
    t: float = Field(default=0, ge=0)


class PointIn(BaseModel):
    """An open or recent point as the client holds it: enough to update it instead of duplicating it."""

    id: str = Field(..., max_length=64)
    kind: Kind = "question"
    tag_key: str = Field(default="question", max_length=200)
    title: str = Field(default="", max_length=300)
    turn_ids: list[Annotated[str, Field(max_length=40)]] = Field(default_factory=list, max_length=20)
    outcome: Outcome = "open"
    # What the rep was shown for it (the answer, or the honest line), so a new one is not the same line again.
    say: Optional[str] = Field(default=None, max_length=400)
    # Its source's id when it was answered from one (none: the point is not in the company's knowledge).
    source_id: Optional[str] = Field(default=None, max_length=200)
    # Every version the rep has seen, the first one first: a rewrite is never one of them again.
    versions: list[Annotated[str, Field(max_length=400)]] = Field(default_factory=list, max_length=8)


class NowIn(BaseModel):
    kind: Literal["step", "data", "goal"]
    id: str = Field(..., max_length=200)
    say: Optional[str] = Field(default=None, max_length=400)


class ProgressIn(BaseModel):
    """What the client already knows of the call against the playbook. The rep's marks are final."""

    done_steps: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=40)
    known_data: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=40)
    goal_reached: bool = False
    # Items the rep ticked by hand, or unticked: the brain neither reverses nor re-reads them.
    rep_ticked: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=60)
    rep_unticked: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=60)
    now: Optional[NowIn] = None
    missing: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=8)
    # The parts of a step already heard (step id -> part ids): a step with parts is done when `need` of them are.
    parts: dict[Annotated[str, Field(max_length=200)], list[Annotated[str, Field(max_length=80)]]] = Field(default_factory=dict, max_length=40)


class Target(BaseModel):
    """What an asked reading is about. rewrite: `point_id` and `version` (how many versions the rep has seen, 1 = only the
    first). ask_step: `kind` and `id` of a pending step or data item."""

    point_id: Optional[str] = Field(default=None, max_length=64)
    kind: Optional[Literal["step", "data"]] = None
    id: Optional[str] = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1, le=50)


class LiveReading(BaseModel):
    """One reading of either producer."""

    call_id: str = Field(..., max_length=128)
    call_mode: Literal["speakerphone", "softphone", "meeting"] = "meeting"
    language: Literal["auto", "en", "es"] = "auto"
    sales_motion_key: Optional[str] = Field(default=None, max_length=64)
    # The type's name as the rep sees it ("Llamada en frío"); only echoed back.
    type_label: Optional[str] = Field(default=None, max_length=120)
    contact_id: Optional[str] = Field(default=None, max_length=128)
    product_context: Optional[str] = Field(default=None, max_length=8000)
    reason: Reason = "turn_end"
    # The call so far: head and tail as the client keeps them. Turn ids are the identity of everything below.
    turns: list[LiveTurn] = Field(..., max_length=MAX_TURNS)
    # The turn where the reading window starts (an automatic check: from the previous one, with a little overlap;
    # Responder: about a minute before the tap). Turns before it are context.
    focus_from: Optional[str] = Field(default=None, max_length=40)
    # The state version the client read this from: echoed back, so a late result is merged by id, never over newer data.
    state_version: int = Field(default=0, ge=0)
    # The previous result's cursor: a reading whose words were all read already is skipped (asked readings never are).
    cursor: Optional[str] = Field(default=None, max_length=100)
    points: list[PointIn] = Field(default_factory=list, max_length=MAX_POINTS)
    progress: Optional[ProgressIn] = None
    # The type was changed in this call: everything is read again under the new playbook.
    type_changed: bool = False
    # The recap reads up to this turn (the moment of the tap); the end of `turns` when absent.
    up_to: Optional[str] = Field(default=None, max_length=40)
    target: Optional[Target] = None
    # The island draws the "Qué decir" view (LIVE_SAY_VIEW_ENABLED): enables the "go deeper" trigger.
    say_view: bool = False


class CardIn(BaseModel):
    """A card of the strategic producer the rep has seen: its words, when it appeared (seconds into the call, the
    producer's own `read_t`) and whether it is still on screen (the rep has not closed it and no card replaced it)."""

    id: str = Field(..., max_length=64)
    say: str = Field(..., max_length=400)
    visible_t: float = Field(..., ge=0)
    open: bool = True


class CardReading(LiveReading):
    """One reading of the strategic card producer (pilot, LIVE_CARD_ENABLED)."""

    # Every card shown in this call, oldest first: the thread of moves already made, and the one on screen.
    cards: list[CardIn] = Field(default_factory=list, max_length=60)
    # What the turn check saw in their latest turn ("none", an objection type or a playbook entry's id).
    objection: Optional[str] = Field(default=None, max_length=200)
    # The previous reading's `read_t`: a long intervention or a long rep floor is read once per stretch.
    last_read_t: Optional[float] = Field(default=None, ge=0)
