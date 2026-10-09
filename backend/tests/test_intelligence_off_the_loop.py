"""The database stages of an intelligence pass run in worker threads, so the event loop stays free
for the requests of the page that is waiting on it."""

import asyncio
import threading
from types import SimpleNamespace

from app.services.intelligence import worker


def test_a_pass_runs_its_blocking_stages_off_the_event_loop_thread(monkeypatch):
    seen: dict[str, int] = {}

    def where(stage):
        def inner(*_a, **_k):
            seen[stage] = threading.get_ident()
            return {"memo_id": "m", "job_id": "j", "run_id": "r"} if stage == "claim" else (
                {"id": "m"} if stage == "load" else (["s"] if stage == "sources" else "stored")
            )
        return inner

    intelligence = SimpleNamespace(model_dump=lambda: {"k": 1}, input_revision="rev")

    def interpret(memo, classify, sources):
        seen["interpret"] = threading.get_ident()
        return intelligence, True

    monkeypatch.setattr("app.services.intelligence.interpret.interpret_memo", interpret)

    async def classify(_memo):
        seen["classify"] = threading.get_ident()
        return {}

    async def scenario():
        loop_thread = threading.get_ident()
        result = await worker.run_claimed_awaiting(
            where("claim"), where("load"), where("publish"), classify, where("sources"), where("store"),
        )
        return loop_thread, result

    loop_thread, result = asyncio.run(scenario())
    assert result["published"] and result["outcome"] == "stored"
    for stage in ("claim", "load", "sources", "interpret", "store", "publish"):
        assert seen[stage] != loop_thread, f"{stage} ran on the event loop"
    assert seen["classify"] == loop_thread  # the LLM call stays async on the loop
