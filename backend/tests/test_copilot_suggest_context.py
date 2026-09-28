import asyncio
from unittest.mock import MagicMock, patch

from app.api import copilot
from app.api.copilot import SuggestRequest, suggest_objection_handling


def _product_context_sent(body: SuggestRequest, saved: str) -> str | None:
    seen: dict = {}

    async def fake_stream(**kwargs):
        seen.update(kwargs)
        yield {"type": "result", "suggestion": {}}

    async def run():
        with (
            patch.object(copilot, "stream_objection_suggestion", fake_stream),
            patch("app.services.extraction_context.load_product_context", return_value=saved),
        ):
            response = await suggest_objection_handling(body, user_id="user-1", supabase=MagicMock())
            async for _ in response.body_iterator:
                pass

    asyncio.run(run())
    return seen["product_context"]


def test_meeting_without_context_uses_the_reps_saved_offer():
    body = SuggestRequest(transcript_window="Them: es caro", latest_turn="es caro", call_mode="meeting")
    assert _product_context_sent(body, "Seguros para flotas") == "Seguros para flotas"


def test_explicit_context_wins():
    body = SuggestRequest(transcript_window="x", latest_turn="x", product_context="Vocify")
    assert _product_context_sent(body, "Seguros para flotas") == "Vocify"


def test_no_saved_offer_sends_none():
    body = SuggestRequest(transcript_window="x", latest_turn="x")
    assert _product_context_sent(body, "") is None
