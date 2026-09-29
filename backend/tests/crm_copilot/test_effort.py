"""Reasoning is spent where it pays: lookups stay low, analysis goes high, and a turn that struggles is bumped up."""

import pytest

from app.services.crm_copilot.effort import HIGH, LOW, choose_effort, heuristic_effort
from app.services.crm_copilot.model_profile import request_extra


@pytest.mark.parametrize(
    "question, expected",
    [
        ("¿cuál fue la tasa de conexión en agosto?", LOW),
        ("¿cuántos deals abiertos tengo?", LOW),
        ("what's my pipeline value?", LOW),
        ("cual es el connect rate de agosto vs setiembre", HIGH),
        ("compara la tasa de conexión de septiembre con la de agosto", HIGH),
        ("¿por qué perdemos deals?", HIGH),
        ("how should I handle the price objection with Marina?", HIGH),
        ("prepárame la llamada con Inés Vidal", HIGH),
        ("dame los datos generales del equipo", HIGH),
        ("¿qué tengo pendiente hoy? ¿y qué debería priorizar?", HIGH),
        ("cuántas llamadas hicimos en agosto y además cuántas conectaron por comercial", HIGH),
        (" ".join(["palabra"] * 26), HIGH),
        ("¿cuántas reuniones ha agendado cada comercial de mi equipo durante las últimas semanas?", None),
    ],
)
def test_the_wording_settles_the_clear_cases_without_a_model_call(question, expected):
    assert heuristic_effort(question) == expected


class FakeJev:
    def __init__(self, answer=None, available=True, fail=False):
        self.answer, self.is_available, self.fail, self.calls = answer, available, fail, []

    async def classify_questions(self, state, questions):
        self.calls.append((state, questions))
        if self.fail:
            raise RuntimeError("down")
        return {"status": "ready", "answers": {"ask_effort": self.answer}}


AMBIGUOUS = "¿cuántas reuniones ha agendado cada comercial de mi equipo durante las últimas semanas?"


@pytest.mark.asyncio
async def test_clear_cases_never_reach_jev():
    jev = FakeJev("analysis")
    assert await choose_effort("¿cuántos deals abiertos tengo?", jev=jev) == LOW
    assert await choose_effort("compara agosto con julio", jev=jev) == HIGH
    assert jev.calls == []


@pytest.mark.asyncio
async def test_an_ambiguous_question_follows_jev():
    assert await choose_effort(AMBIGUOUS, jev=FakeJev("analysis")) == HIGH
    assert await choose_effort(AMBIGUOUS, jev=FakeJev("lookup")) == LOW


@pytest.mark.asyncio
@pytest.mark.parametrize("jev", [FakeJev("unknown"), FakeJev(None), FakeJev(available=False), FakeJev(fail=True)])
async def test_when_jev_is_unsure_unavailable_or_broken_the_answer_is_low_never_an_error(jev):
    assert await choose_effort(AMBIGUOUS, jev=jev) == LOW


def test_effort_reaches_the_request_and_high_gets_room_for_its_reasoning():
    low, high = request_extra("deepseek/deepseek-v4.1-flash", "low"), request_extra("deepseek/deepseek-v4.1-flash", "high")
    assert low["reasoning"] == {"effort": "low"} and high["reasoning"] == {"effort": "high"}
    assert high["max_tokens"] > low["max_tokens"]
    assert request_extra("deepseek/deepseek-v4.1-flash", "nonsense")["reasoning"] == {"effort": "low"}
    assert "provider" not in request_extra("google/gemini-3.8-flash", "high")
