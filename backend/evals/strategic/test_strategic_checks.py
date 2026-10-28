"""The mechanical checks of the replayed brain (run_v2), each with the failure that made it.

    cd backend && .venv/bin/python -m pytest evals/strategic/test_strategic_checks.py -q
"""

from app.services.copilot.live_brain import numbers_in
from evals.strategic.run_v2 import answer_on_screen, authorized_text, call_over, conversation_lines

SOURCES = """OFFER (what the rep sells, in the rep's words):
Vocify ayuda al comercial antes, durante y después de sus reuniones.

APPROVED ANSWERS (id · category "name" (they say) : guidance)
- objection:custom:enviame_un_correo · custom "Envíame un correo" (they say: "Envíame un correo"): Sí, te lo mando sin problema. Aunque entre tú y yo, sabemos que muchos de esos mails acaban en el agujero negro. Y entre correos de aquí para allá a veces perdemos más tiempo que sentándonos 15 min.
- objection:price · price: El precio no va a ser lo que nos separe de trabajar. ¿Tienes 15 minutos esta semana?

STEPS (the rep's ordered playbook; id · label — criterion)
- demo · Demo — Propone una demo de 15 minutos con día y hora."""


def test_the_whole_entry_backs_a_number_the_copied_quote_left_out():
    # 3.0 dropped the approved email answer: the model copied the entry up to «agujero negro», without «15 min».
    card = {"act": "answer", "source": "objection:custom:enviame_un_correo", "source_quote": "Sí, te lo mando sin problema.",
            "say": "Te lo mando, pero en 15 minutos en directo lo vemos mejor."}
    assert numbers_in(card["say"]) <= numbers_in(authorized_text(SOURCES, card))


def test_an_offer_answer_is_checked_against_the_whole_offer():
    card = {"act": "answer", "source": "offer", "source_quote": "Guiados al comercial por el paso a paso", "say": "…"}
    assert "antes, durante y después" in authorized_text(SOURCES, card)


def test_a_line_resting_on_nothing_has_no_authorized_text():
    assert authorized_text(SOURCES, {"source": "context", "source_quote": "", "say": "Te doy acceso de prueba."}) == ""


def test_a_quote_found_in_another_entry_brings_that_entry():
    card = {"source": "context", "source_quote": "El precio no va a ser lo que nos separe", "say": "…"}
    assert authorized_text(SOURCES, card).startswith("objection:price")


def test_no_card_after_the_call_is_over():
    # 916d1bd8: the closing card was ready after the last words; a card nobody can use is not shown.
    assert call_over(466.0, 465.5)
    assert not call_over(464.4, 465.5)


SHOWN = [{"kind": "answer", "source": "offer", "objective": "explain the product clearly", "say": "Vocify ayuda…"}]


def test_the_same_answer_still_on_screen_is_not_shown_again():
    # 916d1bd8 run 2: they asked «¿qué es lo que tú haces?» again while the 0:25 explanation was still on screen.
    card = {"act": "answer", "source": "offer"}
    assert answer_on_screen(card, "explain the product clearly", SHOWN)


def test_once_another_card_came_the_same_source_can_answer_a_new_question():
    shown = SHOWN + [{"kind": "answer", "source": "objection:custom:ya_tenemos_gong", "objective": "find Gong gap", "say": "…"}]
    assert not answer_on_screen({"act": "answer", "source": "offer"}, "explain the product clearly", shown)


def test_a_different_objective_or_a_move_is_not_the_same_answer():
    assert not answer_on_screen({"act": "answer", "source": "offer"}, "", SHOWN)
    assert not answer_on_screen({"act": "move", "source": "offer"}, "explain the product clearly", SHOWN)


def test_the_fact_check_reads_who_said_what_including_the_turn_in_progress():
    # ea5cb466: «ya estamos con Granola…» was still being said when the card was written; the check did not see it and
    # blocked the approved competitor answer for naming Granola.
    turns = [{"t": 0.0, "who": "you", "text": "Vale."}, {"t": 1.0, "who": "them", "text": "ya estamos con Granola y estamos contentos"}]
    assert conversation_lines(turns, [1.0, 4.0], 2.4) == "Seller: Vale.\nOther side: ya estamos con Granola …"


# 916d1bd8, the last turns: the prospect closes the call; the rep says one more thing while the line is still open.
GOODBYE_TURNS = [
    {"t": 449.0, "who": "you", "text": "¿tú crees que es eso?"},
    {"t": 451.8, "who": "them", "text": "Tío. Tío, mándame un mail, mándame un mail y a ver si te podemos ver la semana que viene, ¿ok? Venga, hasta luego, tío. Mi hermano."},
    {"t": 462.7, "who": "you", "text": "pero eso es una feature nueva de Windows o..."},
]
GOODBYE_ENDS = [451.8, 462.7, 465.3]


def test_no_card_after_their_goodbye_while_the_line_is_still_open():
    # The closing card of 3.2 appeared at 7:44, two seconds after «Venga, hasta luego», before the recording ended.
    from evals.strategic.run_v2 import after_goodbye

    assert after_goodbye(GOODBYE_TURNS, GOODBYE_ENDS, 464.4)
    assert not after_goodbye(GOODBYE_TURNS, GOODBYE_ENDS, 460.0)  # still saying it


def test_a_goodbye_they_take_back_reopens_the_moment():
    from evals.strategic.run_v2 import after_goodbye

    turns = GOODBYE_TURNS + [{"t": 465.3, "who": "them", "text": "Bueno, espera, una cosa más sobre el precio que te quería decir"}]
    assert not after_goodbye(turns, GOODBYE_ENDS + [470.0], 471.0)


def test_a_goodbye_in_the_middle_of_a_turn_is_not_the_end():
    from evals.strategic.run_v2 import after_goodbye

    turns = [{"t": 0.0, "who": "them", "text": "le dije hasta luego a mi socio y entonces empezamos a mirar herramientas para el equipo comercial"}]
    assert not after_goodbye(turns, [6.0], 7.0)


def test_the_state_check_reads_only_what_was_said_after_the_earlier_card():
    turns = [{"t": 0.0, "who": "them", "text": "me interesa"}, {"t": 2.0, "who": "you", "text": "¿te enseño 15 minutos?"},
             {"t": 5.0, "who": "them", "text": "sí, sí, ya se ha podido ver"}]
    assert conversation_lines(turns, [2.0, 5.0, 7.0], 8.0, since=4.0) == "Seller: ¿te enseño 15 minutos?\nOther side: sí, sí, ya se ha podido ver"


def test_a_quote_stitched_from_several_turns_counts_when_each_piece_was_said():
    # The state check quoted two turns joined with «...»; the verbatim search of one turn missed it and blocked a good card.
    from evals.strategic.run_v2 import said_after

    turns = [{"t": 0.0, "who": "them", "text": "mándame un mail, ¿sabes? Porque ahora no es buen momento"},
             {"t": 5.0, "who": "them", "text": "al final no soy yo quien toma esa decisión, es el equipo financiero"}]
    assert said_after("ahora no es buen momento... no soy yo quien toma esa decisión", turns, 2, [5.0, 9.0], -1.0)
    assert not said_after("ahora no es buen momento... el jueves a las diez me va bien", turns, 2, [5.0, 9.0], -1.0)


def test_a_time_proposed_in_a_question_is_not_an_invented_number():
    # 1778148f: the approved «envíame un correo» answer was dropped twice for «¿Te llamo mañana a las 9?».
    from evals.strategic.run_v2 import asserted

    assert numbers_in(asserted("Te lo mando, pero mejor 15 minutos y lo ves. ¿Mañana a las 9 o el lunes?")) == numbers_in("15")
    assert numbers_in(asserted("Cuesta 49 euros al mes. ¿Lo vemos?")) == numbers_in("49")
    assert numbers_in(asserted("te llamo mañana a las 9?")) == set()


# 98d65a63 (NeuronUP), the end: the rep closes, the prospect goes along; a card came at 593.3 while it was being said.
CLOSE_TURNS = [
    {"t": 585.3, "who": "them", "text": "Sí, sí, a partir de febrero de 2027, el proyecto tiene que haber entrado en otra fase."},
    {"t": 591.2, "who": "you", "text": "Vale, vale, perfecto, pues te deseo mucha suerte."},
    {"t": 594.1, "who": "them", "text": "Más me va, más me vale. Gracias,"},
]
CLOSE_ENDS = [591.2, 594.1, 596.5]


def test_the_closing_counts_only_with_words_already_said():
    from evals.strategic.run_v2 import closing_confirmed

    assert closing_confirmed({"closing": True, "evidence": "pues te deseo"}, CLOSE_TURNS, CLOSE_ENDS, 593.3)
    # «mucha suerte» had not been said yet at 593.3: the check cannot rest on words still to come.
    assert not closing_confirmed({"closing": True, "evidence": "te deseo mucha suerte"}, CLOSE_TURNS, CLOSE_ENDS, 592.0)
    assert not closing_confirmed({"closing": False, "evidence": ""}, CLOSE_TURNS, CLOSE_ENDS, 597.0)
    assert not closing_confirmed({"closing": True, "evidence": "hasta luego"}, CLOSE_TURNS, CLOSE_ENDS, 597.0)  # never said


def test_the_steps_own_example_is_caught_in_code_even_reworded():
    # 3.6: «Déjale hablar: ¿Cómo lo tenéis montado ahora?» was the Problema example; the model called it its own words.
    from evals.strategic.run_v2 import playbook_example

    steps = SOURCES + "\n- problema · Problema — Pregunta cómo lo gestionan. Example: «¿Cómo lo tenéis organizado ahora?»"
    assert playbook_example(steps, {"say": "Déjale hablar: «¿Cómo lo tenéis montado ahora?»"})
    assert not playbook_example(steps, {"say": "¿Y qué es lo que más se te escapa en esas dos horas de escucha?"})


def test_progress_keeps_evidence_interpretation_and_state_and_a_partial_meeting_is_not_met():
    # 3.6 marked «demo met» on «vamos a hacer una» with no day: a meeting without day and hour is advancing.
    from evals.strategic.run_v2 import objectives_now

    intent = {"steps": [{"id": "problema", "kind": "objective"}, {"id": "demo", "kind": "objective"}], "data": []}
    notes = [{"type": "progress", "text": "problema advancing: supervises the team himself; what he looks for is unknown",
              "quote": "estoy 2 horas escuchando cómo hacen las llamadas", "who": "them"},
             {"type": "progress", "text": "demo advancing: accepts a meeting, no day yet", "quote": "vamos a hacer una", "who": "them"}]
    out = objectives_now(notes, intent)
    assert "problema: ADVANCING — supervises the team himself" in out and "«estoy 2 horas" in out
    assert "demo: ADVANCING" in out and "No evidence yet: goal." in out


def test_the_thread_shows_each_card_with_what_both_sides_said_after_it():
    # One call: the same «te lo mando, pero 15 minutos» came four times; the brain must see their answer to the card.
    from evals.strategic.run_min import thread

    turns = [{"t": 0.0, "who": "them", "text": "pásame información"}, {"t": 3.0, "who": "you", "text": "vale te la mando"},
             {"t": 6.0, "who": "them", "text": "envíamelo y lo comparto con el equipo"}]
    out = thread(turns, [3.0, 6.0, 9.0], [{"visible_t": 3.5, "say": "Te lo mando, ¿15 minutos?"}], 9.5)
    assert "card «Te lo mando, ¿15 minutos?»" in out
    assert "then they: envíamelo y lo comparto con el equipo" in out and "then the rep: vale te la mando" in out


def test_it_reads_at_the_end_of_their_intervention_not_at_every_pause():
    # min-1/3 read at every finished pause: cards came in bursts while the prospect was still on the same idea.
    from evals.strategic.run_turns import moments

    turns = [{"id": "t1", "t": 0.0, "who": "them", "text": "nosotros ya tenemos un proceso bastante optimizado desde hace años"},
             {"id": "t2", "t": 4.0, "who": "you", "text": "claro"},
             {"id": "t3", "t": 5.0, "who": "them", "text": "y los managers lo hacemos bien en las reuniones importantes"},
             {"id": "t4", "t": 9.0, "who": "you", "text": "vale, entonces te cuento cómo lo hacemos nosotros en Vocify con otros equipos"}]
    got = moments(turns, {"t1": {"objection": "none"}, "t3": {"objection": "none"}})
    assert [r for _, r in got] == ["them_end"] and got[0][0] == 9.0  # one reading, when their intervention ends


def test_a_question_or_objection_is_read_at_once_even_mid_intervention():
    from evals.strategic.run_turns import moments

    turns = [{"id": "t1", "t": 0.0, "who": "them", "text": "¿y esto cuánto cuesta para un equipo pequeño?"},
             {"id": "t2", "t": 3.0, "who": "you", "text": "mhm"},
             {"id": "t3", "t": 3.5, "who": "them", "text": "porque somos cuatro comerciales y no tenemos mucho presupuesto"},
             {"id": "t4", "t": 8.0, "who": "you", "text": "te explico cómo funciona el precio por comercial y lo que incluye"}]
    got = moments(turns, {"t1": {"objection": "price"}, "t3": {"objection": "price"}})
    assert ("them_urgent" in [r for _, r in got]) and got[0][0] == 3.0


def test_the_same_objection_flagged_on_each_piece_of_one_intervention_is_read_once():
    # Samuel: «mándamelo por correo» flagged on three pieces of the same intervention gave three readings and two cards.
    from evals.strategic.run_turns import moments

    turns = [{"id": "t1", "t": 0.0, "who": "them", "text": "te pediría que me lo envíes por correo, de verdad"},
             {"id": "t2", "t": 4.0, "who": "you", "text": "vale"},
             {"id": "t3", "t": 4.5, "who": "them", "text": "porque ya no te puedo atender mucho más, envíamelo"},
             {"id": "t4", "t": 9.0, "who": "you", "text": "no te preocupes, te lo mando hoy mismo y te escribo después"}]
    flag = {"objection": "custom", "entry_id": "objection:custom:enviame_un_correo"}
    got = [r for _, r in moments(turns, {"t1": flag, "t3": flag})]
    assert got.count("them_urgent") == 1 and got[-1] == "them_end"  # urgent once; their intervention still read at its end


def test_a_card_waits_until_the_rep_could_use_the_one_on_screen():
    # Ribesalat: three cards in 15 s while the prospect went on about the 10th of November.
    from evals.strategic.run_turns import rep_could_use

    turns = [{"t": 0.0, "who": "them", "text": "hablamos a partir del 10 de noviembre"}, {"t": 4.0, "who": "them", "text": "lo comentaré con mi jefe"},
             {"t": 8.0, "who": "you", "text": "vale, perfecto, pues te llamo el martes diez por la mañana y lo vemos con calma los dos, sin prisa ninguna y con tu responsable"}]
    end, shown = [4.0, 8.0, 14.0], [{"visible_t": 3.0}]
    assert not rep_could_use(shown, turns, end, [(0.0, 8.0)], 7.0)  # same intervention, still talking
    assert rep_could_use(shown, turns, end, [(0.0, 8.0)], 14.5)  # the rep has spoken since


def test_a_question_still_being_asked_is_not_read_and_dime_invites_them_on():
    # Excel 3:51: «¿Se podría…» (the turn check: a question, not finished) — «Dime» — «llamar»: a card said «¿Se podría qué?».
    from evals.strategic import turns as sem
    from evals.strategic.run_turns import moments

    turns = [{"id": "t1", "t": 0.0, "who": "them", "text": "muy fácil. Eh, vale, em, y- ¿Se podría"},
             {"id": "t2", "t": 2.9, "who": "you", "text": "Dime"},
             {"id": "t3", "t": 3.6, "who": "them", "text": "llamar desde Vocify a los clientes directamente, sin otra herramienta"},
             {"id": "t4", "t": 8.0, "who": "you", "text": "es una muy buena pregunta, Vocify graba las llamadas que hacéis desde HubSpot"}]
    assert 1 in sem.listening(turns)  # «Dime» between their two pieces invites them on
    got = moments(turns, {"t1": {"finished": False, "objection": "question"}, "t3": {"finished": True, "objection": "question"}})
    assert got == [(8.0, "them_urgent")]  # read once, with the whole question


def test_a_long_intervention_is_read_while_it_goes_on_not_only_at_its_end():
    # The prospect spoke from 2:36 to 5:56 with only «claro», «sí» from the rep: the main pain (2:44) waited three minutes.
    from evals.strategic.run_turns import moments

    pain = ("uno de las cosas que más nos ha costado era el ramp up period del account executive, el SDR no, el SDR es sencillo; "
            "pocas veces hemos conseguido que superen el ramp up")
    more = "y además el founder es muy reacio a todo lo que sea una inversión que no traiga MRR al corto plazo, es un error"
    turns = [{"id": "t1", "t": 0.0, "who": "them", "text": pain}, {"id": "t2", "t": 8.0, "who": "you", "text": "claro"},
             {"id": "t3", "t": 8.5, "who": "them", "text": more}, {"id": "t4", "t": 16.0, "who": "you", "text": "sí"},
             {"id": "t5", "t": 16.5, "who": "them", "text": "entonces con quien tienes que hablar es con Alejandro y con Andrés"},
             {"id": "t6", "t": 21.0, "who": "you", "text": "perfecto, pues hablo con Alejandro y con Andrés esta misma semana, gracias"}]
    got = moments(turns, {"t1": {"finished": True, "objection": "none"}, "t3": {"finished": True, "objection": "none"},
                          "t5": {"finished": True, "objection": "none"}})
    assert got[0][1] == "them_mid" and got[0][0] < 16.0  # read after the pain, not at the end of the intervention
    assert [r for _, r in got][-1] == "them_end"


def test_the_card_limit_is_35_words():
    # A good 31-word card was cut at 25 words.
    from evals.strategic import run_turns  # noqa: F401  (sets the limit)
    from evals.strategic import run_v2 as v2

    assert v2.MAX_CARD_WORDS == 35
