"""The LLM repair lists misheard words and code decides which of them are applied.

Whatever the model answers (nothing, garbage, an invented rewrite, a runaway), the transcript is
either improved by small, phonetically close fixes or left exactly as it was."""

import asyncio
import random

import pytest

from app.config import settings
from app.services import transcript_patch as tp
from app.services.session_entities import EntityTerm
from app.services.transcript_turns import parse_transcript_turns, serialize_transcript_turns

TRANSCRIPT = (
    "SPEAKER: S1\nHola Marc, soy Toni de Voicify, te llamo por el tema de las tocadas y el CRM.\n\n"
    "SPEAKER: S2\nSí, ahora usamos Pipedrive y Edenred, pero estamos mirando alternativas.\n\n"
    "SPEAKER: S1\nPerfecto, te paso un mail a marc punto buchet arroba matheu punto com con la propuesta.\n\n"
    "SPEAKER: S2\nVale, gracias. Hablamos el jueves."
)


def _terms(*names):
    return [EntityTerm(canonical=n, aliases=(), kind="glossary") for n in names]


def _ctx(terms=("Marc Buchet", "Edenred"), roles=None, two_party=True):
    return tp.PatchContext.build(_terms(*terms), roles or {"rep_name": "Toni"}, two_party)


TURNS = parse_transcript_turns(TRANSCRIPT)


def _patch(*pairs, i=0):
    return {"changes": [{"i": i, "replace": [list(p) for p in pairs]}]}


def _accepted(payload, ctx=None, turns=TURNS):
    acc, _ = tp.validate_patch(turns, payload, ctx or _ctx())
    return [(a, b) for _, a, b in acc]


def _reasons(payload, ctx=None, turns=TURNS):
    return [r for _, _, r in tp.validate_patch(turns, payload, ctx or _ctx())[1]]


# --- the model's answer is not what we asked for --------------------------------------------

@pytest.mark.parametrize("payload", [
    None, "oops not json", 42, [], {}, {"changes": "x"}, {"changes": None}, {"changes": {"i": 0}},
    {"changes": [None, 1, "x", []]}, {"turns": []},
])
def test_an_answer_of_the_wrong_shape_changes_nothing(payload):
    acc, _ = tp.validate_patch(TURNS, payload, _ctx())
    assert acc == []


@pytest.mark.parametrize("change", [
    {"i": 99, "replace": [["a", "b"]]}, {"i": -1, "replace": [["a", "b"]]}, {"i": "0", "replace": [["Voicify", "Vocify"]]},
    {"i": True, "replace": [["Voicify", "Vocify"]]}, {"i": 0}, {"i": 0, "replace": "Voicify"},
    {"i": 0, "replace": [["Voicify"]]}, {"i": 0, "replace": [[1, 2]]}, {"i": 0, "replace": [None]},
])
def test_a_malformed_change_is_dropped(change):
    assert _accepted({"changes": [change]}) == []


def test_text_that_is_not_in_the_turn_is_dropped():
    assert _accepted(_patch(("Buenos días", "Hola"))) == []
    assert _reasons(_patch(("Buenos días", "Hola"))) == ["not_in_turn"]


def test_many_changed_turns_in_a_call_with_few_long_turns_are_fine():
    turns = [{"speaker": "S1", "text": f"Hablamos de Voicify en el punto {n}."} for n in "abcdefghij"]
    payload = {"changes": [{"i": n, "replace": [["Voicify", "Vocify"]]} for n in range(9)]}
    assert len(_accepted(payload, turns=turns)) == 9


def test_a_flood_of_changed_turns_is_refused_whole():
    flood = {"changes": [{"i": 0, "replace": [["Voicify", "Vocify"]]}] * 40}
    assert _accepted(flood) == []
    assert _reasons(flood)[0].startswith("too_many_changed_turns")


def test_random_garbage_never_raises_or_touches_text_that_is_not_there():
    rng = random.Random(7)
    junk = [None, True, 0, -3, 2**40, "", "x", "Voicify", "Vocify", ["a"], [], {}, {"i": 0}, [["Voicify", "Vocify"]], 1.5]

    def value(depth=0):
        r = rng.random()
        if depth < 3 and r < 0.3:
            return [value(depth + 1) for _ in range(rng.randint(0, 4))]
        if depth < 3 and r < 0.5:
            return {rng.choice(["i", "replace", "changes", "x"]): value(depth + 1) for _ in range(rng.randint(0, 3))}
        return rng.choice(junk)

    for _ in range(2000):
        payload = {"changes": [{"i": rng.choice([0, 1, 2, 3, 9, "0", None]), "replace": value()} for _ in range(rng.randint(0, 5))]} \
            if rng.random() < 0.7 else value()
        acc, _ = tp.validate_patch(TURNS, payload, _ctx())
        for i, old, new in acc:
            assert old in TURNS[i]["text"] and old != new


# --- the model proposes something wrong -------------------------------------------------------

def test_a_misheard_brand_is_fixed():
    assert _accepted(_patch(("Voicify", "Vocify"))) == [("Voicify", "Vocify")]


def test_a_misheard_word_is_fixed_when_the_right_word_is_used_elsewhere_in_the_call():
    turns = [{"speaker": "S1", "text": "Te llamo por las tocadas. Las llamadas son lo importante, las llamadas."},
             {"speaker": "S2", "text": "Claro, las llamadas."}]
    assert _accepted(_patch(("tocadas", "llamadas")), turns=turns) == [("tocadas", "llamadas")]


def test_a_rewrite_that_means_something_else_is_refused():
    assert _accepted(_patch(("el tema de las tocadas", "la propuesta comercial"))) == []


def test_a_translation_is_refused():
    turns = [{"speaker": "S2", "text": "Tu també vau a treballar amb ells."}]
    assert _accepted(_patch(("Tu també vau a treballar", "Tú también vais a trabajar")), turns=turns) == []


def test_deleting_words_is_refused():
    assert _accepted(_patch(("Hola Marc, ", ""))) == []
    assert "drops_words" in _reasons(_patch(("Hola Marc, soy", "soy")))


def test_a_real_product_name_is_never_rewritten():
    assert _accepted(_patch(("Pipedrive", "Payper"), i=1)) == []
    assert _reasons(_patch(("Pipedrive", "Payper"), i=1)) == ["protected_real_name"]


def test_a_name_is_only_changed_into_a_name_we_know():
    assert _accepted(_patch(("Marc", "Luis"))) == []
    turns = [{"speaker": "S1", "text": "Hola Mark Buchet, te llamo."}]
    assert _accepted(_patch(("Mark Buchet", "Marc Buchet")), turns=turns) == [("Mark Buchet", "Marc Buchet")]
    assert _accepted(_patch(("Mark Buchet", "Mark Bouchard")), turns=turns) == []


def test_a_known_name_still_has_to_sound_like_the_word_it_replaces():
    turns = [{"speaker": "S1", "text": "Trabajamos con Washper desde hace años."}]
    assert _accepted(_patch(("Washper", "Edenred")), turns=turns) == []


def test_the_reps_own_name_is_only_valid_on_the_reps_turns():
    turns = [{"speaker": "S1", "text": "Hola, soy Tony de Vocify."}, {"speaker": "S2", "text": "Hola Tony, qué tal."}]
    ctx = _ctx(terms=(), roles={"rep_name": "Toni"})
    assert _accepted(_patch(("Tony", "Toni"), i=0), ctx, turns) == [("Tony", "Toni")]
    assert _accepted(_patch(("Tony", "Toni"), i=1), ctx, turns) == []


def test_numbers_are_never_changed():
    turns = [{"speaker": "S1", "text": "Tenemos 10 y 4 comerciales en el equipo."}]
    assert _accepted(_patch(("10 y 4", "10 y 45")), turns=turns) == []


def test_a_spelled_email_is_built_from_the_words_that_were_spoken():
    ok = _patch(("marc punto buchet arroba matheu punto com", "marc.buchet@matheu.com"), i=2)
    assert _accepted(ok) == [("marc punto buchet arroba matheu punto com", "marc.buchet@matheu.com")]
    invented = _patch(("marc punto buchet arroba matheu punto com", "marc.buchet@caleidobook.com"), i=2)
    assert _accepted(invented) == []
    leftover = _patch(("marc punto buchet arroba matheu punto com", "marc.punto.buchet@matheu.com"), i=2)
    assert _accepted(leftover) == []


def test_a_patch_that_changes_too_much_is_refused_whole():
    accepted = [(0, "palabra" * 3, "palabras" * 3)] * 12
    assert not tp.within_budget(accepted, total_words=300)
    assert tp.within_budget(accepted[:2], total_words=300)


# --- the call ---------------------------------------------------------------------------------

class FakeLLM:
    """Stands in for LLMClient; `answers` is a list of dicts or exceptions, one per call."""

    calls: list = []
    answers: list = []

    def __init__(self, model=None):
        self.last_call_meta = {}

    async def chat_json(self, messages, **kwargs):
        FakeLLM.calls.append((messages, kwargs))
        answer = FakeLLM.answers.pop(0) if FakeLLM.answers else {"changes": []}
        if isinstance(answer, Exception):
            raise answer
        self.last_call_meta = {"prompt_tokens": 900, "completion_tokens": 40, "provider": "together"}
        return answer


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setattr(settings, "TRANSCRIPT_SANITIZE_LLM", True)
    monkeypatch.setattr("app.services.llm.LLMClient", FakeLLM)
    FakeLLM.calls, FakeLLM.answers = [], []
    return FakeLLM


def run(transcript=TRANSCRIPT, terms=("Marc Buchet",), **kw):
    kw.setdefault("two_party", True)
    return asyncio.run(tp.patch_transcript(transcript, _terms(*terms), {"rep_name": "Toni"}, **kw))


def test_a_good_patch_is_applied_and_nothing_else_changes(llm):
    llm.answers = [_patch(("Voicify", "Vocify"))]
    result = run()
    assert result.text == TRANSCRIPT.replace("Voicify", "Vocify")
    assert result.edits == [("Voicify", "Vocify")]
    assert (result.prompt_tokens, result.completion_tokens, result.provider) == (900, 40, "together")
    assert result.stage_info()["edits_applied"] == 1


def test_its_cost_is_attributed_to_sanitize_under_the_memos_scope(llm, monkeypatch):
    from app.services.usage import usage_scope
    from app.services.usage.scope import current_scope

    seen = []
    original = llm.chat_json

    async def spy(self, messages, **kwargs):
        seen.append(current_scope())
        return await original(self, messages, **kwargs)

    monkeypatch.setattr(llm, "chat_json", spy)
    with usage_scope("extract", memo_id="memo-1", user_id="user-1"):
        run()
    assert [(s.purpose, s.memo_id, s.user_id) for s in seen] == [("sanitize", "memo-1", "user-1")]


def test_the_answer_is_capped_and_bounded_in_time(llm):
    run()
    _, kwargs = llm.calls[0]
    assert kwargs["max_tokens"] == tp.MAX_TOKENS and kwargs["timeout"] == tp.TIMEOUT_S
    assert kwargs["temperature"] == 0.0 and kwargs["max_retries"] == tp.MAX_RETRIES


@pytest.mark.parametrize("answer", [
    RuntimeError("together down"), TimeoutError(), ValueError("Empty model response"),
    ValueError("No JSON object found"), "not a dict", None, {"changes": "garbage"}, {"changes": [{"i": 99}]},
])
def test_when_the_model_fails_or_answers_badly_the_transcript_is_untouched(llm, answer):
    llm.answers = [answer]
    result = run()
    assert result.text == TRANSCRIPT and result.edits == []


def test_one_wrong_edit_does_not_stop_the_good_ones(llm):
    llm.answers = [{"changes": [{"i": 0, "replace": [["Voicify", "Vocify"], ["el tema", "la propuesta"]]},
                                {"i": 1, "replace": [["Pipedrive", "Payper"]]}]}]
    result = run()
    assert result.text == TRANSCRIPT.replace("Voicify", "Vocify")
    assert {r[2] for r in result.rejected} >= {"protected_real_name"}


def test_a_patch_over_the_diff_budget_leaves_the_transcript_untouched(llm):
    names = [a + b for a in "abcdefgh" for b in "xyz"][:20]
    transcript = f"SPEAKER: S1\n{' '.join(f'pala{n}bra' for n in names)}\n\nSPEAKER: S2\n{' '.join(['relleno'] * 40)}"
    llm.answers = [{"changes": [{"i": 0, "replace": [[f"pala{n}bra", f"pala{n}bras"] for n in names[:12]]}]}]
    result = run(transcript)
    assert result.text == transcript
    assert any(r[2].startswith("diff_budget_exceeded") for r in result.rejected)


def test_short_or_unparseable_transcripts_do_not_call_the_model(llm):
    assert run("SPEAKER: S1\nHola.").skipped == "short"
    assert run(TRANSCRIPT.replace("\n\n", "\n \n\n")).skipped == "unparseable"
    assert llm.calls == []


def test_the_switch_turns_it_off(llm, monkeypatch):
    monkeypatch.setattr(settings, "TRANSCRIPT_SANITIZE_LLM", False)
    assert run().skipped == "disabled" and llm.calls == []


def test_a_long_call_is_repaired_in_parallel_windows_with_global_turn_numbers(llm):
    turn = "palabra " * 120
    transcript = serialize_transcript_turns(
        [{"speaker": "S1" if n % 2 == 0 else "S2", "text": f"{turn.strip()} Voicify {n}" if n == 39 else turn.strip()}
         for n in range(40)])
    llm.answers = [{"changes": []}, {"changes": []}, {"changes": []}, {"changes": []}, {"changes": []}]
    run(transcript)
    assert len(llm.calls) > 1
    prompts = [m[1]["content"] for m, _ in llm.calls]
    assert any("[39]" in p for p in prompts) and not all("[0]" in p for p in prompts)


def test_an_edit_proposed_for_a_turn_outside_its_window_is_dropped(llm):
    turn = "palabra " * 120
    transcript = serialize_transcript_turns([{"speaker": "S1", "text": turn.strip()} for _ in range(40)])
    llm.answers = [{"changes": [{"i": 39, "replace": [["palabra", "palabras"]]}]}]
    result = run(transcript)
    assert result.text == transcript  # window 1 holds turns 0-N, so [39] is out of its scope


# --- where it plugs in ------------------------------------------------------------------------

def test_the_stage_records_the_patch_and_two_channel_calls_skip_the_model(monkeypatch):
    from app.services import transcript_sanitize as ts
    from app.services import pipeline_meta

    seen = []
    monkeypatch.setattr(pipeline_meta, "record_stage", lambda name, t0, **info: seen.append((name, info)))

    async def fake(text, terms, roles, **kw):
        assert kw["two_party"] is True
        return tp.PatchResult(text=text.replace("Voicify", "Vocify"), edits=[("Voicify", "Vocify")], model="m", provider="together")

    monkeypatch.setattr(tp, "patch_transcript", fake)
    text, _ = asyncio.run(ts.prepare_transcript_for_extraction_async(TRANSCRIPT, two_party=True, spoken_language="es"))
    assert "Vocify" in text and "Voicify" not in text
    assert seen[-1][0] == "sanitize" and seen[-1][1]["edits_applied"] == 1

    async def boom(*_a, **_k):
        raise AssertionError("model called for a two-channel call")

    monkeypatch.setattr(tp, "patch_transcript", boom)
    asyncio.run(ts.prepare_transcript_for_extraction_async(TRANSCRIPT, speakers_verified=True, spoken_language="es"))
    assert seen[-1][1] == {"skipped": "speakers_verified"}
