# Telnyx Outbound Calling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** With `CALLING_PROVIDER=telnyx`, an SDR places the same Vocify click-to-call they have today, Telnyx parks the WebRTC leg, the server authorizes the CLI and bridges PSTN with dual-channel WAV, and the existing memo/STT/HubSpot pipeline runs unchanged.

**Architecture:** Feature-flagged dual path. Twilio stays the default. Telnyx uses Call Control + Park Outbound Calls (not TeXML). Browser JWT comes from a per-user telephony credential. `customHeaders` are correlation only. `resolve_caller_id` remains the only From authority. Intelligence/transcription are out of scope.

**Tech Stack:** FastAPI, httpx, PyNaCl (Ed25519), existing `twilio` package (Twilio path), pytest; Chrome MV3 offscreen, vendored `@telnyx/webrtc` UMD (`globalThis.TelnyxWebRTC`), `node --test`.

**Spec:** [`docs/superpowers/specs/2026-09-08-telnyx-outbound-calling-design.md`](../specs/2026-09-08-telnyx-outbound-calling-design.md)

## Global Constraints

- Extension has **no bundler**. Vendor `lib/bundle.js` as a classic script. Do not add webpack/vite.
- The client must never choose `From`. Server `resolve_caller_id` + Telnyx `POST /v2/calls` `from` only.
- Dual-channel **WAV** is mandatory (`record_channels=dual`, `record_format=wav`). Never MP3 into STT/HubSpot.
- Do **not** set `bridge_intent` on dial — Telnyx overwrites `from` with the parked leg.
- Emergency numbers must be rejected in the webhook (parking does not apply to 112/911).
- `CALLING_PROVIDER` default is `twilio`. Twilio routes keep working.
- Do not change Deepgram, extraction, or HubSpot call-log semantics except the opaque external id.
- New env vars are `Optional` in `Settings` so the API boots without Telnyx.
- Backend tests: `cd backend && python -m pytest tests/test_<file>.py -v`
- Extension tests: `cd chrome-extension && node --test lib/<file>.test.js`
- Live Telnyx calls are **not** CI. They are Task 8’s acceptance gate and need a Verified (L2) account.

---

## File map

**Create**

- `backend/migrations/029_telnyx_carrier.sql`
- `backend/app/services/telephony/provider.py`
- `backend/app/services/telephony/telnyx_client.py`
- `backend/app/services/telephony/telnyx_signature.py`
- `backend/app/services/telephony/telnyx_credentials.py`
- `backend/app/services/telephony/emergency.py`
- `backend/tests/test_telephony_provider.py`
- `backend/tests/test_telephony_telnyx_signature.py`
- `backend/tests/test_telephony_telnyx_client.py`
- `backend/tests/test_telephony_telnyx_credentials.py`
- `backend/tests/test_telephony_emergency.py`
- `backend/tests/test_telephony_telnyx_webhook.py`
- `chrome-extension/vendor/telnyx-webrtc-2.27.10.bundle.js`
- `chrome-extension/lib/telnyx-headers.js`
- `chrome-extension/lib/telnyx-headers.test.js`
- `scripts/vendor-telnyx-sdk.sh`
- `docs/runbooks/telnyx-setup.md`

**Modify**

- `backend/requirements.txt` — `PyNaCl>=1.5.0`
- `backend/app/config.py` — `CALLING_PROVIDER`, `TELNYX_*`
- `.env.example` — same
- `backend/app/services/telephony/twilio_client.py` — `telephony_configured()` delegates
- `backend/app/services/telephony/caller_id.py` — `verification_sid` + Telnyx verify branch
- `backend/app/services/telephony/call_processor.py` — `carrier_call_id` + Telnyx WAV download
- `backend/app/api/calls.py` — provider-aware token + `provider` on config
- `backend/app/api/webhooks.py` — `/telnyx/voice` JSON handler
- `backend/app/api/hubspot_recordings.py` — `carrier_call_id`
- `chrome-extension/offscreen.html` — Telnyx script tag
- `chrome-extension/offscreen.js` — provider branch
- `chrome-extension/lib/api.js` — pass `provider` through
- `backend/tests/test_telephony_*.py`, `test_calls_history.py` — column rename

---

### Task 1: Schema + provider switch

**Files:**
- Create: `backend/migrations/029_telnyx_carrier.sql`
- Create: `backend/app/services/telephony/provider.py`
- Create: `backend/tests/test_telephony_provider.py`
- Modify: `backend/app/config.py` (after the `TWILIO_*` block ~164–181)
- Modify: `backend/app/services/telephony/twilio_client.py:20-27`
- Modify: `.env.example` after the Twilio block
- Modify every `twilio_call_sid` / `twilio_validation_sid` read/write listed in the File map

**Interfaces:**
- Consumes: existing `settings` object
- Produces:
  - `CallingProvider = Literal["twilio", "telnyx"]`
  - `def calling_provider() -> CallingProvider`
  - `def telephony_configured() -> bool` (canonical; Twilio module re-exports)
  - columns: `outbound_calls.carrier`, `outbound_calls.carrier_call_id`, `user_caller_ids.verification_sid`

- [ ] **Step 1: Write the failing provider test**

```python
# backend/tests/test_telephony_provider.py
from unittest.mock import patch

from app.services.telephony.provider import calling_provider, telephony_configured


def test_default_provider_is_twilio():
    with patch("app.services.telephony.provider.settings") as settings:
        settings.CALLING_PROVIDER = "twilio"
        settings.TWILIO_ACCOUNT_SID = "ACxxx"
        settings.TWILIO_AUTH_TOKEN = "tok"
        settings.TWILIO_API_KEY_SID = "SKxxx"
        settings.TWILIO_API_KEY_SECRET = "sec"
        settings.TWILIO_TWIML_APP_SID = "APxxx"
        settings.TELNYX_API_KEY = None
        settings.TELNYX_PUBLIC_KEY = None
        settings.TELNYX_CONNECTION_ID = None
        assert calling_provider() == "twilio"
        assert telephony_configured() is True


def test_telnyx_needs_key_connection_and_public_key():
    with patch("app.services.telephony.provider.settings") as settings:
        settings.CALLING_PROVIDER = "telnyx"
        settings.TELNYX_API_KEY = "KEY"
        settings.TELNYX_PUBLIC_KEY = "pub"
        settings.TELNYX_CONNECTION_ID = "conn"
        assert telephony_configured() is True
        settings.TELNYX_PUBLIC_KEY = None
        assert telephony_configured() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_telephony_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.telephony.provider`

- [ ] **Step 3: Write migration + provider module + config**

```sql
-- backend/migrations/029_telnyx_carrier.sql
BEGIN;

ALTER TABLE outbound_calls
  ADD COLUMN IF NOT EXISTS carrier TEXT NOT NULL DEFAULT 'twilio';

ALTER TABLE outbound_calls
  RENAME COLUMN twilio_call_sid TO carrier_call_id;

ALTER TABLE user_caller_ids
  RENAME COLUMN twilio_validation_sid TO verification_sid;

DROP INDEX IF EXISTS idx_user_caller_ids_validation_sid;
CREATE INDEX IF NOT EXISTS idx_user_caller_ids_verification_sid
  ON user_caller_ids (verification_sid)
  WHERE verification_sid IS NOT NULL;

ALTER TABLE outbound_calls
  ADD COLUMN IF NOT EXISTS provider_state JSONB NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS user_telephony_credentials (
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  provider TEXT NOT NULL CHECK (provider IN ('telnyx')),
  credential_id TEXT NOT NULL,
  sip_username TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, provider),
  UNIQUE (sip_username)
);

COMMIT;
```

```python
# backend/app/services/telephony/provider.py
from __future__ import annotations

from typing import Literal

from app.config import settings

CallingProvider = Literal["twilio", "telnyx"]


def calling_provider() -> CallingProvider:
    value = (settings.CALLING_PROVIDER or "twilio").strip().lower()
    if value == "telnyx":
        return "telnyx"
    return "twilio"


def telephony_configured() -> bool:
    if calling_provider() == "telnyx":
        return bool(
            settings.TELNYX_API_KEY
            and settings.TELNYX_PUBLIC_KEY
            and settings.TELNYX_CONNECTION_ID
        )
    return bool(
        settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.TWILIO_API_KEY_SID
        and settings.TWILIO_API_KEY_SECRET
        and settings.TWILIO_TWIML_APP_SID
    )
```

Add to `Settings` in `config.py` immediately after the Twilio block:

```python
    CALLING_PROVIDER: str = "twilio"
    TELNYX_API_KEY: Optional[str] = None
    TELNYX_PUBLIC_KEY: Optional[str] = None
    TELNYX_CONNECTION_ID: Optional[str] = None
    TELNYX_OUTBOUND_VOICE_PROFILE_ID: Optional[str] = None
```

Change `twilio_client.telephony_configured` to:

```python
from app.services.telephony.provider import telephony_configured as telephony_configured
```

Replace every Python key `twilio_call_sid` with `carrier_call_id` and `twilio_validation_sid` with `verification_sid` in:

- `backend/app/api/calls.py`
- `backend/app/api/webhooks.py`
- `backend/app/api/hubspot_recordings.py`
- `backend/app/services/telephony/caller_id.py`
- `backend/app/services/telephony/call_processor.py`
- `backend/tests/test_telephony_call_processor.py`
- `backend/tests/test_telephony_caller_id.py`
- `backend/tests/test_telephony_webhook.py`
- `backend/tests/test_calls_history.py`

JSON API field `callSid` stays `callSid` (opaque). Selects that listed `twilio_call_sid` must list `carrier_call_id`.

`.env.example`:

```
CALLING_PROVIDER=twilio
TELNYX_API_KEY=
TELNYX_PUBLIC_KEY=
TELNYX_CONNECTION_ID=
TELNYX_OUTBOUND_VOICE_PROFILE_ID=
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_telephony_provider.py tests/test_telephony_token.py tests/test_telephony_caller_id.py tests/test_telephony_webhook.py tests/test_telephony_call_processor.py tests/test_calls_history.py -v`
Expected: PASS (Twilio behavior unchanged aside from column names)

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/029_telnyx_carrier.sql backend/app/services/telephony/provider.py backend/app/services/telephony/twilio_client.py backend/app/config.py backend/app/api/calls.py backend/app/api/webhooks.py backend/app/api/hubspot_recordings.py backend/app/services/telephony/caller_id.py backend/app/services/telephony/call_processor.py backend/tests .env.example
git commit -m "$(cat <<'EOF'
feat: add calling provider flag and carrier-agnostic call ids

Rename Twilio-branded columns so Telnyx can store its own ids without a second schema.
EOF
)"
```

---

### Task 2: Ed25519 webhook signature + emergency destinations

**Files:**
- Create: `backend/app/services/telephony/telnyx_signature.py`
- Create: `backend/app/services/telephony/emergency.py`
- Create: `backend/tests/test_telephony_telnyx_signature.py`
- Create: `backend/tests/test_telephony_emergency.py`
- Modify: `backend/requirements.txt` (add `PyNaCl>=1.5.0`)

**Interfaces:**
- Consumes: raw body `bytes`, headers, `TELNYX_PUBLIC_KEY`
- Produces:
  - `def verify_telnyx_signature(*, public_key: str, timestamp: str, signature: str, raw_body: bytes, now: int | None = None, max_skew_seconds: int = 300) -> bool`
  - `def is_emergency_destination(e164: str) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_telephony_telnyx_signature.py
import time

import nacl.encoding
import nacl.signing

from app.services.telephony.telnyx_signature import verify_telnyx_signature


def _keys():
    signing = nacl.signing.SigningKey.generate()
    return signing, signing.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()


def test_accepts_matching_signature():
    signing, pub = _keys()
    ts = str(int(time.time()))
    body = b'{"data":{"event_type":"call.initiated"}}'
    sig = signing.sign(f"{ts}|".encode() + body).signature
    import base64
    assert verify_telnyx_signature(
        public_key=pub,
        timestamp=ts,
        signature=base64.b64encode(sig).decode(),
        raw_body=body,
    )


def test_rejects_tampered_body():
    signing, pub = _keys()
    ts = str(int(time.time()))
    body = b'{"ok":true}'
    import base64
    sig = signing.sign(f"{ts}|".encode() + body).signature
    assert not verify_telnyx_signature(
        public_key=pub,
        timestamp=ts,
        signature=base64.b64encode(sig).decode(),
        raw_body=b'{"ok":false}',
    )


def test_rejects_stale_timestamp():
    signing, pub = _keys()
    ts = str(int(time.time()) - 400)
    body = b"{}"
    import base64
    sig = signing.sign(f"{ts}|".encode() + body).signature
    assert not verify_telnyx_signature(
        public_key=pub,
        timestamp=ts,
        signature=base64.b64encode(sig).decode(),
        raw_body=body,
    )
```

```python
# backend/tests/test_telephony_emergency.py
from app.services.telephony.emergency import is_emergency_destination


def test_blocks_eu_and_us_emergency():
    assert is_emergency_destination("+34112")
    assert is_emergency_destination("+911")
    assert is_emergency_destination("112")


def test_allows_spanish_mobile():
    assert not is_emergency_destination("+34600111222")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_telephony_telnyx_signature.py tests/test_telephony_emergency.py -v`
Expected: FAIL import

- [ ] **Step 3: Implement**

Add `PyNaCl>=1.5.0` to `backend/requirements.txt` and `pip install PyNaCl`.

```python
# backend/app/services/telephony/telnyx_signature.py
from __future__ import annotations

import base64
import logging
import time

import nacl.encoding
import nacl.exceptions
import nacl.signing

logger = logging.getLogger(__name__)


def verify_telnyx_signature(
    *,
    public_key: str,
    timestamp: str,
    signature: str,
    raw_body: bytes,
    now: int | None = None,
    max_skew_seconds: int = 300,
) -> bool:
    if not public_key or not timestamp or not signature or raw_body is None:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    clock = now if now is not None else int(time.time())
    if abs(clock - ts) > max_skew_seconds:
        return False
    try:
        verify_key = nacl.signing.VerifyKey(public_key, encoder=nacl.encoding.HexEncoder)
        verify_key.verify(
            f"{timestamp}|".encode("utf-8") + raw_body,
            base64.b64decode(signature),
        )
        return True
    except (nacl.exceptions.BadSignatureError, ValueError, TypeError) as exc:
        logger.warning("Telnyx signature validation error: %s", exc)
        return False
```

```python
# backend/app/services/telephony/emergency.py
from __future__ import annotations

import re

_DIGITS = re.compile(r"\D+")

# National emergency / priority services we must never originate.
# Parking does not apply to 112/911; the browser From would leak.
_EMERGENCY_NATIONAL = frozenset(
    {
        "112",
        "911",
        "999",
        "000",
        "110",
        "119",
        "061",
        "062",
        "080",
        "091",
        "092",
        "016",
    }
)


def is_emergency_destination(raw: str) -> bool:
    digits = _DIGITS.sub("", raw or "")
    if not digits:
        return False
    if digits in _EMERGENCY_NATIONAL:
        return True
    # +34 112 / +1 911 after a country prefix
    for code in _EMERGENCY_NATIONAL:
        if digits.endswith(code) and len(digits) <= len(code) + 3:
            return True
    return False
```

If Telnyx’s Mission Control public key is **base64** rather than hex, extend `verify_telnyx_signature` to try HexEncoder then Base64Encoder. Cover both in the test by encoding the same verify key both ways.

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_telephony_telnyx_signature.py tests/test_telephony_emergency.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/app/services/telephony/telnyx_signature.py backend/app/services/telephony/emergency.py backend/tests/test_telephony_telnyx_signature.py backend/tests/test_telephony_emergency.py
git commit -m "$(cat <<'EOF'
feat: verify Telnyx Ed25519 webhooks and block emergency destinations

Signature covers timestamp plus raw body so the proxy host cannot break auth.
EOF
)"
```

---

### Task 3: Telnyx HTTP client + per-user credentials + token mint

**Files:**
- Create: `backend/app/services/telephony/telnyx_client.py`
- Create: `backend/app/services/telephony/telnyx_credentials.py`
- Create: `backend/tests/test_telephony_telnyx_client.py`
- Create: `backend/tests/test_telephony_telnyx_credentials.py`
- Modify: `backend/app/api/calls.py` (`get_calling_config`, `create_voice_token`)

**Interfaces:**
- Consumes: `TELNYX_API_KEY`, `TELNYX_CONNECTION_ID`, `user_telephony_credentials`
- Produces:
  - `class TelnyxClient` with `create_telephony_credential`, `mint_credential_token`, `create_verified_number`, `verify_number_code`, `dial`, `speak`, `bridge`, `hangup`, `get_recording`
  - `def ensure_user_credential(supabase, user_id: str) -> dict` → `{credentialId, sipUsername}`
  - `def mint_telnyx_voice_token(supabase, user_id: str) -> dict` → `{token, identity, expiresIn, provider}`
  - `TOKEN_TTL_SECONDS_TELNYX = 24 * 3600`

- [ ] **Step 1: Write the failing client test**

```python
# backend/tests/test_telephony_telnyx_client.py
from unittest.mock import MagicMock, patch

from app.services.telephony.telnyx_client import TelnyxClient


def test_dial_posts_from_chosen_by_server():
    http = MagicMock()
    http.post.return_value.status_code = 200
    http.post.return_value.json.return_value = {
        "data": {"call_control_id": "v3:pstn"}
    }
    http.post.return_value.raise_for_status = lambda: None
    client = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)
    result = client.dial(
        to="+34600111222",
        caller_id="+34600999888",
        link_to="v3:parked",
    )
    assert result["call_control_id"] == "v3:pstn"
    body = http.post.call_args.kwargs["json"]
    assert body["from"] == "+34600999888"
    assert body["to"] == "+34600111222"
    assert body["connection_id"] == "CONN"
    assert "bridge_intent" not in body
    assert body["link_to"] == "v3:parked"
```

```python
# backend/tests/test_telephony_telnyx_credentials.py
from unittest.mock import MagicMock, patch

from app.services.telephony.telnyx_credentials import ensure_user_credential


def test_reuses_existing_row():
    supabase = MagicMock()
    supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {
            "credential_id": "cred-1",
            "sip_username": "userabc",
        }
    ]
    out = ensure_user_credential(supabase, "user-1")
    assert out == {"credentialId": "cred-1", "sipUsername": "userabc"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_telephony_telnyx_client.py tests/test_telephony_telnyx_credentials.py -v`
Expected: FAIL import

- [ ] **Step 3: Implement client, credentials, token route**

```python
# backend/app/services/telephony/telnyx_client.py
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import settings

TELNYX_API = "https://api.telnyx.com/v2"


class TelnyxNotConfigured(RuntimeError):
    pass


class TelnyxClient:
    def __init__(
        self,
        *,
        api_key: str,
        connection_id: str,
        http: Optional[httpx.Client] = None,
    ) -> None:
        self.api_key = api_key
        self.connection_id = connection_id
        self._http = http

    def _client(self) -> httpx.Client:
        if self._http is not None:
            return self._http
        return httpx.Client(
            base_url=TELNYX_API,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        http = self._client()
        response = http.request(method, path, **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def create_telephony_credential(self, name: str) -> dict[str, Any]:
        data = self._request(
            "POST",
            "/telephony_credentials",
            json={"connection_id": self.connection_id, "name": name[:100]},
        )["data"]
        return {
            "credential_id": data["id"],
            "sip_username": data["sip_username"],
        }

    def mint_credential_token(self, credential_id: str) -> str:
        # Telnyx returns the JWT as a raw string body on this endpoint.
        http = self._client()
        response = http.post(f"/telephony_credentials/{credential_id}/token")
        response.raise_for_status()
        text = response.text.strip().strip('"')
        return text

    def create_verified_number(self, phone_number: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/verified_numbers",
            json={"phone_number": phone_number, "verification_method": "call"},
        )

    def verify_number_code(self, phone_number: str, code: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/verified_numbers/{phone_number}/actions/verify",
            json={"verification_code": code},
        )

    def dial(self, *, to: str, caller_id: str, link_to: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "connection_id": self.connection_id,
            "to": to,
            "from": caller_id,
            "link_to": link_to,
            "timeout_secs": 30,
        }
        if settings.TELNYX_OUTBOUND_VOICE_PROFILE_ID:
            payload["outbound_voice_profile_id"] = (
                settings.TELNYX_OUTBOUND_VOICE_PROFILE_ID
            )
        data = self._request("POST", "/calls", json=payload)["data"]
        return {"call_control_id": data["call_control_id"]}

    def speak(self, call_control_id: str, payload: str) -> None:
        self._request(
            "POST",
            f"/calls/{call_control_id}/actions/speak",
            json={"payload": payload, "language": "es-ES", "voice": "female"},
        )

    def bridge(self, parked_id: str, pstn_id: str) -> None:
        self._request(
            "POST",
            f"/calls/{parked_id}/actions/bridge",
            json={
                "call_control_id": pstn_id,
                "record": "record-from-answer",
                "record_channels": "dual",
                "record_format": "wav",
            },
        )

    def hangup(self, call_control_id: str) -> None:
        self._request("POST", f"/calls/{call_control_id}/actions/hangup", json={})

    def get_recording(self, recording_id: str) -> dict[str, Any]:
        return self._request("GET", f"/recordings/{recording_id}")["data"]


def telnyx_rest() -> TelnyxClient:
    if not settings.TELNYX_API_KEY or not settings.TELNYX_CONNECTION_ID:
        raise TelnyxNotConfigured("TELNYX_API_KEY / TELNYX_CONNECTION_ID unset")
    return TelnyxClient(
        api_key=settings.TELNYX_API_KEY,
        connection_id=settings.TELNYX_CONNECTION_ID,
    )
```

`ensure_user_credential`: select `user_telephony_credentials` for `(user_id, 'telnyx')`; if missing, `create_telephony_credential(name=f"vocify-{user_id}")` and insert. `mint_telnyx_voice_token` calls ensure then `mint_credential_token`.

In `calls.py`:

- `get_calling_config` returns `"provider": calling_provider()` and, when Telnyx, calls `ensure_user_credential` so the 5 s settle happens before click-to-call.
- `create_voice_token`: if `calling_provider() == "telnyx"`, return `{token, identity: user_id, expiresIn: 86400, provider: "telnyx"}`; else existing Twilio mint plus `"provider": "twilio"`.

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_telephony_telnyx_client.py tests/test_telephony_telnyx_credentials.py tests/test_telephony_token.py tests/test_telephony_provider.py -v`
Expected: PASS. Add a token test that Telnyx mint does not call Twilio `AccessToken`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/telephony/telnyx_client.py backend/app/services/telephony/telnyx_credentials.py backend/app/api/calls.py backend/tests/test_telephony_telnyx_client.py backend/tests/test_telephony_telnyx_credentials.py backend/tests/test_telephony_token.py
git commit -m "$(cat <<'EOF'
feat: mint Telnyx WebRTC JWTs from per-user telephony credentials

Provision the credential on config load so click-to-call does not hit the 5s settle window.
EOF
)"
```

---

### Task 4: Telnyx verified caller ID

**Files:**
- Modify: `backend/app/services/telephony/caller_id.py` (`start_caller_id_verification`)
- Modify: `backend/app/api/calls.py` (`create_caller_id` docstring / Telnyx code confirm)
- Create or extend: `POST /api/v1/calls/caller-ids/confirm` if Telnyx requires a typed OTP (Twilio types DTMF on the phone; Telnyx `actions/verify` is a second API call)
- Modify: `backend/tests/test_telephony_caller_id.py`

**Interfaces:**
- Consumes: `TelnyxClient.create_verified_number`, `verify_number_code`
- Produces: same JSON as today `{phoneNumber, verificationCode, status, validationSid, alreadyVerified}` plus optional `needsCodeSubmit: true` on Telnyx
- `start_caller_id_verification` stores `verification_sid` from Telnyx’s verification id when present, else the E.164 (Telnyx verify is keyed by number)

Telnyx flow: `POST /v2/verified_numbers` sends OTP; user hears/reads code; client must `POST /v2/verified_numbers/{n}/actions/verify`. Twilio types the code on the keypad — different UX. Add:

```python
# calls.py
class CallerIdConfirmRequest(BaseModel):
    phoneNumber: str
    code: str = Field(min_length=4, max_length=12)


@router.post("/caller-ids/confirm")
async def confirm_caller_id(...):
    # Telnyx only. Twilio confirm is the keypad on the verification call.
```

On success: `user_caller_ids.status = verified`, `verified_at = now()`.

- [ ] **Step 1: Write the failing test**

```python
def test_telnyx_start_persists_pending_without_inventing_a_code():
    # calling_provider() == "telnyx"
    # mock create_verified_number → 200
    # assert result["needsCodeSubmit"] is True
    # assert "verificationCode" not in result or result["verificationCode"] is None
    # assert row status == "pending"
```

The OTP arrives on the handset (SMS or voice). The existing caller-ID UI already collects a code for Twilio’s keypad call — reuse that field to call `POST /caller-ids/confirm`. Never invent or echo a code the API did not return.

- [ ] **Step 2: Run test — expect FAIL**
- [ ] **Step 3: Implement branch in `start_caller_id_verification`**

```python
if calling_provider() == "telnyx":
    telnyx_rest().create_verified_number(phone_number)
    # upsert pending, verification_sid = phone_number
    return {
        "phoneNumber": phone_number,
        "status": "pending",
        "needsCodeSubmit": True,
        "alreadyVerified": False,
    }
# existing Twilio path
```

- [ ] **Step 4: pytest `tests/test_telephony_caller_id.py tests/test_telephony_token.py -v`** — PASS
- [ ] **Step 5: Commit** `feat: verify caller IDs through Telnyx Verified Numbers`

---

### Task 5: Park webhook state machine

**Files:**
- Modify: `backend/app/api/webhooks.py` (add routes after the Twilio block)
- Create: `backend/tests/test_telephony_telnyx_webhook.py`

**Interfaces:**
- Consumes: `verify_telnyx_signature`, `resolve_caller_id`, `normalize_e164`, `is_emergency_destination`, `TelnyxClient`, `user_telephony_credentials`
- Produces: `POST /webhooks/telnyx/voice` (JSON). Events handled:
  - `call.initiated` + `state=parked` → authorize, insert `outbound_calls`, `dial`
  - `call.answered` on PSTN → optional `speak`, else `bridge`
  - `call.speak.ended` / `call.playback.ended` → `bridge`
  - `call.hangup` on PSTN with cause ≠ normal_clearing before recorded → `log_missed_call_activity`
  - `call.recording.saved` → Task 6

`outbound_calls.provider_state` (added in Task 1) stores `{"parked_id":"v3:…","pstn_id":"v3:…"}`.

Lookup user:

```python
def user_id_from_parked_payload(supabase, payload: dict) -> str | None:
    sip = (payload.get("from") or "").strip()
    rows = (
        supabase.table("user_telephony_credentials")
        .select("user_id")
        .eq("provider", "telnyx")
        .eq("sip_username", sip)
        .limit(1)
        .execute()
        .data
    ) or []
    return str(rows[0]["user_id"]) if rows else None
```

Header helper:

```python
def _header(payload: dict, name: str) -> str:
    for item in payload.get("custom_headers") or []:
        if (item.get("header_name") or "").lower() == name.lower():
            return item.get("header_value") or ""
    return ""
```

Parked handler (authoritative sequence):

```python
to_number = normalize_e164(payload["to"], settings.CALLING_DEFAULT_COUNTRY_CODE)
if is_emergency_destination(to_number):
    telnyx_rest().hangup(payload["call_control_id"])
    return Response(status_code=204)
caller_id = resolve_caller_id(supabase, user_id, _header(payload, "X-Vocify-Caller-Id") or None)
# insert outbound_calls carrier=telnyx, carrier_call_id=parked call_control_id
# ContactId/DealId from headers, never trusted for auth
pstn = telnyx_rest().dial(
    to=to_number,
    caller_id=caller_id,
    link_to=payload["call_control_id"],
)
# save pstn_id in provider_state
```

Webhook entry:

```python
@router.post("/telnyx/voice")
async def telnyx_voice(request: Request):
    raw = await request.body()
    if not verify_telnyx_signature(
        public_key=settings.TELNYX_PUBLIC_KEY or "",
        timestamp=request.headers.get("telnyx-timestamp", ""),
        signature=request.headers.get("telnyx-signature-ed25519", ""),
        raw_body=raw,
    ):
        return PlainTextResponse("Forbidden", status_code=403)
    event = json.loads(raw.decode("utf-8"))
    # dispatch on event["data"]["event_type"]
    return Response(status_code=204)
```

- [ ] **Step 1: Fixture + tests**

Use a parked `call.initiated` fixture (from Telnyx outbound-dialer docs) with `custom_headers` and `from` = sip username. Tests:

1. Bad signature → 403, `dial` not called
2. Unknown sip → hangup parked, no insert
3. Emergency `to` → hangup, no dial
4. Unverified CLI → hangup, no dial
5. Happy parked → insert + `dial(from=resolved CLI)` and **no** `bridge_intent`
6. `call.answered` + announcement off → `bridge` with `record_format=wav`, `record_channels=dual`

- [ ] **Step 2: Run — expect FAIL**
- [ ] **Step 3: Implement dispatcher in `webhooks.py`**
- [ ] **Step 4: `pytest tests/test_telephony_telnyx_webhook.py tests/test_telephony_webhook.py -v`** — both suites PASS
- [ ] **Step 5: Commit** `feat: park-and-bridge Telnyx outbound calls with server-chosen CLI`

---

### Task 6: Recording download into the existing memo pipeline

**Files:**
- Modify: `backend/app/services/telephony/call_processor.py`
- Modify: `backend/app/api/webhooks.py` (`call.recording.saved` branch)
- Modify: `backend/tests/test_telephony_call_processor.py`

**Interfaces:**
- Consumes: `TelnyxClient.get_recording` → `download_urls.wav`
- Produces: `async def download_telnyx_recording(recording_id: str) -> bytes` then existing `upload_call_recording` / `initiate_vocify_call_memo` / `process_vocify_call_background`

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_download_telnyx_recording_uses_wav_url(httpx_mock):
    # mock GET /v2/recordings/rec-1 -> download_urls.wav
    # mock GET wav url with Bearer -> b"RIFF...."
    audio = await download_telnyx_recording("rec-1")
    assert audio.startswith(b"RIFF")
```

Webhook test: `call.recording.saved` with `call_control_id` matching `carrier_call_id` **or** `provider_state.parked_id` / `pstn_id` — look up with `.or_`. Prefer matching `carrier_call_id` to the parked id (the row we inserted) and also try payload `call_session_id` if Telnyx records against the PSTN leg. Implementation rule: update lookup to

```python
def find_outbound_call(supabase, payload: dict):
    candidates = [
        payload.get("call_control_id"),
        (payload.get("client_state") or ""),
    ]
    # plus provider_state contains pstn_id
    for cid in [c for c in candidates if c]:
        rows = supabase.table("outbound_calls").select("*").eq("carrier_call_id", cid).limit(1).execute().data
        if rows:
            return rows[0]
    rows = (
        supabase.table("outbound_calls")
        .select("*")
        .contains("provider_state", {"pstn_id": payload.get("call_control_id")})
        .limit(1)
        .execute()
        .data
    )
    return (rows or [None])[0]
```

Download with `httpx.AsyncClient(headers={"Authorization": f"Bearer {settings.TELNYX_API_KEY}"})`. If 403/404, `get_recording` once and retry the new `download_urls.wav`. 10-minute expiry is why the retry exists.

If `download_urls.wav` is missing, fail — do not fall back to mp3.

- [ ] **Step 2–4:** implement, pytest PASS including existing Twilio download tests
- [ ] **Step 5: Commit** `feat: ingest Telnyx dual-channel WAV into the vocify_call memo pipeline`

---

### Task 7: Chrome extension Telnyx device

**Files:**
- Create: `scripts/vendor-telnyx-sdk.sh`
- Create: `chrome-extension/vendor/telnyx-webrtc-2.27.10.bundle.js` (generated)
- Create: `chrome-extension/lib/telnyx-headers.js`
- Create: `chrome-extension/lib/telnyx-headers.test.js`
- Modify: `chrome-extension/offscreen.html`
- Modify: `chrome-extension/offscreen.js`
- Modify: `chrome-extension/lib/api.js` if token payload needs passing `provider`
- Modify: `chrome-extension/background.js` token refresh (Telnyx JWT is 24 h; still refresh on `telnyx.error` auth failures)

**Interfaces:**
- Consumes: `/calls/config.provider`, `/calls/token.{token,provider}`
- Produces: same `CALL_STATE` messages the popup already understands

```javascript
// chrome-extension/lib/telnyx-headers.js
export function vocifyCallHeaders({ callerId, contactId, dealId }) {
  const headers = [];
  if (callerId) headers.push({ name: 'X-Vocify-Caller-Id', value: String(callerId) });
  if (contactId) headers.push({ name: 'X-Vocify-Contact-Id', value: String(contactId) });
  if (dealId) headers.push({ name: 'X-Vocify-Deal-Id', value: String(dealId) });
  return headers;
}
```

`scripts/vendor-telnyx-sdk.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
VER="${1:-2.27.10}"
DEST="chrome-extension/vendor/telnyx-webrtc-${VER}.bundle.js"
curl -fsSL "https://unpkg.com/@telnyx/webrtc@${VER}/lib/bundle.js" -o "$DEST"
```

`offscreen.html`:

```html
<script src="vendor/twilio-voice-2.18.3.min.js"></script>
<script src="vendor/telnyx-webrtc-2.27.10.bundle.js"></script>
<script src="offscreen.js" type="module"></script>
```

`startCall` becomes:

```javascript
async function startCall({ token, to, callerId, contactId, dealId, provider }) {
  if (provider === 'telnyx') {
    return startTelnyxCall({ token, to, callerId, contactId, dealId });
  }
  return startTwilioCall({ token, to, callerId, contactId, dealId });
}

async function startTelnyxCall({ token, to, callerId, contactId, dealId }) {
  const TelnyxRTC = globalThis.TelnyxWebRTC?.TelnyxRTC;
  if (!TelnyxRTC) throw new Error('Telnyx WebRTC SDK no cargado');
  const client = new TelnyxRTC({ login_token: token });
  await new Promise((resolve, reject) => {
    client.on('telnyx.ready', resolve);
    client.on('telnyx.error', reject);
    client.connect();
  });
  const remote = document.getElementById('telnyx-remote') || document.body.appendChild(Object.assign(document.createElement('audio'), { id: 'telnyx-remote', autoplay: true }));
  const call = client.newCall({
    destinationNumber: to,
    audio: true,
    remoteElement: remote, // per-call, not session-level
    customHeaders: vocifyCallHeaders({ callerId, contactId, dealId }),
  });
  // map call states → reportCallState RINGING / ACTIVE / IDLE
}
```

Background: when fetching the token, pass `provider` into the offscreen `startCall` message. Do not send `callerNumber` as the presented CLI.

- [ ] **Step 1:** `telnyx-headers.test.js` with `node --test`
- [ ] **Step 2:** fail (module missing)
- [ ] **Step 3:** implement + vendor script
- [ ] **Step 4:** `cd chrome-extension && node --test lib/telnyx-headers.test.js` PASS; existing dialer tests PASS
- [ ] **Step 5: Commit** `feat: place parked WebRTC calls through the Telnyx SDK in the offscreen doc`

---

### Task 8: Runbook + live acceptance gate

**Files:**
- Create: `docs/runbooks/telnyx-setup.md`
- Modify: `docs/telephony/DECISION.md` — one paragraph at the top pointing at this plan (cost swap, not CLI fix)
- Modify: `docs/telephony/telnyx/README.md` — “implementation in progress” + link

Runbook must include, in order:

1. Upgrade Mission Control to **Verified (L2)**. Paid limits cannot pilot a team.
2. Create Credential Connection. Auth type credentials. Webhook `https://<BACKEND_PUBLIC_URL>/webhooks/telnyx/voice`, API v2.
3. PATCH connection: `outbound.call_parking_enabled=true`, attach Outbound Voice Profile with Spain enabled.
4. Copy API key, connection id, Ed25519 public key into env. `CALLING_PROVIDER=telnyx`.
5. Apply migration 029.
6. Verify one real +34 number (`POST /v2/verified_numbers`). If it 4xx, stop — do not ship BYO for that country.
7. Place one answered call. Confirm: audio both ways, disclosure only on callee if flag on, dual WAV in Supabase, memo created, HubSpot engagement.
8. Read CDR `cost` for that call. Write the number in the runbook (do not invent a band).
9. Photograph/note handset CLI. Connected ≠ delivered.
10. After a week of staging, compute share of calls ≤6 s. If >15%, talk to Telnyx about SDC before production.

- [ ] **Step 1:** Write the runbook with the checklist above (no live secrets)
- [ ] **Step 2:** Manual gate — do not mark this task done without steps 6–9
- [ ] **Step 3: Commit** `docs: add Telnyx Mission Control setup and live acceptance gate`

---

## Self-review

**Spec coverage**

| Spec section | Task |
|---|---|
| Provider switch | 1 |
| Schema rename + credentials table | 1, 3 |
| Ed25519 + raw body | 2 |
| Emergency block | 2, 5 |
| Per-user credential + JWT | 3 |
| Verified Numbers | 4 |
| Park → dial → speak → bridge WAV | 5 |
| Recording → existing pipeline | 6 |
| MV3 UMD offscreen | 7 |
| L2 + CDR + SDC + handset CLI | 8 |
| Non-goals (STT, Managed Accounts, TeXML, hard cutover) | omitted on purpose |

**Type consistency:** `carrier_call_id`, `verification_sid`, `calling_provider()`, `TelnyxClient.dial(to=, caller_id=, link_to=)`, headers `X-Vocify-Caller-Id` / `Contact-Id` / `Deal-Id`.

**Not in this plan:** custom storage credentials to Supabase, Managed Accounts, flipping the production default, Spain 400-range DIDs.
