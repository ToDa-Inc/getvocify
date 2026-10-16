"""One trial of the Head of Sales, as a session (`playbook_assistant_sessions`, kind `trial`):

  state = {motion_key, lang, cases: [{id, source, client_text, motion_key}], runs: {case_id: run},
           verdicts: {case_id: {verdict, topic}}, touched: [call type keys]}

The cases are made once and kept, so the trial can be left and resumed. A case is run with the draft as it is now;
a verdict that changes the answer edits the draft through `apply_verdict`, runs the case again and, for a correction,
checks one similar phrase. Nothing here publishes: `finish_trial` does, only when the Head of Sales activates.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from app.services.company import Membership
from app.services.copilot.load_grounding import whole_playbook
from app.services.playbooks.api_support import company_context, product_context
from app.services.playbooks.assistant import draft_content, edit_draft
from app.services.playbooks.assistant_store import AssistantStore
from app.services.playbooks.gaps import recent_suggest_events
from app.services.playbooks.repository import PlaybookRepository
from app.services.playbooks.structured import OBJECTION_CATEGORIES
from app.services.playbooks.trial import (
    VERDICTS,
    activate,
    apply_verdict,
    build_cases,
    draft_snapshot,
    run_case,
    similar_phrase,
    trial_result,
)

CHANGING = frozenset({"corrected", "never_say", "branch", "own"})


class TrialError(Exception):
    """code: session_not_found | case_not_found | bad_verdict"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


Runner = Callable[..., Awaitable[dict]]
Similar = Callable[..., Awaitable[str]]


def _load(store: AssistantStore, membership: Membership, session_id: str) -> dict:
    session = store.get_session(membership.company_id, session_id)
    if session is None or session.get("kind") != "trial":
        raise TrialError("session_not_found")
    return session


def _case(state: dict, case_id: str) -> dict:
    found = next((c for c in state.get("cases") or [] if c["id"] == case_id), None)
    if found is None:
        raise TrialError("case_not_found")
    return found


def public_trial(session: dict) -> dict:
    """What the screen needs: the cases with their verdicts, the runs seen so far, which case is next and how it is
    going. The model's instructions and the draft never travel."""
    state = session["state"]
    verdicts = state.get("verdicts") or {}
    cases = state.get("cases") or []
    current = next((c["id"] for c in cases if c["id"] not in verdicts), None)
    return {
        "id": session["id"],
        "motion_key": state["motion_key"],
        "status": "done" if session.get("status") == "done" else "open",
        "total": len(cases),
        "decided": len(verdicts),
        "cases": [
            {"id": c["id"], "source": c["source"], "client_text": c["client_text"], "verdict": (verdicts.get(c["id"]) or {}).get("verdict")}
            for c in cases
        ],
        "current_id": current,
        "runs": dict(state.get("runs") or {}),
        "result": trial_result(list(verdicts.values())),
    }


async def start_trial(
    store: AssistantStore, repository: PlaybookRepository, supabase: Any, membership: Membership, *, motion_key: str, lang: str,
    llm: Any = None, fresh: bool = False,
) -> dict:
    """The company's open trial, or a new one with its cases. With `fresh` the open one is closed first (repeating it)."""
    company_id = membership.company_id
    open_session = store.latest_open_session(company_id, "trial")
    if open_session is not None and not fresh:
        return open_session
    if open_session is not None:
        store.save_session(company_id, open_session["id"], state=open_session["state"], status="done")
    content, _ = draft_content(repository, company_id, motion_key)
    material = [company_context(supabase, repository, company_id)]
    material += [f"{s.get('label')}: {s.get('criterion')}" for s in content["steps"]]
    material += [f"{o.get('label') or o.get('category')}: {o.get('guidance')}" for o in content["objections"] if o.get("guidance")]
    cases = await build_cases(
        events=recent_suggest_events(supabase, company_id), source_texts=material, entries=content["objections"],
        lang=lang, motion_key=motion_key, llm=llm,
    )
    state = {"motion_key": motion_key, "lang": lang, "cases": cases, "runs": {}, "verdicts": {}, "touched": []}
    return store.create_session(company_id, membership.user_id, "trial", state)


async def _run(repository: PlaybookRepository, supabase: Any, company_id: str, state: dict, case: dict, runner: Runner) -> dict:
    motion = state["motion_key"]
    snapshot = whole_playbook(supabase, company_id, draft_snapshot(repository.editor_snapshot(company_id, motion, include_draft=True), motion))
    knowledge = (repository.get_knowledge(company_id) or {}).get("data")
    return await runner(case, snapshot=snapshot, knowledge=knowledge, product_context=product_context(supabase, company_id), lang=state.get("lang") or "es")


async def run_trial_case(
    store: AssistantStore, repository: PlaybookRepository, supabase: Any, membership: Membership, *, session_id: str, case_id: str,
    runner: Runner = run_case,
) -> dict:
    """The case run with the draft as it is now -> {case, run}; the run is kept so the trial can be resumed."""
    session = _load(store, membership, session_id)
    state = dict(session["state"])
    case = _case(state, case_id)
    run = await _run(repository, supabase, membership.company_id, state, case, runner)
    state["runs"] = {**(state.get("runs") or {}), case_id: run}
    store.save_session(membership.company_id, session_id, state=state)
    return {"case": {"id": case["id"], "source": case["source"], "client_text": case["client_text"]}, "run": run}


def _target(run: Optional[dict]) -> Optional[str]:
    """The answer a correction is about: the one the card followed, the team's own objection that matched, or the usual
    objection the turn check named."""
    if not run:
        return None
    source = (run.get("card") or {}).get("source_id")
    if source:
        return str(source)
    if run.get("entry_id"):
        return str(run["entry_id"])
    return f"objection:{run['detected']}" if run.get("detected") in OBJECTION_CATEGORIES else None


def _topic(run: Optional[dict]) -> str:
    if not run:
        return ""
    return str(run.get("label") or run.get("detected") or "") if run.get("detected") == "custom" else str(run.get("detected") or "")


async def decide_case(
    store: AssistantStore, repository: PlaybookRepository, supabase: Any, membership: Membership, *, session_id: str, case_id: str,
    verdict: str, text: Optional[str] = None, when: Optional[str] = None, runner: Runner = run_case, similar: Similar = similar_phrase,
) -> dict:
    """Records a verdict -> {run, similar, result, trial}. A verdict that changes the answer edits the draft first (an answer
    that does not fit raises ValueError and nothing is recorded), runs the case again with the new draft and, for a
    correction, runs one similar phrase to see whether it holds."""
    if verdict not in VERDICTS:
        raise TrialError("bad_verdict")
    session = _load(store, membership, session_id)
    state = dict(session["state"])
    case = _case(state, case_id)
    company_id, motion = membership.company_id, state["motion_key"]
    run = (state.get("runs") or {}).get(case_id)
    rerun: Optional[dict] = None
    similar_out: Optional[dict] = None
    card = (run or {}).get("card")
    if verdict == "approve" and card and not card.get("source_id"):
        # Vocify's general help, approved: from now on it is the team's own answer, so it is what live help follows.
        target = _target(run)
        line = str(card.get("say_this") or "")
        edit_draft(repository, company_id, motion, lambda content: apply_verdict(content, case, target, "corrected", line), lang=state.get("lang") or "es")
        state["touched"] = list(dict.fromkeys([*(state.get("touched") or []), motion]))
    if verdict in CHANGING:
        if run is None:
            run = await _run(repository, supabase, company_id, state, case, runner)
        target = _target(run)
        edit_draft(repository, company_id, motion, lambda content: apply_verdict(content, case, target, verdict, text, when=when), lang=state.get("lang") or "es")
        state["touched"] = list(dict.fromkeys([*(state.get("touched") or []), motion]))
        rerun = await _run(repository, supabase, company_id, state, case, runner)
    topic = _topic(run)
    if rerun is not None:
        state["runs"] = {**(state.get("runs") or {}), case_id: rerun}
        if verdict == "corrected":
            phrase = await similar(case, state.get("lang") or "es")
            if phrase:
                sim_case = {**case, "id": f"{case_id}-similar", "client_text": phrase}
                similar_out = {"text": phrase, "run": await _run(repository, supabase, company_id, state, sim_case, runner)}
    state["verdicts"] = {**(state.get("verdicts") or {}), case_id: {"verdict": verdict, "topic": topic}}
    saved = store.save_session(company_id, session_id, state=state)
    public = public_trial(saved)
    return {"run": rerun, "similar": similar_out, "result": public["result"], "trial": public}


def finish_trial(store: AssistantStore, repository: PlaybookRepository, membership: Membership, *, session_id: str) -> dict:
    """Activates: publishes the drafts of the call types the trial touched (or the trial's own type when it changed
    nothing) -> {published, failed}. The trial is closed."""
    session = _load(store, membership, session_id)
    state = session["state"]
    outcome = activate(repository, membership, list(state.get("touched") or [state["motion_key"]]))
    store.save_session(membership.company_id, session_id, state=state, status="done")
    return outcome
