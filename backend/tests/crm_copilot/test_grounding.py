"""The answer may only state numbers the tools returned and cite quotes the tools returned."""

from app.services.crm_copilot.grounding import (
    coverage_note,
    drop_sentences_with,
    resolve_evidence,
    unverified_numbers,
)

FACTS = '{"n": 14, "items": [{"name": "price", "count": 9}], "at": "2026-09-28T10:05:00+00:00"}'


def test_numbers_in_the_facts_are_verified():
    assert unverified_numbers("Precio: 9 de 14 quedaron abiertas.", FACTS, "") == []


def test_a_computed_percentage_is_not_verified():
    assert unverified_numbers("Precio: 64% abiertas.", FACTS, "") == ["64%"]


def test_small_counts_are_allowed_because_the_model_counts_list_items() :
    assert unverified_numbers("Hay 3 puntos abiertos.", FACTS, "") == []


def test_a_number_the_user_typed_is_allowed():
    assert unverified_numbers("Sobre los últimos 45 días: 9 abiertas.", FACTS, "últimos 45 días") == []


def test_dates_and_times_from_the_facts_are_verified():
    assert unverified_numbers("El 28 a las 10:05.", FACTS, "") == []
    assert unverified_numbers("El 17 de octubre.", FACTS, "") == ["17"]


def test_decimals_and_leading_zeros_normalize():
    assert unverified_numbers("Media 3,5 h.", '{"h": 3.5}', "") == []
    assert unverified_numbers("Son 007.", '{"x": 7}', "") == []


def test_evidence_tokens_are_not_read_as_numbers():
    assert unverified_numbers("Caro [ev-3f9a1234].", FACTS, "") == []


EVIDENCE = [
    {"id": "ev-aaa", "quote": "Nos parece caro", "memo_id": "m1"},
    {"id": "ev-bbb", "quote": "te lo envío", "memo_id": "m1"},
]


def test_known_tokens_become_numbered_citations_in_order_of_appearance():
    text, used = resolve_evidence("Dijo que es caro [ev-bbb] y luego [ev-aaa] y otra vez [ev-bbb].", EVIDENCE)
    assert text == "Dijo que es caro [1] y luego [2] y otra vez [1]."
    assert [e["id"] for e in used] == ["ev-bbb", "ev-aaa"]


def test_an_unknown_token_is_removed_not_invented():
    text, used = resolve_evidence("Algo [ev-zzz] cierto.", EVIDENCE)
    assert text == "Algo cierto."
    assert used == []


def test_drop_sentences_removes_only_the_offending_ones():
    text = "Marina está interesada. Subió un 64% este mes. Llámala el jueves."
    assert drop_sentences_with(text, ["64%"]) == "Marina está interesada. Llámala el jueves."


def test_coverage_note_reports_the_weakest_read():
    assert coverage_note([]) is None
    assert coverage_note([{"coverage": "complete"}]) is None
    note = coverage_note([{"coverage": "complete"}, {"coverage": "partial", "n": 14, "n_analysed": 6}])
    assert note == {"level": "partial", "n": 14, "n_analysed": 6}
    assert coverage_note([{"coverage": "partial"}, {"coverage": "forbidden"}])["level"] == "forbidden"
    assert coverage_note([{"coverage": "unavailable"}, {"coverage": "partial"}])["level"] == "unavailable"


def test_the_unit_of_what_was_read_travels_with_the_note():
    note = coverage_note([{"coverage": "partial", "n": 100, "n_analysed": 40, "unit": "calls"}])
    assert note == {"level": "partial", "n": 100, "n_analysed": 40, "unit": "calls"}


def test_playbook_citations_are_numbered_like_conversation_citations():
    evidence = [{"id": "pb-e-price", "quote": "Pregunta cuánto cuesta hoy el problema.", "speaker": "playbook"}]
    text, used = resolve_evidence("La respuesta aprobada es preguntar el coste actual [pb-e-price].", evidence)
    assert text == "La respuesta aprobada es preguntar el coste actual [1]."
    assert used[0]["speaker"] == "playbook"
    assert unverified_numbers("Regla [pb-e-price] y [ev-3f9a1234].", FACTS, "") == []


def test_a_copied_internal_id_is_removed_but_numbered_citations_survive():
    text, used = resolve_evidence("Gong [m19] y Salesloft [c-42] dijo caro [ev-aaa] (ver [2026]).", EVIDENCE)
    assert text == "Gong y Salesloft dijo caro [1] (ver [2026])."
    assert [e["id"] for e in used] == ["ev-aaa"]


def test_amounts_may_be_written_with_thousand_separators_or_a_k_suffix():
    facts = '{"open_value": 157000, "avg": 6000, "rate": 23.5}'
    for written in ("157.000 €", "157,000", "157000", "157k", "157 k€", "6.000 €", "6K"):
        assert unverified_numbers(f"Valen {written}.", facts, "") == [], written
    assert unverified_numbers("Valen 158.000 €.", facts, "") == ["158.000"]
    assert unverified_numbers("La media es 23,5 %.", facts, "") == []
    assert unverified_numbers("La media es 23.5%.", facts, "") == []


def test_an_ambiguous_dot_is_read_both_ways_but_facts_are_read_as_json():
    assert unverified_numbers("Son 1.234 llamadas.", '{"n": 1234}', "") == []
    assert unverified_numbers("Son 1.234 llamadas.", '{"n": 1.234}', "") == []
    assert unverified_numbers("Son 1.234.567 €.", '{"v": 1234567}', "") == []
    assert unverified_numbers("Son 1.234,56 €.", '{"v": 1234.56}', "") == []


def test_a_closing_offer_is_dropped_but_a_lone_clarifying_question_stays():
    from app.services.crm_copilot.grounding import strip_trailing_offer

    assert strip_trailing_offer("No existe ese campo. ¿Quieres que mire otra propiedad?") == "No existe ese campo."
    assert strip_trailing_offer("Tienes 3 tareas.\n\nDo you want me to list them?") == "Tienes 3 tareas."
    assert strip_trailing_offer("Hay dos que encajan, ¿cuál es?") == "Hay dos que encajan, ¿cuál es?"
    assert strip_trailing_offer("¿Quieres que lo mire?") == "¿Quieres que lo mire?"
    assert strip_trailing_offer("Son 12 deals.") == "Son 12 deals."
    assert strip_trailing_offer("No hay campo de cualificación.\n\nSi quieres, puedo mirar las conversaciones.") == "No hay campo de cualificación."
    assert strip_trailing_offer("Sin datos. If you want, I can check calls.") == "Sin datos."
    assert strip_trailing_offer("Si quieres, puedo mirarlo.") == "Si quieres, puedo mirarlo."
    assert strip_trailing_offer("Tienes 2 reuniones. Si quieres cerrar este mes, necesitas 3 más.") == "Tienes 2 reuniones. Si quieres cerrar este mes, necesitas 3 más."
    assert strip_trailing_offer("Te queda una tarea. Vence hoy?") == "Te queda una tarea. Vence hoy?"


def test_a_period_the_tool_chose_is_carried_so_the_app_can_say_it():
    assert coverage_note([{"coverage": "complete", "n": 9, "n_analysed": 9, "period_days": 90, "period_defaulted": True}]) == {"level": "period", "period_days": 90}
    assert coverage_note([{"coverage": "complete", "period_days": 30, "period_defaulted": False}]) is None
    partial = coverage_note([{"coverage": "partial", "n": 10, "n_analysed": 4, "unit": "conversations", "period_days": 30, "period_defaulted": True}])
    assert partial == {"level": "partial", "n": 10, "n_analysed": 4, "unit": "conversations", "period_days": 30}
    assert coverage_note([{"coverage": "forbidden", "period_days": 30, "period_defaulted": True}]) == {"level": "forbidden"}
