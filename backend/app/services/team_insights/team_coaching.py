"""Equipo (Head of Sales): three questions over the team's conversations of one interaction type,
read like the reps' own coaching (rep_coaching) so both see the same numbers. No I/O.

1. Do they follow the playbook? Team adherence, and each rep against each step.
2. Does the playbook work? Per step, how often the goal is reached when the step is done and when
   it is not. The goal is what the rep declared (a meeting), never what a model read in the call.
3. Why do we lose? The calls marked not interested or disqualified in Vocify, or whose deal was
   lost in the CRM, each with its main cause read from that call: the objection left open, else the
   obstacle, else the contact's earlier calls; "never got to talk" when there was no conversation.
"""

from __future__ import annotations

from app.services.coaching import rep_coaching as engine
from app.services.coaching.metrics import aggregate_adherence
from app.services.playbooks.step_identity import StepMatcher

# A comparison needs this many calls on each side and this many goals reached; below it, no verdict.
MIN_GROUP = 5
MIN_GOALS = 3
# Ten points between doing a step and not doing it is a difference worth a verdict.
DIFFERENCE = 0.10
LOST_OUTCOMES = ("not_interested", "disqualified")
_MAX_EXAMPLES = 3


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def adherence_of(rows: list[dict]) -> dict:
    """{adherence, conversations}: THE "% del proceso" (rep_coaching.adherence_part), summed."""
    parts = [part for part in (engine.adherence_part(row) for row in rows) if part is not None]
    return {
        "adherence": aggregate_adherence(parts)["adherence"] if parts else None,
        "conversations": len(parts),
    }


def rep_matrix(rows_by_user: dict[str, list[dict]], reps: list[dict], steps: list[dict]) -> list[dict]:
    """One row per rep: their adherence, conversations, meetings and each step's done / applicable."""
    out = []
    for rep in reps:
        rows = rows_by_user.get(str(rep["userId"]), [])
        conversations = [row for row in rows if row.get("is_conversation", True)]
        out.append({
            "user_id": str(rep["userId"]),
            "name": rep.get("name") or "",
            **adherence_of(rows),
            "meetings": sum(1 for row in conversations if row.get("meeting_agreed")),
            "steps": {
                rate["step_id"]: {"done": rate["done"], "applicable": rate["applicable"], "rate": rate["rate"]}
                for rate in engine.step_rates(rows, steps)
            },
        })
    return out


def _verdict(with_side: dict, without_side: dict) -> str:
    """helps / hurts / no_difference, or few_data when either side is thin or goals are few."""
    if min(with_side["calls"], without_side["calls"]) < MIN_GROUP or with_side["goals"] + without_side["goals"] < MIN_GOALS:
        return "few_data"
    difference = (with_side["rate"] or 0.0) - (without_side["rate"] or 0.0)
    if difference >= DIFFERENCE:
        return "helps"
    if difference <= -DIFFERENCE:
        return "hurts"
    return "no_difference"


def _side(rows: list[dict]) -> dict:
    goals = sum(1 for row in rows if row.get("meeting_agreed"))
    return {"calls": len(rows), "goals": goals, "rate": _rate(goals, len(rows))}


def step_effects(rows: list[dict], steps: list[dict]) -> list[dict]:
    """Per published step: the goal rate in conversations where it was done (halfway counts) and where
    it was not, and the verdict. A step whose verdict is the goal itself (the meeting the rep declares)
    is left out: it would only prove itself."""
    conversations = [row for row in rows if row.get("is_conversation", True)]
    out = []
    for step in steps:
        if step.get("outcome"):
            continue
        step_id = str(step.get("step_id"))
        matcher = StepMatcher([step])
        done, missing = [], []
        for row in conversations:
            state = next(
                (s["state"] for s in row["steps"] if matcher.match(s["step_id"], s.get("criterion")) == step_id),
                None,
            )
            if state in engine.DONE_STATES:
                done.append(row)
            elif state == "missing":
                missing.append(row)
        with_side, without_side = _side(done), _side(missing)
        out.append({
            "step_id": step_id,
            "label": str(step.get("label") or step_id),
            "with": with_side,
            "without": without_side,
            "verdict": _verdict(with_side, without_side),
        })
    return out


def process_effect(rows: list[dict]) -> dict:
    """The whole process: conversations that ran it complete against the rest."""
    conversations = [row for row in rows if row.get("is_conversation", True) and row.get("full_process", True)]
    complete = [row for row in conversations if engine.process_complete(row)]
    rest = [row for row in conversations if not engine.process_complete(row)]
    with_side, without_side = _side(complete), _side(rest)
    return {"with": with_side, "without": without_side, "verdict": _verdict(with_side, without_side)}


# --- why we lose ---------------------------------------------------------------------------------


def call_signals(memo: dict) -> dict | None:
    """What a call says about a loss, with or without a playbook: who, when, with whom, whether there
    was a conversation, and every time the prospect resisted."""
    observed = engine.parse_instant(memo.get("capture_started_at")) or engine.parse_instant(memo.get("created_at"))
    if observed is None:
        return None
    intel = engine._intelligence(memo)
    resistances = [
        {
            "kind": "obstacle" if item.get("kind") == "obstacle" else "objection",
            "category": str(item.get("category") or "other"),
            "objection_id": item.get("objection_id") or None,
            "resolution": item.get("resolution"),
            "quote": item.get("quote") or None,
        }
        for item in intel.get("objections") or []
        if isinstance(item, dict)
    ]
    return {
        "memo_id": str(memo.get("id") or ""),
        "user_id": str(memo.get("user_id") or ""),
        "motion": memo.get("sales_motion_key"),
        "observed_at": observed,
        "keys": [str(key) for key in (memo.get("hubspot_contact_id"), memo.get("hubspot_deal_id")) if key],
        "conversation": engine.is_conversation(memo),
        "rep_outcome": memo.get("rep_outcome"),
        "resistances": resistances,
    }


def _cause_key(item: dict, custom_ids: set[str]) -> str:
    if item["kind"] == "obstacle":
        return f"obstacle:{item['category']}"
    if item.get("objection_id") and item["objection_id"] in custom_ids:
        return f"custom:{item['objection_id']}"
    return item["category"]


def _main_resistance(signal: dict) -> dict | None:
    """The objection left open (the last one), else an obstacle, else any objection raised."""
    resistances = signal["resistances"]
    for pick in (
        lambda r: r["kind"] == "objection" and r.get("resolution") == "open",
        lambda r: r["kind"] == "obstacle",
        lambda r: r["kind"] == "objection",
    ):
        found = [item for item in resistances if pick(item)]
        if found:
            return found[-1]
    return None


def loss_cause(signal: dict, history: list[dict], custom_ids: set[str]) -> dict:
    """{cause, quote, memo_id, from_history} of one lost call. Its own resistance first; with none,
    the newest earlier call with the same contact or deal that has one; "no_conversation" when the
    contact was never talked to (all voicemails, no answers, seconds-long calls), else "unclear"."""
    item = _main_resistance(signal)
    if item is not None:
        return {"cause": _cause_key(item, custom_ids), "quote": item["quote"], "memo_id": signal["memo_id"], "from_history": False}
    earlier = sorted(
        (other for other in history
         if other["memo_id"] != signal["memo_id"]
         and other["observed_at"] <= signal["observed_at"]
         and set(other["keys"]) & set(signal["keys"])),
        key=lambda other: other["observed_at"],
        reverse=True,
    )
    for other in earlier:
        item = _main_resistance(other)
        if item is not None:
            return {"cause": _cause_key(item, custom_ids), "quote": item["quote"], "memo_id": other["memo_id"], "from_history": True}
    talked = signal["conversation"] or any(other["conversation"] for other in earlier)
    return {"cause": "unclear" if talked else "no_conversation", "quote": None, "memo_id": signal["memo_id"], "from_history": False}


def losses(
    signals: list[dict],
    crm_lost: set[str],
    custom_labels: dict[str, str],
    names: dict[str, str],
    *,
    history: list[dict] | None = None,
) -> dict:
    """The lost calls of these signals ranked by cause. `signals` are the period's calls of the type;
    `history` (every call read, earlier ones too; `signals` by default) is where a call with nothing
    to say looks back. A call the rep marked in Vocify keeps that source; one only lost in the CRM is
    "crm_lost"."""
    custom_ids = {key.split(":", 1)[1] for key in custom_labels}
    by_source = {"not_interested": 0, "disqualified": 0, "crm_lost": 0}
    causes: dict[str, dict] = {}
    for signal in sorted(signals, key=lambda s: s["observed_at"], reverse=True):
        source = signal["rep_outcome"] if signal["rep_outcome"] in LOST_OUTCOMES else ("crm_lost" if signal["memo_id"] in crm_lost else None)
        if source is None:
            continue
        by_source[source] += 1
        found = loss_cause(signal, history if history is not None else signals, custom_ids)
        entry = causes.setdefault(found["cause"], {"cause": found["cause"], "label": custom_labels.get(found["cause"]), "count": 0, "examples": []})
        entry["count"] += 1
        if found["quote"] and len(entry["examples"]) < _MAX_EXAMPLES:
            entry["examples"].append({
                "memo_id": found["memo_id"],
                "quote": found["quote"],
                "rep": names.get(signal["user_id"], ""),
                "observed_at": signal["observed_at"].isoformat(),
                "from_history": found["from_history"],
            })
    total = sum(by_source.values())
    ranked = sorted(causes.values(), key=lambda entry: (-entry["count"], entry["cause"]))
    for entry in ranked:
        entry["share"] = _rate(entry["count"], total)
    return {"total": total, "by_source": by_source, "causes": ranked}
