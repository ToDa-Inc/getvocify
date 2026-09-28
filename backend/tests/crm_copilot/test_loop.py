from dataclasses import dataclass

import pytest

from app.services.crm_copilot.loop import CopilotTurnResult, run_copilot_turn
from app.services.crm_copilot.tools import OPENAI_TOOLS


@dataclass
class ScriptedLLM:
    responses: list

    async def chat_tools(self, messages, tools, **kwargs):
        del messages, tools, kwargs
        return self.responses.pop(0)


@dataclass
class ToolMsg:
    content: str | None = None
    tool_calls: list | None = None
    raw_message: dict | None = None

    def __post_init__(self):
        self.tool_calls = self.tool_calls or []
        if self.raw_message is None:
            self.raw_message = {
                "role": "assistant",
                "content": self.content,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": "{}"},
                    }
                    for tc in self.tool_calls
                ]
                or None,
            }


@pytest.mark.asyncio
async def test_search_then_text_does_not_extract():
    executed = []

    async def execute(name, args, ctx):
        executed.append(name)
        assert name == "search_contacts"
        return {"contacts": [{"id": "c1", "name": "Marc Boixet", "url": "https://hs/c1"}]}

    llm = ScriptedLLM(
        [
            ToolMsg(
                tool_calls=[{"id": "1", "name": "search_contacts", "arguments": {"query": "Marc"}}]
            ),
            ToolMsg(content="Marc Boixet: https://hs/c1"),
        ]
    )
    result = await run_copilot_turn(
        "qué pasó con Marc Boixet",
        artifacts={},
        llm=llm,
        execute=execute,
        tools=OPENAI_TOOLS,
        system="test",
    )
    assert result.kind == "text"
    assert "https://hs/c1" in result.text
    assert executed == ["search_contacts"]
    assert "extract_sales_update" not in executed
    assert result.state == "idle"


@pytest.mark.asyncio
async def test_apply_write_pauses_for_confirm():
    async def execute(name, args, ctx):
        raise AssertionError(f"must not execute {name} before confirm")

    llm = ScriptedLLM(
        [
            ToolMsg(
                tool_calls=[
                    {
                        "id": "1",
                        "name": "apply_write",
                        "arguments": {"object_type": "contacts", "object_id": "c1", "properties": {"jobtitle": "CEO"}},
                    }
                ]
            )
        ]
    )
    result = await run_copilot_turn(
        "update job title",
        artifacts={},
        llm=llm,
        execute=execute,
        tools=OPENAI_TOOLS,
        system="test",
    )
    assert result.kind == "confirm"
    assert result.state == "waiting_approval"
    assert result.artifacts["copilot"]["pending_tool"] == "apply_write"
    assert "Actualizar" in (result.text or "") or result.text


@pytest.mark.asyncio
async def test_offer_choices_pauses_list():
    async def execute(name, args, ctx):
        raise AssertionError("offer_user_choices is a pause, not a HubSpot call")

    llm = ScriptedLLM(
        [
            ToolMsg(
                tool_calls=[
                    {
                        "id": "1",
                        "name": "offer_user_choices",
                        "arguments": {
                            "prompt": "Which contact?",
                            "choices": [
                                {"id": "pick:contact:1", "label": "Marc Boixet"},
                                {"id": "pick:contact:2", "label": "Marc Other"},
                            ],
                        },
                    }
                ]
            )
        ]
    )
    result = await run_copilot_turn(
        "Marc",
        artifacts={},
        llm=llm,
        execute=execute,
        tools=OPENAI_TOOLS,
        system="test",
    )
    assert result.kind == "choices"
    assert result.state == "waiting_retarget"
    assert result.list_sections
    assert result.artifacts["copilot"]["choices"][0]["id"] == "pick:contact:1"


@pytest.mark.asyncio
async def test_reset_command_clears_session_without_llm():
    async def execute(name, args, ctx):
        raise AssertionError("reset must not call tools")

    llm = ScriptedLLM([])
    result = await run_copilot_turn(
        "nueva conversación",
        artifacts={"copilot": {"last_contact_id": "c1", "messages": [{"role": "user", "content": "old"}]}},
        llm=llm,
        execute=execute,
        tools=OPENAI_TOOLS,
        system="test",
    )
    assert result.kind == "text"
    assert result.state == "idle"
    assert result.artifacts["copilot"] == {"messages": []}
    assert "Sesión nueva" in result.text


@pytest.mark.asyncio
async def test_confirm_true_executes_pending_write():
    executed = []

    async def execute(name, args, ctx):
        executed.append((name, args))
        return {"ok": True, "contact_url": "https://hs/c1"}

    llm = ScriptedLLM([ToolMsg(content="Done. https://hs/c1")])
    artifacts = {
        "copilot": {
            "messages": [],
            "pending_tool": "apply_write",
            "pending_args": {"object_type": "contacts", "object_id": "c1", "properties": {"jobtitle": "CEO"}},
        }
    }
    result = await run_copilot_turn(
        "act:approve",
        artifacts=artifacts,
        llm=llm,
        execute=execute,
        confirm=True,
        tools=OPENAI_TOOLS,
        system="test",
    )
    assert executed[0][0] == "apply_write"
    assert result.kind == "text"
    assert "https://hs/c1" in result.text


@pytest.mark.asyncio
async def test_hollow_apply_write_confirms_note_instead():
    async def execute(name, args, ctx):
        raise AssertionError(f"must not execute {name} before confirm")

    llm = ScriptedLLM(
        [
            ToolMsg(
                tool_calls=[
                    {
                        "id": "1",
                        "name": "apply_write",
                        "arguments": {"memo_id": "m1", "skip_deal": True},
                    }
                ]
            )
        ]
    )
    result = await run_copilot_turn(
        "Les encaja la solución para comerciales de calle",
        artifacts={
            "copilot": {
                "last_contact_id": "864833868997",
                "last_preview_text": "Contacto\nSolo contacto",
                "extraction": {"summary": "Les encaja la solución para sus comerciales de calle."},
            }
        },
        llm=llm,
        execute=execute,
        tools=OPENAI_TOOLS,
        system="test",
    )
    assert result.kind == "confirm"
    assert result.artifacts["copilot"]["pending_tool"] == "create_note"
    assert "Les encaja" in result.text
    assert "Solo contacto" not in result.text
    assert "Actualizar or No actualizar" not in result.text


@pytest.mark.asyncio
async def test_each_visible_tool_is_reported_running_then_done():
    events = []

    async def execute(name, args, ctx):
        if name == "get_contact":
            return {"ok": False, "error": "not_found"}
        return {"contacts": [{"id": "c1"}]}

    llm = ScriptedLLM([
        ToolMsg(tool_calls=[
            {"id": "0", "name": "load_skill", "arguments": {"name": "lookup"}},
            {"id": "1", "name": "search_contacts", "arguments": {"query": "  Marc   Boixet "}},
            {"id": "2", "name": "get_contact", "arguments": {"contact_id": "c1"}},
        ]),
        ToolMsg(content="No lo encuentro."),
    ])
    await run_copilot_turn(
        "qué pasó con Marc", artifacts={}, llm=llm, execute=execute, tools=OPENAI_TOOLS,
        system="test", on_step=events.append,
    )
    # load_skill is bookkeeping, never a step; a search shows what it looked for, never an id.
    assert events == [
        {"tool": "search_contacts", "state": "running", "detail": "Marc Boixet"},
        {"tool": "search_contacts", "state": "done", "detail": "Marc Boixet"},
        {"tool": "get_contact", "state": "running", "detail": ""},
        {"tool": "get_contact", "state": "error", "detail": ""},
    ]


@pytest.mark.asyncio
async def test_a_broken_progress_callback_never_breaks_the_turn():
    def boom(_event):
        raise RuntimeError("ui gone")

    async def execute(name, args, ctx):
        return {"contacts": []}

    llm = ScriptedLLM([
        ToolMsg(tool_calls=[{"id": "1", "name": "search_contacts", "arguments": {"query": "x"}}]),
        ToolMsg(content="Nada."),
    ])
    result = await run_copilot_turn(
        "x", artifacts={}, llm=llm, execute=execute, tools=OPENAI_TOOLS, system="test", on_step=boom,
    )
    assert result.text == "Nada."


@pytest.mark.asyncio
async def test_an_empty_model_answer_is_never_an_english_done():
    from app.services.crm_copilot.loop import EMPTY_ANSWER

    llm = ScriptedLLM([ToolMsg(content="")])
    result = await run_copilot_turn("hola", artifacts={}, llm=llm, execute=None, tools=OPENAI_TOOLS, system="test")
    assert result.text == EMPTY_ANSWER
