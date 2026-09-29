"""The reply language is decided from the question, in code."""

import pytest

from app.services.crm_copilot.language import answer_hint, reply_language


@pytest.mark.parametrize(
    "question, expected",
    [
        ("How many calls did Luis make in August?", "en"),
        ("how did I handle the price objection with Marina?", "en"),
        ("What should I do today?", "en"),
        ("¿Cuál fue mi tasa de conexión en agosto?", "es"),
        ("dame los datos generales del equipo", "es"),
        ("qué deals se me están enfriando", "es"),
        ("ok", None),
        ("Marina López", None),
    ],
)
def test_the_question_decides_the_language(question, expected):
    assert reply_language(question) == expected


def test_the_hint_names_the_language_only_when_it_is_known():
    assert answer_hint("en") == "(Answer in English.)" and answer_hint("es") == "(Responde en español.)"
    assert answer_hint(None) is None
