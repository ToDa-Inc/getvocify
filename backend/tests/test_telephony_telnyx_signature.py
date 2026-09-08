import base64
import time

import nacl.encoding
import nacl.signing

from app.services.telephony.telnyx_signature import verify_telnyx_signature


def _keys():
    signing = nacl.signing.SigningKey.generate()
    return signing, signing.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()


def _signed(signing, body: bytes, ts: str | None = None):
    timestamp = ts if ts is not None else str(int(time.time()))
    sig = signing.sign(f"{timestamp}|".encode() + body).signature
    return timestamp, base64.b64encode(sig).decode()


def test_accepts_matching_signature():
    signing, pub = _keys()
    ts = str(int(time.time()))
    body = b'{"data":{"event_type":"call.initiated"}}'
    sig = signing.sign(f"{ts}|".encode() + body).signature
    assert verify_telnyx_signature(
        public_key=pub,
        timestamp=ts,
        signature=base64.b64encode(sig).decode(),
        raw_body=body,
    )


def test_accepts_hex_and_base64_public_keys():
    signing = nacl.signing.SigningKey.generate()
    body = b'{"ok":true}'
    ts, signature = _signed(signing, body)
    hex_pub = signing.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()
    b64_pub = signing.verify_key.encode(encoder=nacl.encoding.Base64Encoder).decode()
    assert hex_pub != b64_pub
    assert verify_telnyx_signature(
        public_key=hex_pub,
        timestamp=ts,
        signature=signature,
        raw_body=body,
    )
    assert verify_telnyx_signature(
        public_key=b64_pub,
        timestamp=ts,
        signature=signature,
        raw_body=body,
    )


def test_rejects_tampered_body():
    signing, pub = _keys()
    ts = str(int(time.time()))
    body = b'{"ok":true}'
    sig = signing.sign(f"{ts}|".encode() + body).signature
    assert not verify_telnyx_signature(
        public_key=pub,
        timestamp=ts,
        signature=base64.b64encode(sig).decode(),
        raw_body=b'{"ok":false}',
    )


def test_strips_whitespace_and_quotes_from_public_key():
    signing, pub = _keys()
    ts = str(int(time.time()))
    body = b'{"ok":true}'
    sig = signing.sign(f"{ts}|".encode() + body).signature
    wrapped = f'  "{pub}"\n'
    assert verify_telnyx_signature(
        public_key=wrapped,
        timestamp=ts,
        signature=base64.b64encode(sig).decode(),
        raw_body=body,
    )


def test_rejects_stale_timestamp():
    signing, pub = _keys()
    ts = str(int(time.time()) - 400)
    body = b"{}"
    sig = signing.sign(f"{ts}|".encode() + body).signature
    assert not verify_telnyx_signature(
        public_key=pub,
        timestamp=ts,
        signature=base64.b64encode(sig).decode(),
        raw_body=body,
    )
