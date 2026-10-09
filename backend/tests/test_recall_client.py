"""T14: Recall.ai client (create bot, get bot, download transcript) and the pure
conversion from Recall's per-participant word segments to C01 turns + plain text."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-recall-3232b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-recall-3232b")

import asyncio
import json

import httpx
import pytest
import respx

from app.integrations import recall_client as rc


def test_base_url_for_region_defaults_to_us_west_2():
    assert rc.base_url_for_region(None) == "https://eu-central-1.recall.ai"
    assert rc.base_url_for_region("") == "https://eu-central-1.recall.ai"


def test_base_url_for_region_honors_region():
    assert rc.base_url_for_region("eu-central-1") == "https://eu-central-1.recall.ai"


@respx.mock
def test_create_bot_posts_meeting_url_and_streaming_transcript_config():
    route = respx.post("https://eu-central-1.recall.ai/api/v1/bot/").mock(
        return_value=httpx.Response(201, json={"id": "bot-1", "status": "joining_call"})
    )
    client = rc.RecallClient(api_key="key-1", region="eu-central-1")
    result = asyncio.run(client.create_bot("https://zoom.us/j/123"))

    assert result == {"id": "bot-1", "status": "joining_call"}
    sent = json.loads(route.calls.last.request.content)
    assert sent["meeting_url"] == "https://zoom.us/j/123"
    assert sent["bot_name"] == rc.DEFAULT_BOT_NAME
    assert sent["recording_config"]["transcript"]["provider"] == {"recallai_streaming": {}}
    assert route.calls.last.request.headers["Authorization"] == "Token key-1"


def test_create_bot_without_api_key_raises():
    client = rc.RecallClient(api_key=None, region="eu-central-1")
    with pytest.raises(rc.RecallClientError):
        asyncio.run(client.create_bot("https://zoom.us/j/123"))


@respx.mock
def test_create_bot_error_response_raises_recall_client_error():
    respx.post("https://eu-central-1.recall.ai/api/v1/bot/").mock(
        return_value=httpx.Response(422, text="invalid meeting_url")
    )
    client = rc.RecallClient(api_key="key-1")
    with pytest.raises(rc.RecallClientError):
        asyncio.run(client.create_bot("not-a-url"))


@respx.mock
def test_get_bot_fetches_bot_detail():
    respx.get("https://eu-central-1.recall.ai/api/v1/bot/bot-1/").mock(
        return_value=httpx.Response(200, json={"id": "bot-1", "recordings": []})
    )
    client = rc.RecallClient(api_key="key-1")
    result = asyncio.run(client.get_bot("bot-1"))
    assert result["id"] == "bot-1"


@respx.mock
def test_download_transcript_gets_the_presigned_url_without_recall_auth():
    route = respx.get("https://cdn.example/transcript.json").mock(
        return_value=httpx.Response(200, json=[{"participant": {"name": "Jane"}, "words": []}])
    )
    client = rc.RecallClient(api_key="key-1")
    result = asyncio.run(client.download_transcript("https://cdn.example/transcript.json"))
    assert result == [{"participant": {"name": "Jane"}, "words": []}]
    assert "Authorization" not in route.calls.last.request.headers


def test_transcript_download_url_from_bot_finds_nested_url():
    bot = {
        "recordings": [
            {"media_shortcuts": {"transcript": {"data": {"download_url": None}}}},
            {"media_shortcuts": {"transcript": {"data": {"download_url": "https://cdn.example/t.json"}}}},
        ]
    }
    assert rc.transcript_download_url_from_bot(bot) == "https://cdn.example/t.json"


def test_transcript_download_url_from_bot_is_none_when_not_ready():
    assert rc.transcript_download_url_from_bot({"recordings": []}) is None
    assert rc.transcript_download_url_from_bot({}) is None


SEGMENTS = [
    {
        "participant": {"name": "Marta Vendedora"},
        "words": [
            {"text": "Hola,", "start_timestamp": {"relative": 0.0}, "end_timestamp": {"relative": 0.4}},
            {"text": "buenos días.", "start_timestamp": {"relative": 0.4}, "end_timestamp": {"relative": 1.2}},
        ],
    },
    {
        "participant": {"name": "Cliente Prospecto"},
        "words": [
            {"text": "Buenos días,", "start_timestamp": {"relative": 1.5}, "end_timestamp": {"relative": 2.5}},
        ],
    },
    {"participant": {"name": "Sin palabras"}, "words": []},
]


def test_turns_from_recall_transcript_matches_rep_by_name():
    transcript, turns = rc.turns_from_recall_transcript(SEGMENTS, rep_name="Marta")

    assert len(turns) == 2
    assert turns[0]["speaker_role"] == "rep"
    assert turns[0]["text"] == "Hola, buenos días."
    assert turns[0]["start_ms"] == 0
    assert turns[0]["end_ms"] == 1200
    assert turns[0]["is_final"] is True
    assert turns[1]["speaker_role"] == "prospect"
    assert "Marta Vendedora: Hola, buenos días." in transcript
    assert "Cliente Prospecto: Buenos días," in transcript


def test_turns_from_recall_transcript_without_rep_name_is_unknown_not_a_guess():
    _, turns = rc.turns_from_recall_transcript(SEGMENTS)
    assert all(t["speaker_role"] == "unknown" for t in turns)


def test_turns_from_recall_transcript_matches_full_name_not_just_a_substring():
    segments = [
        {"participant": {"name": "Marta Vendedora"}, "words": [{"text": "Hola"}]},
        {"participant": {"name": "Mariana Cliente"}, "words": [{"text": "Hola"}]},
    ]
    _, turns = rc.turns_from_recall_transcript(segments, rep_name="Marta")
    # "Marta" is a substring of "Mariana" but not the same first name - must not match.
    assert turns[0]["speaker_role"] == "rep"
    assert turns[1]["speaker_role"] == "prospect"


def test_turns_from_recall_transcript_matches_full_name_token_order_independent():
    segments = [{"participant": {"name": "Vendedora Marta"}, "words": [{"text": "Hola"}]}]
    _, turns = rc.turns_from_recall_transcript(segments, rep_name="Marta Vendedora")
    assert turns[0]["speaker_role"] == "rep"


def test_turns_from_recall_transcript_skips_empty_segments():
    _, turns = rc.turns_from_recall_transcript(SEGMENTS, rep_name="Marta")
    # The "Sin palabras" segment has no words and produces no turn.
    assert len(turns) == 2
