"""T14: Recall.ai webhook signature (Svix-style: webhook-id/webhook-timestamp/
webhook-signature, secret prefixed whsec_)."""

import base64
import hashlib
import hmac
import time

from app.services.recall_webhook_signature import verify_recall_webhook_signature

SECRET_RAW = b"a-shared-secret-32-bytes-long!!!"
SECRET = "whsec_" + base64.b64encode(SECRET_RAW).decode("ascii")


def _sign(webhook_id: str, ts: str, body: bytes, secret_bytes: bytes = SECRET_RAW) -> str:
    signed_content = f"{webhook_id}.{ts}.".encode("utf-8") + body
    sig = base64.b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()).decode("ascii")
    return f"v1,{sig}"


def test_accepts_a_signature_recall_would_produce():
    body = b'{"event":"bot.done"}'
    ts = str(int(time.time()))
    header = _sign("msg-1", ts, body)
    assert verify_recall_webhook_signature(
        webhook_id="msg-1", webhook_timestamp=ts, signature_header=header, body=body, secret=SECRET
    ) is True


def test_accepts_when_a_valid_token_is_among_several_space_separated():
    body = b'{"event":"bot.done"}'
    ts = str(int(time.time()))
    good = _sign("msg-1", ts, body)
    header = f"v1,bogus== {good}"
    assert verify_recall_webhook_signature(
        webhook_id="msg-1", webhook_timestamp=ts, signature_header=header, body=body, secret=SECRET
    ) is True


def test_rejects_a_tampered_body():
    ts = str(int(time.time()))
    header = _sign("msg-1", ts, b'{"event":"bot.done"}')
    tampered = b'{"event":"bot.status_change"}'
    assert verify_recall_webhook_signature(
        webhook_id="msg-1", webhook_timestamp=ts, signature_header=header, body=tampered, secret=SECRET
    ) is False


def test_rejects_a_signature_from_a_different_webhook_id():
    body = b'{"event":"bot.done"}'
    ts = str(int(time.time()))
    header = _sign("msg-1", ts, body)
    assert verify_recall_webhook_signature(
        webhook_id="msg-2", webhook_timestamp=ts, signature_header=header, body=body, secret=SECRET
    ) is False


def test_rejects_an_expired_timestamp():
    body = b'{"event":"bot.done"}'
    ts = str(int(time.time()) - 1000)
    header = _sign("msg-1", ts, body)
    assert verify_recall_webhook_signature(
        webhook_id="msg-1", webhook_timestamp=ts, signature_header=header, body=body, secret=SECRET
    ) is False


def test_rejects_wrong_secret():
    body = b'{"event":"bot.done"}'
    ts = str(int(time.time()))
    header = _sign("msg-1", ts, body, secret_bytes=b"a-different-secret-32-bytes-long")
    assert verify_recall_webhook_signature(
        webhook_id="msg-1", webhook_timestamp=ts, signature_header=header, body=body, secret=SECRET
    ) is False


def test_rejects_missing_pieces():
    assert verify_recall_webhook_signature(
        webhook_id="", webhook_timestamp="1", signature_header="v1,x", body=b"{}", secret=SECRET
    ) is False
    assert verify_recall_webhook_signature(
        webhook_id="msg-1", webhook_timestamp="1", signature_header="", body=b"{}", secret=SECRET
    ) is False
    assert verify_recall_webhook_signature(
        webhook_id="msg-1", webhook_timestamp="1", signature_header="v1,x", body=b"{}", secret=""
    ) is False
