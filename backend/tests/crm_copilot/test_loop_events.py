"""The loop reports what it is doing, streams when it can, and never changes WhatsApp behavior."""

from dataclasses import dataclass

import pytest

from app.services.crm_copilot.loop import run_copilot_turn
from app.services.crm_copilot.model_profile import request_extra
from app.services.llm.providers.openrouter import ChatToolsResult


def _tool_turn(name="get_contact", args=None, call_id="c1") -> ChatToolsResult:
    return ChatToolsResult(
        content=None,
        tool_calls=[{"id": call_id, "name": name, "arguments": args or {}}],
        raw_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}],
        },
    )


@dataclass
class PlainLLM:
    responses: list
    models: list

    async def chat_tools(self, messages, tools, **kwargs):
        self.models.append(kwargs.get("model"))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@dataclass
class StreamingLLM:
    script: list

    async def chat_tools_stream(self, messages, tools, **kwargs):
        step = self.script.pop(0)
        for delta in step.get("deltas", []):
            yield "delta", delta
        yield "final", step["final"]


class Sink:
    def __init__(self):
        self.events = []

    async def __call__(self, event):
        self.events.append(event)

    def kinds(self):
        return [e["type"] for e in self.events]


@pytest.mark.asyncio
async def test_events_cover_tool_start_result_and_streamed_content():
    async def execute(name, args, ctx):
        return {
            "coverage": "partial",
            "n": 3,
            "evidence": [{"id": "ev-1", "quote": "tres horas"}],
            "contacts": [],
        }

    llm = StreamingLLM(
        [
            {"final": _tool_turn()},
            {"deltas": ["Marina ", "sigue interesada."], "final": ChatToolsResult(content="Marina sigue interesada.")},
        ]
    )
    sink = Sink()
    result = await run_copilot_turn(
        "qué pasó con Marina", artifacts={}, llm=llm, execute=execute, tools=[], on_event=sink, model="m"
    )
    assert result.text == "Marina sigue interesada."
    assert sink.kinds() == ["state", "tool_start", "tool_result", "state", "content", "content"]
    start = sink.events[1]
    assert start["tool"] == "get_contact" and start["call_id"] == "c1"
    done = sink.events[2]
    assert done["ok"] is True and done["coverage"] == "partial" and done["n"] == 3
    assert "contacts" not in done
    assert result.evidence == [{"id": "ev-1", "quote": "tres horas"}]
    assert result.coverages == ["partial"]


@pytest.mark.asyncio
async def test_a_llm_without_streaming_emits_the_whole_text_once():
    llm = PlainLLM([ChatToolsResult(content="Hecho.")], [])
    sink = Sink()
    result = await run_copilot_turn("hola", artifacts={}, llm=llm, tools=[], on_event=sink, model="m")
    assert result.text == "Hecho."
    assert sink.kinds() == ["state", "content"]
    assert sink.events[1]["delta"] == "Hecho."


@pytest.mark.asyncio
async def test_a_failing_tool_reports_ok_false():
    async def execute(name, args, ctx):
        return {"ok": False, "error": "forbidden"}

    llm = PlainLLM([_tool_turn(), ChatToolsResult(content="No puedo verlo.")], [])
    sink = Sink()
    await run_copilot_turn("x", artifacts={}, llm=llm, execute=execute, tools=[], on_event=sink, model="m")
    result_event = next(e for e in sink.events if e["type"] == "tool_result")
    assert result_event["ok"] is False


@pytest.mark.asyncio
async def test_fallback_model_is_used_once_when_the_first_call_fails():
    llm = PlainLLM([RuntimeError("boom"), ChatToolsResult(content="Listo.")], [])
    result = await run_copilot_turn(
        "hola", artifacts={}, llm=llm, tools=[], model="primary", fallback_model="backup"
    )
    assert result.text == "Listo."
    assert llm.models == ["primary", "backup"]


@pytest.mark.asyncio
async def test_without_a_fallback_the_error_propagates():
    llm = PlainLLM([RuntimeError("boom")], [])
    with pytest.raises(RuntimeError):
        await run_copilot_turn("hola", artifacts={}, llm=llm, tools=[], model="primary")


def test_deepseek_reasons_at_low_effort_on_pinned_providers_and_others_keep_low():
    deepseek = request_extra("deepseek/deepseek-v4.1-flash")
    assert deepseek["reasoning"] == {"effort": "low"}
    assert deepseek["provider"] == {"require_parameters": True, "data_collection": "deny"}
    assert deepseek["max_tokens"] == 4096 and request_extra("google/gemini-3.8-flash")["max_tokens"] == 4096  # a bounded call is never refused for a 65k reservation
    assert request_extra("google/gemini-3.8-flash")["reasoning"] == {"effort": "low"}


def _facts_tool(name="objection_breakdown"):
    async def execute(n, a, c):
        return {"coverage": "complete", "n": 14, "items": [{"name": "price", "count": 9}]}
    return execute


@pytest.mark.asyncio
async def test_an_invented_number_triggers_one_rewrite_and_a_content_reset():
    llm = PlainLLM(
        [
            _tool_turn("objection_breakdown"),
            ChatToolsResult(content="Precio: el 64% quedó abierto."),
            ChatToolsResult(content="Precio: 9 de 14 quedaron abiertas."),
        ],
        [],
    )
    sink = Sink()
    result = await run_copilot_turn(
        "¿qué objeción?", artifacts={}, llm=llm, execute=_facts_tool(), tools=[],
        on_event=sink, model="m", verify_numbers=True,
    )
    assert result.text == "Precio: 9 de 14 quedaron abiertas."
    assert "content_reset" in sink.kinds()


@pytest.mark.asyncio
async def test_a_second_failure_drops_the_unverified_sentence():
    llm = PlainLLM(
        [
            _tool_turn("objection_breakdown"),
            ChatToolsResult(content="Hay actividad. Subió un 64%."),
            ChatToolsResult(content="Hay actividad. Subió un 64% otra vez."),
        ],
        [],
    )
    result = await run_copilot_turn(
        "¿qué objeción?", artifacts={}, llm=llm, execute=_facts_tool(), tools=[], model="m", verify_numbers=True
    )
    assert result.text == "Hay actividad."


@pytest.mark.asyncio
async def test_a_turn_with_no_tool_facts_is_not_linted():
    llm = PlainLLM([ChatToolsResult(content="Tienes 5000 contactos.")], [])
    result = await run_copilot_turn("hola", artifacts={}, llm=llm, tools=[], model="m", verify_numbers=True)
    assert result.text == "Tienes 5000 contactos."


@pytest.mark.asyncio
async def test_lint_is_off_by_default_for_whatsapp():
    llm = PlainLLM([_tool_turn(), ChatToolsResult(content="Subió un 64%.")], [])
    result = await run_copilot_turn("x", artifacts={}, llm=llm, execute=_facts_tool(), tools=[], model="m")
    assert result.text == "Subió un 64%."


@pytest.mark.asyncio
async def test_an_empty_session_dict_is_updated_in_place_so_a_first_turn_write_keeps_its_confirmation():
    llm = PlainLLM(
        [_tool_turn("create_note", {"body": "x", "contact_id": "c1"}, call_id="call-9")],
        [],
    )
    session: dict = {}
    result = await run_copilot_turn("nota", artifacts=session, llm=llm, tools=[], model="m")
    assert result.kind == "confirm"
    assert session["copilot"]["pending_tool"] == "create_note"
    assert session["copilot"]["pending_id"] == "call-9"


@dataclass
class RecordingLLM:
    responses: list
    seen: list

    async def chat_tools(self, messages, tools, **kwargs):
        self.seen.append((kwargs.get("model"), [dict(m) for m in messages]))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _reasoned_tool_turn() -> ChatToolsResult:
    turn = _tool_turn()
    turn.raw_message["reasoning_details"] = [{"type": "reasoning.text", "text": "need the stats", "index": 0}]
    return turn


async def _exec(name, args, ctx):
    return {"ok": True}


@pytest.mark.asyncio
async def test_reasoning_is_replayed_within_the_turn_and_never_stored():
    llm = RecordingLLM([_reasoned_tool_turn(), ChatToolsResult(content="Listo.")], [])
    artifacts = {}
    await run_copilot_turn("hola", artifacts=artifacts, llm=llm, execute=_exec, tools=[], model="deepseek/deepseek-v4.1-flash")
    second_call = llm.seen[1][1]
    replayed = [m for m in second_call if m.get("tool_calls")]
    assert replayed and replayed[0]["reasoning_details"][0]["text"] == "need the stats"
    stored = artifacts["copilot"]["messages"]
    assert not any("reasoning_details" in m for m in stored)


@pytest.mark.asyncio
async def test_reasoning_is_dropped_when_the_fallback_model_takes_over():
    llm = RecordingLLM([_reasoned_tool_turn(), RuntimeError("primary down"), ChatToolsResult(content="Listo.")], [])
    await run_copilot_turn(
        "hola", artifacts={}, llm=llm, execute=_exec, tools=[], model="deepseek/deepseek-v4.1-flash", fallback_model="google/gemini-3.8-flash"
    )
    model, messages = llm.seen[2]
    assert model == "google/gemini-3.8-flash"
    assert not any("reasoning_details" in m for m in messages)


@pytest.mark.asyncio
async def test_an_empty_final_message_is_retried_once_instead_of_saying_done():
    llm = RecordingLLM([_tool_turn(), ChatToolsResult(content=""), ChatToolsResult(content="Luis conectó el 18 %.")], [])
    result = await run_copilot_turn("¿tasa de Luis?", artifacts={}, llm=llm, execute=_exec, tools=[], model="m", retry_empty=True)
    assert result.text == "Luis conectó el 18 %."
    assert llm.seen[2][1][-1]["role"] == "user"  # the nudge


@pytest.mark.asyncio
async def test_two_empty_messages_end_in_an_honest_line_in_the_question_language():
    spanish = await run_copilot_turn("¿cuál fue la tasa de conexión?", artifacts={}, llm=RecordingLLM([ChatToolsResult(content=""), ChatToolsResult(content="")], []), execute=_exec, tools=[], model="m", retry_empty=True)
    english = await run_copilot_turn("What was the connection rate in August?", artifacts={}, llm=RecordingLLM([ChatToolsResult(content=""), ChatToolsResult(content="")], []), execute=_exec, tools=[], model="m", retry_empty=True)
    assert spanish.text.startswith("No he encontrado") and english.text.startswith("I could not")


@pytest.mark.asyncio
async def test_the_answer_hint_reaches_the_model_on_the_last_user_turn_but_is_never_stored():
    llm = RecordingLLM([ChatToolsResult(content="Hola.")], [])
    artifacts = {}
    await run_copilot_turn("How many calls?", artifacts=artifacts, llm=llm, execute=_exec, tools=[], model="m", answer_hint="(Answer in English.)")
    sent = llm.seen[0][1]
    assert sent[-1] == {"role": "user", "content": "How many calls?\n\n(Answer in English.)"}
    assert all("(Answer in English.)" not in str(m.get("content")) for m in artifacts["copilot"]["messages"])


def test_web_ask_defaults_to_deepseek_v41_flash_and_retries_it_once(monkeypatch):
    from app.config import settings
    from app.services.crm_copilot import model_profile

    assert settings.ASK_MODEL == "deepseek/deepseek-v4.1-flash" and settings.ASK_FALLBACK_MODEL == "deepseek/deepseek-v4.1-flash"
    monkeypatch.setattr(settings, "ASK_MODEL", "")
    assert model_profile.ask_model() == settings.CRM_COPILOT_MODEL


@pytest.mark.asyncio
async def test_a_fallback_is_logged_so_a_pinned_provider_outage_is_visible(caplog):
    llm = PlainLLM([RuntimeError("No endpoints found matching your data policy"), ChatToolsResult(content="Listo.")], [])
    with caplog.at_level("WARNING"):
        await run_copilot_turn("hola", artifacts={}, llm=llm, tools=[], model="deepseek/deepseek-v4.1-flash", fallback_model="google/gemini-3.8-flash")
    assert any("deepseek/deepseek-v4.1-flash failed" in r.message and "using fallback" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_the_last_round_is_a_plain_answer_from_what_was_found_not_a_dead_end():
    seen_tools = []

    class Counting(RecordingLLM):
        async def chat_tools(self, messages, tools, **kwargs):
            seen_tools.append(list(tools))
            return await super().chat_tools(messages, tools, **kwargs)

    llm = Counting([_tool_turn(), _tool_turn(call_id="c2"), ChatToolsResult(content="Encontré A; no pude determinar B.")], [])
    result = await run_copilot_turn("pregunta", artifacts={}, llm=llm, execute=_exec, tools=[{"type": "function"}], model="m", max_rounds=3)
    assert result.text == "Encontré A; no pude determinar B."
    assert seen_tools[0] and seen_tools[1] and seen_tools[2] == []  # the third and last call has no tools
    assert "no lookups left" in llm.seen[2][1][-1]["content"]


@pytest.mark.asyncio
async def test_a_single_round_turn_keeps_its_tools():
    llm = RecordingLLM([ChatToolsResult(content="Hola.")], [])
    await run_copilot_turn("hola", artifacts={}, llm=llm, execute=_exec, tools=[{"type": "function"}], model="m", max_rounds=1)
    assert "no lookups left" not in str(llm.seen[0][1])


def test_a_finished_question_keeps_its_answer_but_not_the_lookups_behind_it():
    from app.services.crm_copilot.loop import _settle

    history = [{"role": "user", "content": "antes"}, {"role": "assistant", "content": "respuesta antes"}]
    turn = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "{...}"},
        {"role": "assistant", "content": "final"},
    ]
    settled = _settle([*history, *turn], 2)
    assert [m["role"] for m in settled] == ["user", "assistant", "user", "assistant"] and settled[-1]["content"] == "final"
    confirmation = [{"role": "tool", "tool_call_id": "p", "content": "{ok}"}, {"role": "assistant", "content": "hecho"}]
    assert _settle([*history, *confirmation], 2) == [*history, *confirmation]  # would orphan the pending call otherwise


def test_history_is_trimmed_at_a_question_never_between_a_call_and_its_result():
    from app.services.crm_copilot.loop import _trim

    messages = []
    for i in range(6):
        messages += [{"role": "user", "content": f"q{i}"}, {"role": "assistant", "tool_calls": [{"id": f"c{i}"}]}, {"role": "tool", "tool_call_id": f"c{i}"}, {"role": "assistant", "content": f"a{i}"}]
    trimmed = _trim(messages, 10)
    assert trimmed[0]["role"] == "user" and len(trimmed) <= 10
    for index, message in enumerate(trimmed):
        if message["role"] == "tool":
            assert trimmed[index - 1].get("tool_calls"), "a tool result lost its call"


@pytest.mark.asyncio
async def test_a_second_turn_does_not_replay_the_first_turns_tool_results():
    llm = RecordingLLM([_tool_turn(), ChatToolsResult(content="Primera."), ChatToolsResult(content="Segunda.")], [])
    artifacts = {}
    await run_copilot_turn("uno", artifacts=artifacts, llm=llm, execute=_exec, tools=[], model="m")
    await run_copilot_turn("dos", artifacts=artifacts, llm=llm, execute=_exec, tools=[], model="m")
    second_call = llm.seen[-1][1]
    assert not any(m.get("role") == "tool" or m.get("tool_calls") for m in second_call)
    assert [m["content"] for m in second_call if m["role"] in ("user", "assistant")] == ["uno", "Primera.", "dos"]


DSML = "<｜｜DSML｜｜ calls>\n<｜｜DSML｜｜ invoke name=\"crm_call_stats\">\n</｜｜DSML｜｜ invoke>"


@pytest.mark.asyncio
async def test_a_tool_call_written_as_text_is_never_shown_and_is_asked_again():
    llm = StreamingLLM([
        {"deltas": [DSML[:6], DSML[6:]], "final": ChatToolsResult(content=DSML)},
        {"deltas": ["Un 24 %."], "final": ChatToolsResult(content="Un 24 %.")},
    ])
    sink = Sink()
    result = await run_copilot_turn("tasa", artifacts={}, llm=llm, execute=_exec, tools=[], model="deepseek/deepseek-v4.1-flash", on_event=sink)
    assert result.text == "Un 24 %."
    shown = "".join(e.get("delta", "") for e in sink.events if e["type"] == "content")
    assert "DSML" not in shown and shown == "Un 24 %."


@pytest.mark.asyncio
async def test_markup_twice_ends_in_the_honest_empty_answer_line_not_in_garbage():
    llm = PlainLLM([ChatToolsResult(content=DSML), ChatToolsResult(content=DSML), ChatToolsResult(content="")], [])
    result = await run_copilot_turn("What was the rate?", artifacts={}, llm=llm, tools=[], model="m", retry_empty=True)
    assert "DSML" not in result.text and result.text.startswith("I could not")


@pytest.mark.asyncio
async def test_a_short_honest_reply_is_not_mistaken_for_markup():
    llm = StreamingLLM([{"deltas": ["<3", " ok"], "final": ChatToolsResult(content="<3 ok")}])
    sink = Sink()
    result = await run_copilot_turn("hola", artifacts={}, llm=llm, execute=_exec, tools=[], model="m", on_event=sink)
    assert result.text == "<3 ok" and "".join(e.get("delta", "") for e in sink.events if e["type"] == "content") == "<3 ok"


@pytest.mark.asyncio
async def test_the_chosen_effort_is_sent_and_a_turn_that_keeps_failing_is_bumped_to_high(monkeypatch):
    seen = []

    class Spy(RecordingLLM):
        async def chat_tools(self, messages, tools, **kwargs):
            seen.append((kwargs.get("extra") or {}).get("reasoning", {}).get("effort"))
            return await super().chat_tools(messages, tools, **kwargs)

    async def failing(name, args, ctx):
        return {"ok": False, "error": "unknown_property"}

    llm = Spy([_tool_turn(call_id="a"), _tool_turn(call_id="b"), _tool_turn(call_id="c"), ChatToolsResult(content="Listo.")], [])
    await run_copilot_turn("hola", artifacts={}, llm=llm, execute=failing, tools=[], model="m", effort="low")
    assert seen == ["low", "low", "high", "high"]  # two failed lookups, then the third call thinks harder

    seen.clear()
    calm = Spy([ChatToolsResult(content="Listo.")], [])
    await run_copilot_turn("hola", artifacts={}, llm=calm, execute=_exec, tools=[], model="m", effort="high")
    assert seen == ["high"]
