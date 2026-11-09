"""Live chunks: fragments in a script the rep never speaks are dropped (the 6 Nov call's lines, verbatim)."""

from app.services.transcript_turns import without_foreign_script

ES_CA = ["es", "ca"]


def test_the_invented_fragments_go_and_the_spanish_stays():
    assert without_foreign_script("うーん。 Yo sepa, ni en diferente, en efecto", ES_CA) == "Yo sepa, ni en diferente, en efecto"
    assert without_foreign_script("应该是这样子 飲みたとえ。 Todo esto ya lo tengo analizado", ES_CA) == "Todo esto ya lo tengo analizado"
    assert without_foreign_script("estaban alisando y diciendo al comercial: えー、 ¿Qué era lo que estaba cometiendo?", ES_CA) == (
        "estaban alisando y diciendo al comercial: ¿Qué era lo que estaba cometiendo?"
    )
    assert without_foreign_script("ya en el ticket. ครับ", ES_CA) == "ya en el ticket."


def test_a_chunk_that_was_only_invented_text_is_dropped():
    assert without_foreign_script("ดีสัญญา", ES_CA) == ""
    assert without_foreign_script("みらせ- ばけ", ES_CA) == ""


def test_spanish_catalan_and_accents_are_untouched():
    for line in ("¿Cómo lo habéis hecho?", "Bon dia, et truco per parlar de la proposta.", "Sí, perfecto. Ñandú, pingüino."):
        assert without_foreign_script(line, ES_CA) == line


def test_a_rep_who_speaks_a_non_latin_language_keeps_everything():
    assert without_foreign_script("Привет, как дела", ["es", "ru"]) == "Привет, как дела"
    assert without_foreign_script("ครับ ok", ["th"]) == "ครับ ok"
