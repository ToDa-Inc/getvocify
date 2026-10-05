"""A model that answers without reasoning gets the *_no_reasoning checks; Jev's next-action
decisions replace the judge's only where Jev is sure."""

import asyncio

import pytest

from app.config import settings

TOGETHER = "together/deepseek-ai/DeepSeek-V4.1-Flash"


def test_answers_without_reasoning():
    from app.services.llm.shared import answers_without_reasoning

    assert answers_without_reasoning(TOGETHER, None)
    assert answers_without_reasoning("google/gemini-3.8-flash", "none")
    assert not answers_without_reasoning(TOGETHER, "low")
    assert not answers_without_reasoning("google/gemini-3.8-flash", None)


def test_the_reading_gets_its_checks_only_without_reasoning():
    from app.services.intelligence.call_reading import build_reading_messages

    turns = [{"speaker": "S1", "text": "Hola"}, {"speaker": "S2", "text": "Dime"}]
    plain = build_reading_messages(turns, captured_at="2026-10-06")[0]["content"]
    checked = build_reading_messages(turns, captured_at="2026-10-06", no_reasoning=True)[0]["content"]
    assert "Final check before you answer (call_type)" not in plain
    assert checked.startswith(plain) and "Final check before you answer (call_type)" in checked


@pytest.mark.parametrize("model,effort,expected", [
    (TOGETHER, None, True),
    ("google/gemini-3.8-flash", None, False),
    ("google/gemini-3.8-flash", "none", True),
])
def test_the_judge_gets_its_checks_only_without_reasoning(monkeypatch, model, effort, expected):
    from app.services.intelligence.extract import CALL_READING_PROMPT_VERSION, build_messages

    monkeypatch.setattr(settings, "INTELLIGENCE_MODEL", model)
    monkeypatch.setattr(settings, "INTELLIGENCE_JUDGE_EFFORT", effort)
    memo = {"id": "m1", "transcript": "You: Hola\nThem: Dime", "extraction": {}}
    system = build_messages(memo, prompt_version=CALL_READING_PROMPT_VERSION, transcript=memo["transcript"],
                            call={"call_type": "cold_first_contact"})[0]["content"]
    assert ("every step you marked \"missed\"" in system) is expected


@pytest.mark.parametrize("model,effort,expected", [(TOGETHER, None, True), ("google/gemini-3.5-flash-lite", None, False)])
def test_step_one_gets_its_rules_only_without_reasoning(monkeypatch, model, effort, expected):
    from app.services.extraction import GROUNDED_SYSTEM_PROMPT, grounded_system_prompt

    monkeypatch.setattr(settings, "EXTRACTION_MODEL", model)
    monkeypatch.setattr(settings, "EXTRACTION_REASONING_EFFORT", effort)
    prompt = grounded_system_prompt()
    assert prompt.startswith(GROUNDED_SYSTEM_PROMPT)
    assert ("(poco claro en el audio)" in prompt) is expected


def _shaped():
    return {
        "next": {"callback": {"needed": True, "when": "2026-10-07"}, "followup_email": {"needed": False}},
        "meeting": {"agreed": None, "starts_at": None},
    }


def test_jev_decisions_replace_the_judges_where_jev_is_sure(monkeypatch):
    from app.services.intelligence import extract
    from app.services.llm import jev

    async def fake(self, state, questions):
        assert [q["question"] for q in questions] == ["followup_email", "callback", "meeting_agreed"]
        return {"status": "partial", "answers": {"followup_email": "yes", "callback": "no", "meeting_agreed": "unknown"}}

    monkeypatch.setattr(jev.JevClient, "classify_questions", fake)
    shaped = _shaped()
    asyncio.run(extract._apply_jev_decisions(shaped, "You: hola"))
    assert shaped["next"]["followup_email"]["needed"] is True
    assert shaped["next"]["callback"] == {"needed": False, "when": "2026-10-07"}  # the judge's day stays
    assert shaped["meeting"]["agreed"] is None  # unknown keeps the judge's


def test_jev_down_keeps_the_judges_decisions(monkeypatch):
    from app.services.intelligence import extract
    from app.services.llm import jev

    async def boom(self, state, questions):
        raise RuntimeError("down")

    monkeypatch.setattr(jev.JevClient, "classify_questions", boom)
    shaped = _shaped()
    asyncio.run(extract._apply_jev_decisions(shaped, "You: hola"))
    assert shaped == _shaped()
