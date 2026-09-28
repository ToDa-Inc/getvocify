"""T14: POST /webhooks/recall. Invalid signature -> 403 with no write. bot.status_change
is a no-op ack. bot.done with no reserved capture is a no-op ack. bot.done for a
reserved capture downloads the transcript and completes it through the same
complete_capture path a desktop capture uses, then starts extraction (D5/D8's
run_post_extraction_hooks pipeline, via start_extraction_from_transcript)."""

import base64
import hashlib
import hmac
import json
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-recall-3232b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-recall-3232b")

import httpx
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import webhooks
from app.api.webhooks import router as webhooks_router
from app.config import settings

SECRET_RAW = b"a-shared-secret-32-bytes-long!!!"
SECRET = "whsec_" + base64.b64encode(SECRET_RAW).decode("ascii")
BOT_ID = "bot-99"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self._store, self._table = store, table
        self._filters = []
        self._mode = "select"
        self._payload = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, _n):
        return self

    def update(self, payload):
        self._mode, self._payload = "update", payload
        return self

    def execute(self):
        rows = self._store.setdefault(self._table, [])
        if self._mode == "update":
            updated = []
            for row in rows:
                if all(row.get(c) == v for c, v in self._filters):
                    row.update(self._payload)
                    updated.append(dict(row))
            return _Result(updated)
        filtered = list(rows)
        for c, v in self._filters:
            filtered = [row for row in filtered if row.get(c) == v]
        return _Result(filtered)


class _Supabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _Query(self.tables, name)


def _test_client() -> TestClient:
    app = FastAPI()
    app.include_router(webhooks_router, prefix="/webhooks")
    return TestClient(app)


def _sign(webhook_id: str, ts: str, body: bytes) -> str:
    signed_content = f"{webhook_id}.{ts}.".encode("utf-8") + body
    sig = base64.b64encode(hmac.new(SECRET_RAW, signed_content, hashlib.sha256).digest()).decode("ascii")
    return f"v1,{sig}"


def _memo_row():
    return {
        "id": "memo-1",
        "user_id": "rep-1",
        "company_id": "co-1",
        "client_capture_id": f"recall:{BOT_ID}",
        "source_type": "recall_bot",
        "extraction": None,
    }


def setup_function():
    settings.RECALL_WEBHOOK_SECRET = SECRET
    settings.RECALL_API_KEY = "key-1"


def teardown_function():
    settings.RECALL_WEBHOOK_SECRET = None
    settings.RECALL_API_KEY = None
    settings.ENVIRONMENT = "development"


def test_no_secret_is_403_outside_development():
    settings.RECALL_WEBHOOK_SECRET = None
    settings.ENVIRONMENT = "production"
    supabase = _Supabase({"memos": [_memo_row()]})
    body = json.dumps({"event": "bot.done", "data": {"bot": {"id": BOT_ID}}}).encode("utf-8")
    try:
        with patch("app.api.webhooks.get_supabase", return_value=supabase):
            response = _test_client().post("/webhooks/recall", content=body, headers={"content-type": "application/json"})
        assert response.status_code == 403
    finally:
        settings.ENVIRONMENT = "development"


def test_no_secret_is_accepted_in_development():
    settings.RECALL_WEBHOOK_SECRET = None
    settings.ENVIRONMENT = "development"
    supabase = _Supabase({"memos": []})
    body = json.dumps({"event": "bot.status_change", "data": {"bot": {"id": "bot-x"}}}).encode("utf-8")
    with patch("app.api.webhooks.get_supabase", return_value=supabase):
        response = _test_client().post("/webhooks/recall", content=body, headers={"content-type": "application/json"})
    assert response.status_code == 200


def test_invalid_signature_is_403_and_no_write():
    supabase = _Supabase({"memos": [_memo_row()]})
    body = json.dumps({"event": "bot.done", "data": {"bot": {"id": BOT_ID}}}).encode("utf-8")
    with patch("app.api.webhooks.get_supabase", return_value=supabase):
        response = _test_client().post(
            "/webhooks/recall",
            content=body,
            headers={
                "webhook-id": "msg-1",
                "webhook-timestamp": str(int(time.time())),
                "webhook-signature": "v1,not-the-real-signature",
                "content-type": "application/json",
            },
        )
    assert response.status_code == 403
    assert supabase.tables["memos"][0]["extraction"] is None


def test_bot_status_change_is_a_no_op_ack():
    supabase = _Supabase({"memos": [_memo_row()]})
    body = json.dumps({"event": "bot.status_change", "data": {"bot": {"id": BOT_ID}}}).encode("utf-8")
    ts = str(int(time.time()))
    with patch("app.api.webhooks.get_supabase", return_value=supabase):
        response = _test_client().post(
            "/webhooks/recall",
            content=body,
            headers={
                "webhook-id": "msg-1",
                "webhook-timestamp": ts,
                "webhook-signature": _sign("msg-1", ts, body),
                "content-type": "application/json",
            },
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_bot_done_for_an_unknown_bot_is_a_no_op_ack():
    supabase = _Supabase({"memos": []})
    body = json.dumps({"event": "bot.done", "data": {"bot": {"id": "bot-missing"}}}).encode("utf-8")
    ts = str(int(time.time()))
    with patch("app.api.webhooks.get_supabase", return_value=supabase):
        response = _test_client().post(
            "/webhooks/recall",
            content=body,
            headers={
                "webhook-id": "msg-1",
                "webhook-timestamp": ts,
                "webhook-signature": _sign("msg-1", ts, body),
                "content-type": "application/json",
            },
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@respx.mock
def test_bot_done_downloads_and_completes_the_capture():
    supabase = _Supabase({"memos": [_memo_row()], "user_profiles": []})
    body = json.dumps({"event": "bot.done", "data": {"bot": {"id": BOT_ID}}}).encode("utf-8")
    ts = str(int(time.time()))

    respx.get(f"https://us-west-2.recall.ai/api/v1/bot/{BOT_ID}/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": BOT_ID,
                "recordings": [
                    {"media_shortcuts": {"transcript": {"data": {"download_url": "https://cdn.example/t.json"}}}}
                ],
            },
        )
    )
    respx.get("https://cdn.example/t.json").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "participant": {"name": "Marta"},
                    "words": [{"text": "Hola", "start_timestamp": {"relative": 0.0}, "end_timestamp": {"relative": 0.5}}],
                }
            ],
        )
    )

    fake_extract = AsyncMock()
    with (
        patch("app.api.webhooks.get_supabase", return_value=supabase),
        patch("app.api.memos.start_extraction_from_transcript", fake_extract),
    ):
        response = _test_client().post(
            "/webhooks/recall",
            content=body,
            headers={
                "webhook-id": "msg-1",
                "webhook-timestamp": ts,
                "webhook-signature": _sign("msg-1", ts, body),
                "content-type": "application/json",
            },
        )

    assert response.status_code == 200
    memo = supabase.tables["memos"][0]
    assert memo["transcript"] == "Marta: Hola"
    assert memo["transcript_complete"] is True
    assert memo["capture_turns"][0]["speaker_role"] == "unknown"
    fake_extract.assert_awaited_once()
    args, kwargs = fake_extract.call_args
    assert args[0] == "memo-1"
    assert args[1] == "rep-1"
    assert args[2] == "Marta: Hola"
    assert kwargs["source_type"] == "meeting_transcript"


def test_bot_done_replay_after_already_complete_is_skipped_without_a_recall_call():
    memo = _memo_row()
    memo["transcript_complete"] = True
    memo["transcript"] = "Ya completado"
    supabase = _Supabase({"memos": [memo]})
    body = json.dumps({"event": "bot.done", "data": {"bot": {"id": BOT_ID}}}).encode("utf-8")
    ts = str(int(time.time()))
    with patch("app.api.webhooks.get_supabase", return_value=supabase):
        response = _test_client().post(
            "/webhooks/recall",
            content=body,
            headers={
                "webhook-id": "msg-1",
                "webhook-timestamp": ts,
                "webhook-signature": _sign("msg-1", ts, body),
                "content-type": "application/json",
            },
        )
    assert response.status_code == 200
    # unchanged - proves no download/complete was attempted (no respx route registered
    # for this test, so an attempt would raise ConnectionError, not a clean 200).
    assert supabase.tables["memos"][0]["transcript"] == "Ya completado"


@respx.mock
def test_bot_done_content_conflict_is_acked_not_500():
    memo = _memo_row()
    memo["transcript_complete"] = True
    memo["capture_content_fingerprint"] = None
    supabase = _Supabase({"memos": [memo], "user_profiles": []})
    body = json.dumps({"event": "bot.done", "data": {"bot": {"id": BOT_ID}}}).encode("utf-8")
    ts = str(int(time.time()))

    respx.get(f"https://us-west-2.recall.ai/api/v1/bot/{BOT_ID}/").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": BOT_ID,
                "recordings": [
                    {"media_shortcuts": {"transcript": {"data": {"download_url": "https://cdn.example/t.json"}}}}
                ],
            },
        )
    )
    respx.get("https://cdn.example/t.json").mock(
        return_value=httpx.Response(
            200,
            json=[{"participant": {"name": "Marta"}, "words": [{"text": "Hola"}]}],
        )
    )

    from unittest.mock import patch as _patch
    with (
        patch("app.api.webhooks.get_supabase", return_value=supabase),
        _patch("app.services.meetings.recall_bot.complete_capture") as fake_complete,
    ):
        from app.services.captures import CaptureContentConflict

        fake_complete.side_effect = CaptureContentConflict(
            capture_id="memo-1", memo_id="memo-1", status="processing"
        )
        response = _test_client().post(
            "/webhooks/recall",
            content=body,
            headers={
                "webhook-id": "msg-1",
                "webhook-timestamp": ts,
                "webhook-signature": _sign("msg-1", ts, body),
                "content-type": "application/json",
            },
        )
    assert response.status_code == 200


@respx.mock
def test_bot_done_transcript_fetch_failure_marks_the_capture_failed_not_500():
    supabase = _Supabase({"memos": [_memo_row()], "user_profiles": []})
    body = json.dumps({"event": "bot.done", "data": {"bot": {"id": BOT_ID}}}).encode("utf-8")
    ts = str(int(time.time()))

    respx.get(f"https://us-west-2.recall.ai/api/v1/bot/{BOT_ID}/").mock(
        return_value=httpx.Response(200, json={"id": BOT_ID, "recordings": []})
    )

    with patch("app.api.webhooks.get_supabase", return_value=supabase):
        response = _test_client().post(
            "/webhooks/recall",
            content=body,
            headers={
                "webhook-id": "msg-1",
                "webhook-timestamp": ts,
                "webhook-signature": _sign("msg-1", ts, body),
                "content-type": "application/json",
            },
        )

    assert response.status_code == 200
    memo = supabase.tables["memos"][0]
    assert memo["capture_status"] == "failed"
    assert memo["status"] == "failed"
