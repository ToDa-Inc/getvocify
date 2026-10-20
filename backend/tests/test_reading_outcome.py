from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.telephony.reading_outcome import apply_reading_outcome, unanswered_outcome

VOICEMAIL = {"call_type": "no_conversation", "call_type_reason": "Solo se oye el buzón de voz."}


class TestUnansweredOutcome:
    def test_reading_that_found_a_voicemail(self):
        assert unanswered_outcome(VOICEMAIL, "hola") == "voicemail"

    def test_voicemail_greeting_in_the_transcript(self):
        assert unanswered_outcome({"call_type": "no_conversation"}, "Deje su mensaje después del tono") == "voicemail"

    def test_nobody_talked_and_no_voicemail_is_no_response(self):
        assert unanswered_outcome({"call_type": "no_conversation", "call_type_reason": "Solo un ¿sí?"}, "¿Sí?") == "no_response"

    def test_a_real_call_is_left_alone(self):
        assert unanswered_outcome({"call_type": "discovery_meeting"}, "buzón de voz") is None
        assert unanswered_outcome(None, "buzón de voz") is None


def _supabase(memo: dict, calls: list[dict]) -> MagicMock:
    supabase = MagicMock()
    table = supabase.table.return_value
    table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [memo]
    table.update.return_value.eq.return_value.execute.return_value.data = calls
    return supabase


@pytest.mark.asyncio
async def test_logged_call_becomes_no_answer_in_hubspot():
    memo = {"user_id": "u1", "source": "vocify_call", "screening_outcome": "connected", "transcript": "x"}
    supabase = _supabase(memo, [{"hubspot_engagement_id": "99"}])
    client = MagicMock(patch=AsyncMock())
    with patch("app.api.crm.get_hubspot_client_from_connection", return_value=client):
        assert await apply_reading_outcome(supabase, "m1", VOICEMAIL) == "voicemail"
    path = client.patch.await_args.args[0]
    props = client.patch.await_args.kwargs["data"]["properties"]
    assert path.endswith("/99")
    assert props == {"hs_call_status": "NO_ANSWER", "hs_call_disposition": "73a0d17f-1163-4015-bdd5-ec830791da20"}


@pytest.mark.asyncio
async def test_call_not_logged_yet_is_left_for_the_logger():
    memo = {"user_id": "u1", "source": "vocify_call", "screening_outcome": None, "transcript": "x"}
    supabase = _supabase(memo, [{"hubspot_engagement_id": None}])
    with patch("app.api.crm.get_hubspot_client_from_connection") as get_client:
        assert await apply_reading_outcome(supabase, "m1", VOICEMAIL) == "voicemail"
    get_client.assert_not_called()


@pytest.mark.asyncio
async def test_memo_already_screened_or_not_a_call_is_untouched():
    for memo in (
        {"user_id": "u1", "source": "vocify_call", "screening_outcome": "voicemail", "transcript": "x"},
        {"user_id": "u1", "source": "voice_memo", "screening_outcome": None, "transcript": "x"},
    ):
        assert await apply_reading_outcome(_supabase(memo, []), "m1", VOICEMAIL) is None

