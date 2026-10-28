"""Semantic turns: who holds the floor and where an idea ends, not every change of speaker.

A transcript splits speech at every change of voice, so «Mhm», «claro» or «sí, eso es» said while the other person keeps
talking look like turns. They are listening signals: the person speaking still holds the floor and their idea goes on.
Readings that start at such a split answer half an idea, and a rep's «claro» is not a reply.

- `backchannel(text)`: only acknowledgement words, short. A listening signal, never a turn of its own.
- `floors(turns)`: the call as stretches where one side holds the floor, listening signals of the other side inside.
- `idea_ends(turns, finished)`: the moments where the other side has finished an idea, as known live: they paused with a
  complete thought (the turn check's `finished`, the classifier production asks at every pause) or the rep really took
  the floor. The classifier catches a sentence cut short («el problema es que...»); it calls «Mhm» finished, which is
  why listening signals are found here, in code.
- `speaking_at(turns, t)`: whether the other side is talking at a moment (a card does not appear over them).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from evals.strategic.run import ends

# Words that only acknowledge (Spanish and the English that slips into these calls).
ACK = {
    "mhm", "mm", "mmm", "hmm", "hm", "ajá", "aja", "ah", "eh", "oh", "uh", "uh-huh", "ok", "okay", "vale", "sí", "si",
    "claro", "total", "exacto", "exactamente", "eso", "es", "correcto", "efectivamente", "cierto", "verdad", "ya", "bien",
    "perfecto", "genial", "entiendo", "entendido", "vaya", "ostras", "guay", "venga", "bueno", "pues", "y", "que",
    "tanto", "obvio", "seguro", "yeah", "yes", "right", "sure",
}
BACKCHANNEL_MAX_WORDS = 5


def tokens(text: str) -> list[str]:
    return [w for w in re.split(r"[\s,.;:¿?¡!…\-]+", text.lower()) if w]


def backchannel(text: str) -> bool:
    """«Mhm», «claro, claro», «sí, eso es», «vale, perfecto»: only acknowledgement, at most BACKCHANNEL_MAX_WORDS words."""
    ws = tokens(text)
    return 0 < len(ws) <= BACKCHANNEL_MAX_WORDS and all(w in ACK for w in ws)


def substance(text: str) -> int:
    """Words that are not acknowledgement: what makes a reply a reply."""
    return sum(1 for w in tokens(text) if w not in ACK)


SIGNAL_MAX_WORDS, SIGNAL_MAX_SUBSTANCE = 6, 3


def signal_like(text: str) -> bool:
    """A backchannel, or a fragment too short to take the floor («Sí. Yo claro», «te», «sí, ya está, poco más»).
    A question never is: «¿Cuántos sois?» takes the floor however short."""
    if "?" in text:
        return False
    return backchannel(text) or (len(tokens(text)) <= SIGNAL_MAX_WORDS and substance(text) <= SIGNAL_MAX_SUBSTANCE)


def listening(turns: list[dict]) -> set[int]:
    """Indexes of turns that are a listening signal: a backchannel or a short fragment said while the other side holds
    the floor (their speech comes right before it and, if the call goes on, right after it). A «vale» followed by its own
    speaker going on is the start of a turn, not a signal."""
    out = set()
    for i, t in enumerate(turns):
        if not signal_like(t["text"]):
            continue
        before = next((u for u in reversed(turns[:i]) if not signal_like(u["text"])), None)
        after = next((u for u in turns[i + 1:] if not signal_like(u["text"])), None)
        # What it does, not which word it is: the other side speaks right after it, even a fragment («¿Se podría…» —
        # «Dime» — «llamar» — «…desde Vocify?»), so it invited them to go on rather than took the floor.
        right_after = turns[i + 1] if i + 1 < len(turns) else None
        if before and before["who"] != t["who"] and (after is None or after["who"] != t["who"]
                                                     or (right_after is not None and right_after["who"] != t["who"])):
            out.add(i)
    return out


def floors(turns: list[dict]) -> list[dict]:
    """Stretches where one side holds the floor: {who, first, last (indexes), signals (indexes of the other side's
    listening signals inside)}."""
    signals = listening(turns)
    out: list[dict] = []
    for i, t in enumerate(turns):
        if i in signals:
            if out:
                out[-1]["signals"].append(i)
            continue
        if out and out[-1]["who"] == t["who"]:
            out[-1]["last"] = i
        else:
            out.append({"who": t["who"], "first": i, "last": i, "signals": []})
    return out


def idea_ends(turns: list[dict], finished: dict[str, bool] | None = None, who: str = "them") -> list[int]:
    """Indexes of `who`'s turns that end an idea, as it can be known live: they paused with a complete thought (the turn
    check's `finished[turn id]`; unknown counts as complete), or it is the last turn of their floor (the other side then
    really speaks: production's backstop reads it then). A listening signal is never a turn of its own."""
    signals = listening(turns)
    out = []
    for f in floors(turns):
        if f["who"] != who:
            continue
        mine = [i for i in range(f["first"], f["last"] + 1) if i not in signals and turns[i]["who"] == who]
        out += [i for i in mine if i == mine[-1] or (finished or {}).get(turns[i]["id"], True)]
    return sorted(set(out))


def speaking_at(turns: list[dict], t: float, who: str = "them") -> int | None:
    """The index of `who`'s turn in progress at second t (a real turn, not a listening signal), or None."""
    end = ends(turns)
    signals = listening(turns)
    for i, u in enumerate(turns):
        if u["who"] == who and i not in signals and u["t"] <= t < end[i]:
            return i
    return None


def label(turns: list[dict]) -> dict[str, str]:
    """{turn id: "listening"} for the listening signals, to show in a log."""
    return {turns[i]["id"]: "listening" for i in listening(turns)}


CHECKS = Path.home() / ".vocify-evals" / "strategic-2026-10-21" / "turncheck"
CHECKS_FULL = Path.home() / ".vocify-evals" / "strategic-2026-10-21" / "turncheck-full"
CHECKS_PROD = Path.home() / ".vocify-evals" / "strategic-2026-10-21" / "turncheck-prod"
CONVERSATION_TURNS = 30


def turn_checks(call: dict) -> dict[str, bool]:
    """{turn id: finished} for the other side's turns, from production's turn check (app.services.copilot.turn), asked once
    per call and kept in CHECKS. The conversation it sees is what came before, as production sends it."""
    import asyncio

    path = CHECKS / f"{call['id']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    from app.services.copilot.turn import read_turn

    turns = call["turns"]
    signals = listening(turns)
    asks = [i for i, t in enumerate(turns) if t["who"] == "them" and i not in signals and len(tokens(t["text"])) >= 4]

    async def one(i: int) -> tuple[str, bool]:
        convo = "\n".join(f"{'Them' if u['who'] == 'them' else 'You'}: {u['text']}" for u in turns[max(0, i - CONVERSATION_TURNS):i + 1])
        reading = await read_turn(convo, turns[i]["text"])
        if reading["finished"] is None and reading["objection"] is None:
            raise RuntimeError(f"turn check unavailable for {call['id']} {turns[i]['id']}: nothing is kept")
        return turns[i]["id"], reading["finished"] is not False

    async def run() -> dict[str, bool]:
        sem = asyncio.Semaphore(8)

        async def guarded(i):
            async with sem:
                return await one(i)
        return dict(await asyncio.gather(*(guarded(i) for i in asks)))

    out = asyncio.run(run())
    CHECKS.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def turn_readings(call: dict, custom: dict | None = None) -> dict[str, dict]:
    """{turn id: {"finished", "objection"}} from production's turn check for the other side's turns (objection: "none",
    a fixed kind or "custom"; "question" is a direct question), asked once per call and kept in CHECKS_FULL. With
    `custom` (the playbook's own objections, as production passes them) it is kept apart, in CHECKS_PROD."""
    import asyncio

    path = (CHECKS_PROD if custom else CHECKS_FULL) / f"{call['id']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    from app.services.copilot.turn import read_turn

    turns = call["turns"]
    signals = listening(turns)
    asks = [i for i, t in enumerate(turns) if t["who"] == "them" and i not in signals and len(tokens(t["text"])) >= 2]

    async def one(i: int) -> tuple[str, dict]:
        convo = "\n".join(f"{'Them' if u['who'] == 'them' else 'You'}: {u['text']}" for u in turns[max(0, i - CONVERSATION_TURNS):i + 1])
        r = await read_turn(convo, turns[i]["text"], custom)
        if r["finished"] is None and r["objection"] is None:
            # The classifier could not be reached (a spent key answered 403 for hours and every turn was kept as "none").
            raise RuntimeError(f"turn check unavailable for {call['id']} {turns[i]['id']}: nothing is kept")
        return turns[i]["id"], {"finished": r["finished"] is not False, "objection": r.get("entry_id") or r["objection"] or "none"}

    async def run() -> dict[str, dict]:
        sem = asyncio.Semaphore(8)

        async def guarded(i):
            async with sem:
                return await one(i)
        return dict(await asyncio.gather(*(guarded(i) for i in asks)))

    out = asyncio.run(run())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
