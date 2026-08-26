# Vocify Outbound Calling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An SDR on a HubSpot contact page clicks "Llamar" in the Vocify side panel, the call goes out with their own verified phone number as caller ID, the conversation is recorded dual-channel, and it lands in HubSpot as a call engagement with a playable recording plus a Vocify memo in the existing review/approve pipeline.

**Architecture:** Twilio Voice JS SDK runs in the extension's existing offscreen document (which already holds `USER_MEDIA`). The browser leg connects to a TwiML App whose Voice URL is a Vocify webhook; that webhook resolves the caller ID server-side from the authenticated Twilio identity and returns `<Dial record="record-from-answer-dual">`. Twilio's recording callback downloads the WAV, stores it in a **private** Supabase bucket, and feeds `transcribe_bytes` → `start_extraction_from_transcript` exactly like `hubspot/call_processor.py`. Vocify then logs the call to HubSpot with `hs_call_source: INTEGRATIONS_PLATFORM` and serves the audio through HubSpot's authenticated-recording pipeline, so **Vocify owns the recording and HubSpot is the consumer** — the inverse of today's `hs_call_recording_url` fetch.

**Tech Stack:** FastAPI, `twilio` Python SDK (AccessToken, VoiceResponse, RequestValidator, REST), Supabase Storage (private bucket + signed URLs), Deepgram batch via existing `stt_batch`, pytest; Chrome MV3 extension (plain ES modules, no bundler), vendored `@twilio/voice-sdk` UMD bundle, `node --test`.

## Global Constraints

- **The extension has no bundler.** `chrome-extension/` is plain ES modules loaded directly; `scripts/package-chrome-extension.sh` rsyncs raw source. Do NOT introduce webpack/rollup/vite. Vendor `@twilio/voice-sdk`'s prebuilt `dist/twilio.min.js` (UMD, exposes `globalThis.Twilio.Device`).
- **Caller ID is always the user's own verified number.** Never a Twilio-purchased number. Outbound only — no number is rented, so no regulatory bundle.
- **The client must never choose its own `From`.** The voice webhook resolves the caller ID from the Twilio `From=client:<user_id>` identity against `user_caller_ids`. A client-supplied caller ID that the user has not verified must be rejected.
- **`record-from-answer-dual` is mandatory, not a preference.** HubSpot's pipeline splits by channel and requires caller on channel 1, recipient on channel 2. Mono recordings will not transcribe.
- **HubSpot accepts only `.WAV`, `.FLAC`, `.MP4`** — never MP3. Download Twilio recordings as `RecordingUrl + ".wav"`.
- **The recording URL served to HubSpot must honour the `Range` header and return `206`.** Supabase Storage signed URLs do this natively; do not build a proxy that breaks it.
- Recordings bucket is **private**. Call audio is personal data under RGPD; a public bucket URL is not acceptable.
- New env vars go in `backend/app/config.py` `Settings` and `/Users/danizal/getvocify/.env.example`. Config import style is `from app.config import settings`.
- Settings must stay optional (`Optional[str] = None`) so the API still boots without Twilio configured, matching `HUBSPOT_CLIENT_ID` etc.
- Backend tests: `cd backend && python -m pytest tests/test_<file>.py -v`
- Extension tests: `cd chrome-extension && node --test lib/<file>.test.js`
- Full suites: `make test` (backend), `make test-js` (extension + dashboard + desktop)
- Memo `source` has a CHECK constraint; `source_type` does not but is validated in `app/services/pipeline_meta.py`. Both need `vocify_call` added.

## Out of scope

Twilio subaccounts per customer, Salesforce call logging, inbound calls / callbacks, the dashboard-side caller-ID settings page (verification lives in the side panel for v1), Telnyx as an alternative carrier, and power/parallel dialing.

## File map

**Create**

- `backend/app/services/telephony/__init__.py`
- `backend/app/services/telephony/twiml.py`
- `backend/app/services/telephony/caller_id.py`
- `backend/app/services/telephony/twilio_client.py`
- `backend/app/services/telephony/webhook_signature.py`
- `backend/app/services/telephony/call_processor.py`
- `backend/app/services/hubspot/call_log.py`
- `backend/app/services/hubspot/calling_settings.py`
- `backend/app/api/calls.py`
- `backend/app/api/hubspot_recordings.py`
- `backend/migrations/024_outbound_calling.sql`
- `backend/tests/test_telephony_twiml.py`
- `backend/tests/test_telephony_caller_id.py`
- `backend/tests/test_telephony_token.py`
- `backend/tests/test_telephony_webhook.py`
- `backend/tests/test_telephony_call_processor.py`
- `backend/tests/test_hubspot_call_log.py`
- `chrome-extension/vendor/twilio-voice-2.18.3.min.js`
- `chrome-extension/lib/dialer.js`
- `chrome-extension/lib/dialer.test.js`
- `scripts/vendor-twilio-sdk.sh`
- `docs/runbooks/twilio-setup.md`

**Modify**

- `backend/requirements.txt` — add `twilio>=9.0.0`
- `backend/app/config.py` — `TWILIO_*` settings
- `backend/app/api/router.py` — include `calls` and `hubspot_recordings` routers
- `backend/app/api/webhooks.py` — Twilio voice / whisper / recording / caller-id-status routes
- `backend/app/services/storage.py` — private call-recording upload + signed URL
- `backend/app/services/pipeline_meta.py` — add `vocify_call` to `_EXTRACTION_SOURCE_TYPES`
- `/Users/danizal/getvocify/.env.example` — `TWILIO_*` placeholders
- `chrome-extension/offscreen.html` — vendored SDK script tag
- `chrome-extension/offscreen.js` — Twilio `Device` lifecycle
- `chrome-extension/background.js` — call state, token fetch, message routing
- `chrome-extension/lib/api.js` — calling endpoints
- `chrome-extension/popup/index.html` — dial UI
- `chrome-extension/popup/popup.js` — dial UI wiring
- `Makefile` — `vendor-twilio` target

---

### Task 1: TwiML builder (pure)

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`
- Modify: `/Users/danizal/getvocify/.env.example`
- Create: `backend/app/services/telephony/__init__.py`
- Create: `backend/app/services/telephony/twiml.py`
- Create: `backend/tests/test_telephony_twiml.py`

**Interfaces:**
- Consumes: `settings` from `app.config`
- Produces:
  - `normalize_e164(raw: str, default_country_code: str = "34") -> str` (raises `InvalidPhoneNumber`)
  - `InvalidPhoneNumber(ValueError)`
  - `build_outbound_twiml(*, to: str, caller_id: str, recording_callback_url: str, whisper_url: str, timeout: int = 30) -> str`
  - `build_whisper_twiml(*, announcement: str, language: str = "es-ES") -> str`
  - `DEFAULT_RECORDING_ANNOUNCEMENT_ES: str`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_telephony_twiml.py`:

```python
import pytest

from app.services.telephony.twiml import (
    InvalidPhoneNumber,
    build_outbound_twiml,
    build_whisper_twiml,
    normalize_e164,
)


class TestNormalizeE164:
    def test_passes_through_e164(self):
        assert normalize_e164("+34600111222") == "+34600111222"

    def test_strips_spaces_dots_and_dashes(self):
        assert normalize_e164("+34 600-111.222") == "+34600111222"

    def test_adds_default_country_code_to_national_number(self):
        assert normalize_e164("600111222") == "+34600111222"

    def test_converts_double_zero_prefix(self):
        assert normalize_e164("0034600111222") == "+34600111222"

    def test_rejects_too_short(self):
        with pytest.raises(InvalidPhoneNumber):
            normalize_e164("600")

    def test_rejects_letters(self):
        with pytest.raises(InvalidPhoneNumber):
            normalize_e164("+34600ABC222")

    def test_rejects_empty(self):
        with pytest.raises(InvalidPhoneNumber):
            normalize_e164("")


class TestBuildOutboundTwiml:
    def _xml(self):
        return build_outbound_twiml(
            to="+34600111222",
            caller_id="+34910000000",
            recording_callback_url="https://api.getvocify.com/webhooks/twilio/recording",
            whisper_url="https://api.getvocify.com/webhooks/twilio/whisper",
        )

    def test_records_dual_channel(self):
        # HubSpot needs one speaker per channel; mono will not transcribe.
        assert 'record="record-from-answer-dual"' in self._xml()

    def test_sets_caller_id_to_the_verified_number(self):
        assert 'callerId="+34910000000"' in self._xml()

    def test_dials_the_target_number(self):
        assert "+34600111222" in self._xml()

    def test_registers_recording_callback_on_completed(self):
        xml = self._xml()
        assert "webhooks/twilio/recording" in xml
        assert 'recordingStatusCallbackEvent="completed"' in xml

    def test_whisper_url_is_on_the_number_not_the_dial(self):
        # The disclosure must play to the prospect, not to the SDR.
        xml = self._xml()
        assert 'url="https://api.getvocify.com/webhooks/twilio/whisper"' in xml
        assert xml.index("<Number") < xml.index("</Dial>")

    def test_answer_on_bridge_so_sdr_hears_ringing_during_whisper(self):
        assert 'answerOnBridge="true"' in self._xml()

    def test_rejects_non_e164_target(self):
        with pytest.raises(InvalidPhoneNumber):
            build_outbound_twiml(
                to="600111222x",
                caller_id="+34910000000",
                recording_callback_url="https://x/r",
                whisper_url="https://x/w",
            )

    def test_rejects_non_e164_caller_id(self):
        with pytest.raises(InvalidPhoneNumber):
            build_outbound_twiml(
                to="+34600111222",
                caller_id="910000000x",
                recording_callback_url="https://x/r",
                whisper_url="https://x/w",
            )


class TestBuildWhisperTwiml:
    def test_says_the_announcement_in_spanish(self):
        xml = build_whisper_twiml(announcement="Esta llamada se graba.")
        assert "Esta llamada se graba." in xml
        assert 'language="es-ES"' in xml

    def test_contains_no_dial_verb(self):
        # Twilio rejects <Dial> inside a Number url document.
        assert "<Dial" not in build_whisper_twiml(announcement="hola")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_telephony_twiml.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.telephony'`

- [ ] **Step 3: Add the dependency and settings**

Append to `backend/requirements.txt`:

```
twilio>=9.0.0
```

Install: `cd backend && pip install -r requirements.txt`

In `backend/app/config.py`, add these fields to `Settings` immediately after the `WHATSAPP_*` block:

```python
    # Twilio outbound calling. Caller ID is always the user's own verified
    # number, so no Twilio number is rented and no regulatory bundle applies.
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_API_KEY_SID: Optional[str] = None
    TWILIO_API_KEY_SECRET: Optional[str] = None
    TWILIO_TWIML_APP_SID: Optional[str] = None
    # AEPD Circular 1/2023: the prospect must be told at the start of the call
    # that it is being recorded, and why. Played to the called party only.
    TWILIO_RECORDING_ANNOUNCEMENT: Optional[str] = None
    TWILIO_ANNOUNCEMENT_LANGUAGE: str = "es-ES"
    # Default country code for national numbers coming from CRM contact fields.
    CALLING_DEFAULT_COUNTRY_CODE: str = "34"
    # Lifetime of the signed recording URL handed to HubSpot.
    CALL_RECORDING_URL_TTL_SECONDS: int = 3600
```

Append to `/Users/danizal/getvocify/.env.example`:

```
# Twilio outbound calling (optional; calling is disabled when unset)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_API_KEY_SID=
TWILIO_API_KEY_SECRET=
TWILIO_TWIML_APP_SID=
TWILIO_RECORDING_ANNOUNCEMENT=
TWILIO_ANNOUNCEMENT_LANGUAGE=es-ES
CALLING_DEFAULT_COUNTRY_CODE=34
CALL_RECORDING_URL_TTL_SECONDS=3600
```

- [ ] **Step 4: Write the implementation**

Create `backend/app/services/telephony/__init__.py` (empty file).

Create `backend/app/services/telephony/twiml.py`:

```python
"""TwiML for Vocify outbound calls.

Pure string generation — no network, no DB, no settings reads. The webhook
resolves identity and caller ID, then asks this module for the XML.

Two documents are produced:

  * the outbound document, returned to the TwiML App's Voice URL, which dials
    the prospect from the SDR's verified number and records dual-channel;
  * the whisper document, returned via the ``<Number url>`` attribute, which
    plays the recording disclosure to the *prospect only* after they answer
    and before the legs are bridged.

`record-from-answer-dual` is a hard requirement, not a preference: HubSpot's
transcription pipeline splits the file by channel and expects the caller on
channel 1 and the recipient on channel 2.
"""

from __future__ import annotations

import re

from twilio.twiml.voice_response import Dial, VoiceResponse

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_SEPARATORS_RE = re.compile(r"[\s().\-/]")

DEFAULT_RECORDING_ANNOUNCEMENT_ES = (
    "Le informamos de que esta llamada se graba y se transcribe para "
    "registrarla en nuestro sistema de gestion comercial. "
    "Si no desea que se grabe, indiquelo y la detendremos."
)


class InvalidPhoneNumber(ValueError):
    """Raised when a number cannot be expressed in E.164."""


def normalize_e164(raw: str, default_country_code: str = "34") -> str:
    """Best-effort E.164 for numbers coming from CRM free-text fields."""
    value = _SEPARATORS_RE.sub("", (raw or "").strip())
    if not value:
        raise InvalidPhoneNumber("phone number is empty")

    if value.startswith("00"):
        value = "+" + value[2:]
    elif not value.startswith("+"):
        # A leading 0 is a national trunk prefix in most of the EU.
        value = f"+{default_country_code}{value.lstrip('0')}"

    if not E164_RE.match(value):
        raise InvalidPhoneNumber(f"cannot normalize {raw!r} to E.164 (got {value!r})")
    return value


def _require_e164(label: str, value: str) -> str:
    if not E164_RE.match(value or ""):
        raise InvalidPhoneNumber(f"{label} must already be E.164, got {value!r}")
    return value


def build_outbound_twiml(
    *,
    to: str,
    caller_id: str,
    recording_callback_url: str,
    whisper_url: str,
    timeout: int = 30,
) -> str:
    """Dial `to` from `caller_id`, recording both legs on separate channels."""
    _require_e164("to", to)
    _require_e164("caller_id", caller_id)

    response = VoiceResponse()
    dial = Dial(
        caller_id=caller_id,
        record="record-from-answer-dual",
        recording_status_callback=recording_callback_url,
        recording_status_callback_event="completed",
        # Keeps the SDR hearing ringback while the disclosure plays.
        answer_on_bridge=True,
        timeout=timeout,
    )
    dial.number(to, url=whisper_url)
    response.append(dial)
    return str(response)


def build_whisper_twiml(*, announcement: str, language: str = "es-ES") -> str:
    """Disclosure played to the called party before the legs are bridged.

    Twilio forbids `<Dial>` inside a `<Number url>` document.
    """
    response = VoiceResponse()
    response.say(announcement, language=language)
    return str(response)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_telephony_twiml.py -v`
Expected: PASS (18 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/config.py .env.example \
        backend/app/services/telephony/__init__.py \
        backend/app/services/telephony/twiml.py \
        backend/tests/test_telephony_twiml.py
git commit -m "feat(calling): TwiML builder for dual-channel outbound calls"
```

---

### Task 2: Schema and caller-ID verification service

**Files:**
- Create: `backend/migrations/024_outbound_calling.sql`
- Create: `backend/app/services/telephony/twilio_client.py`
- Create: `backend/app/services/telephony/caller_id.py`
- Create: `backend/tests/test_telephony_caller_id.py`

**Interfaces:**
- Consumes: `normalize_e164`, `InvalidPhoneNumber` from `app.services.telephony.twiml`; `settings` from `app.config`
- Produces:
  - `twilio_rest() -> twilio.rest.Client` and `TelephonyNotConfigured(RuntimeError)` in `twilio_client.py`
  - `start_caller_id_verification(supabase, user_id, raw_number, label) -> dict` returning `{"phoneNumber", "verificationCode", "status"}`
  - `mark_caller_id_verified(supabase, phone_number) -> bool`
  - `mark_caller_id_failed(supabase, phone_number) -> bool`
  - `list_caller_ids(supabase, user_id) -> list[dict]`
  - `resolve_caller_id(supabase, user_id, requested: str | None) -> str` (raises `CallerIdNotVerified`)
  - `CallerIdNotVerified(PermissionError)`

- [ ] **Step 1: Write the migration**

Create `backend/migrations/024_outbound_calling.sql`:

```sql
-- 024_outbound_calling.sql
--
-- Outbound calling through Twilio with the SDR's own number as caller ID.
--
--   user_caller_ids  — one row per (user, phone number) verified with Twilio's
--                      OutgoingCallerIds resource. Twilio enforces ownership;
--                      this table is how the voice webhook decides whether a
--                      client is allowed to present a given number.
--   outbound_calls   — created by the voice webhook keyed on the parent (client)
--                      leg CallSid, which is the same CallSid the recording
--                      callback reports. Carries the CRM association from dial
--                      time through to the recording arriving minutes later.
--
-- memos.source gains 'vocify_call' so calls placed by Vocify are
-- distinguishable from recordings fetched out of HubSpot ('hubspot_call').

BEGIN;

CREATE TABLE IF NOT EXISTS user_caller_ids (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  phone_number TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'verified', 'failed')),
  label TEXT,
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  twilio_validation_sid TEXT,
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, phone_number)
);

CREATE INDEX IF NOT EXISTS idx_user_caller_ids_user
  ON user_caller_ids (user_id, status);

-- The voice webhook looks numbers up by number alone (it only knows the
-- Twilio identity + requested caller ID), so this lookup must be indexed.
CREATE INDEX IF NOT EXISTS idx_user_caller_ids_number
  ON user_caller_ids (phone_number);

CREATE TABLE IF NOT EXISTS outbound_calls (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  twilio_call_sid TEXT NOT NULL UNIQUE,
  from_number TEXT NOT NULL,
  to_number TEXT NOT NULL,
  hubspot_hub_id TEXT,
  hubspot_contact_id TEXT,
  hubspot_deal_id TEXT,
  hubspot_engagement_id TEXT,
  recording_sid TEXT,
  recording_path TEXT,
  recording_duration INTEGER,
  memo_id UUID REFERENCES memos(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'dialing'
    CHECK (status IN ('dialing', 'recorded', 'logged', 'failed')),
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outbound_calls_user
  ON outbound_calls (user_id, created_at DESC);

ALTER TABLE user_caller_ids ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbound_calls ENABLE ROW LEVEL SECURITY;

ALTER TABLE memos DROP CONSTRAINT IF EXISTS memos_source_check;
ALTER TABLE memos ADD CONSTRAINT memos_source_check
  CHECK (source IN (
    'web', 'voice_memo', 'whatsapp', 'unipile', 'hubspot_call', 'vocify_call'
  ));

-- Private bucket: call audio is personal data under RGPD and must not be
-- reachable by URL alone. HubSpot playback uses short-lived signed URLs.
INSERT INTO storage.buckets (id, name, public)
VALUES ('call-recordings', 'call-recordings', FALSE)
ON CONFLICT (id) DO NOTHING;

COMMIT;
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_telephony_caller_id.py`:

```python
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.telephony.caller_id import (
    CallerIdNotVerified,
    resolve_caller_id,
    start_caller_id_verification,
)


class FakeQuery:
    """Minimal supabase-py table() chain returning a canned payload."""

    def __init__(self, rows):
        self.rows = rows
        self.inserted = None
        self.updated = None

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def insert(self, row):
        self.inserted = row
        return self

    def upsert(self, row, **_k):
        self.inserted = row
        return self

    def update(self, row):
        self.updated = row
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


def fake_supabase(rows):
    query = FakeQuery(rows)
    client = MagicMock()
    client.table.return_value = query
    return client, query


class TestResolveCallerId:
    def test_returns_requested_number_when_verified_for_that_user(self):
        supabase, _ = fake_supabase(
            [{"phone_number": "+34910000000", "status": "verified"}]
        )
        assert (
            resolve_caller_id(supabase, "user-1", "+34910000000") == "+34910000000"
        )

    def test_rejects_number_that_is_not_verified(self):
        supabase, _ = fake_supabase([])
        with pytest.raises(CallerIdNotVerified):
            resolve_caller_id(supabase, "user-1", "+34910000000")

    def test_rejects_number_still_pending(self):
        supabase, _ = fake_supabase(
            [{"phone_number": "+34910000000", "status": "pending"}]
        )
        with pytest.raises(CallerIdNotVerified):
            resolve_caller_id(supabase, "user-1", "+34910000000")

    def test_falls_back_to_default_when_no_number_requested(self):
        supabase, _ = fake_supabase(
            [{"phone_number": "+34910000001", "status": "verified"}]
        )
        assert resolve_caller_id(supabase, "user-1", None) == "+34910000001"

    def test_raises_when_user_has_no_verified_number_at_all(self):
        supabase, _ = fake_supabase([])
        with pytest.raises(CallerIdNotVerified):
            resolve_caller_id(supabase, "user-1", None)


class TestStartCallerIdVerification:
    @patch("app.services.telephony.caller_id.twilio_rest")
    def test_normalizes_number_and_returns_twilio_code(self, rest):
        rest.return_value.validation_requests.create.return_value = SimpleNamespace(
            validation_code="482913", friendly_name="Oficina"
        )
        supabase, query = fake_supabase([{"id": "row-1"}])

        result = start_caller_id_verification(
            supabase, "user-1", "600 111 222", label="Oficina"
        )

        assert result["phoneNumber"] == "+34600111222"
        assert result["verificationCode"] == "482913"
        assert result["status"] == "pending"
        assert query.inserted["phone_number"] == "+34600111222"
        assert query.inserted["status"] == "pending"

    @patch("app.services.telephony.caller_id.twilio_rest")
    def test_passes_status_callback_to_twilio(self, rest):
        rest.return_value.validation_requests.create.return_value = SimpleNamespace(
            validation_code="111111", friendly_name=None
        )
        supabase, _ = fake_supabase([{"id": "row-1"}])

        start_caller_id_verification(supabase, "user-1", "+34600111222", label=None)

        kwargs = rest.return_value.validation_requests.create.call_args.kwargs
        assert "webhooks/twilio/caller-id-status" in kwargs["status_callback"]
        assert kwargs["phone_number"] == "+34600111222"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_telephony_caller_id.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.telephony.caller_id'`

- [ ] **Step 4: Write the implementation**

Create `backend/app/services/telephony/twilio_client.py`:

```python
"""Twilio REST client factory.

Kept in its own module so tests can patch a single seam and so the rest of the
telephony package never reads credentials directly.
"""

from __future__ import annotations

from functools import lru_cache

from twilio.rest import Client as TwilioRestClient

from app.config import settings


class TelephonyNotConfigured(RuntimeError):
    """Twilio credentials are absent; calling features are unavailable."""


def telephony_configured() -> bool:
    return bool(
        settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.TWILIO_API_KEY_SID
        and settings.TWILIO_API_KEY_SECRET
        and settings.TWILIO_TWIML_APP_SID
    )


@lru_cache(maxsize=1)
def _client(account_sid: str, auth_token: str) -> TwilioRestClient:
    return TwilioRestClient(account_sid, auth_token)


def twilio_rest() -> TwilioRestClient:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise TelephonyNotConfigured("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN unset")
    return _client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
```

Create `backend/app/services/telephony/caller_id.py`:

```python
"""Verified caller IDs: the SDR's own number, presented on outbound calls.

Twilio's Transit Caller ID was sunset on 2026-06-22, so a Verified Caller ID
(or a Twilio-owned number) is the only supported way to present a number.
Twilio performs the ownership proof; `user_caller_ids` records the outcome so
the voice webhook can authorize a caller ID without a round trip.

The verification call/SMS is placed by Twilio and is English-only, so the UI
must surface `verificationCode` to the user.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import Client

from app.config import settings
from app.services.telephony.twilio_client import twilio_rest
from app.services.telephony.twiml import normalize_e164

logger = logging.getLogger(__name__)


class CallerIdNotVerified(PermissionError):
    """The requested caller ID is not a verified number for this user."""


def _status_callback_url() -> str:
    base = (settings.BACKEND_PUBLIC_URL or "").rstrip("/")
    return f"{base}/webhooks/twilio/caller-id-status"


def start_caller_id_verification(
    supabase: Client,
    user_id: str,
    raw_number: str,
    label: Optional[str],
) -> dict[str, Any]:
    """Ask Twilio to verify a number and return the code the user must enter."""
    phone_number = normalize_e164(
        raw_number, default_country_code=settings.CALLING_DEFAULT_COUNTRY_CODE
    )

    validation = twilio_rest().validation_requests.create(
        phone_number=phone_number,
        friendly_name=(label or f"Vocify {phone_number}")[:64],
        status_callback=_status_callback_url(),
    )

    supabase.table("user_caller_ids").upsert(
        {
            "user_id": user_id,
            "phone_number": phone_number,
            "status": "pending",
            "label": label,
            "verified_at": None,
        },
        on_conflict="user_id,phone_number",
    ).execute()

    return {
        "phoneNumber": phone_number,
        "verificationCode": validation.validation_code,
        "status": "pending",
    }


def _set_status(supabase: Client, phone_number: str, status: str) -> bool:
    update: dict[str, Any] = {"status": status}
    if status == "verified":
        update["verified_at"] = datetime.now(timezone.utc).isoformat()
    res = (
        supabase.table("user_caller_ids")
        .update(update)
        .eq("phone_number", phone_number)
        .execute()
    )
    return bool(res.data)


def mark_caller_id_verified(supabase: Client, phone_number: str) -> bool:
    return _set_status(supabase, phone_number, "verified")


def mark_caller_id_failed(supabase: Client, phone_number: str) -> bool:
    return _set_status(supabase, phone_number, "failed")


def list_caller_ids(supabase: Client, user_id: str) -> list[dict[str, Any]]:
    res = (
        supabase.table("user_caller_ids")
        .select("phone_number,status,label,is_default,verified_at")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    return [
        {
            "phoneNumber": row.get("phone_number"),
            "status": row.get("status"),
            "label": row.get("label"),
            "isDefault": bool(row.get("is_default")),
            "verifiedAt": row.get("verified_at"),
        }
        for row in (res.data or [])
    ]


def resolve_caller_id(
    supabase: Client,
    user_id: str,
    requested: Optional[str],
) -> str:
    """Authorize a caller ID for this user, or raise.

    The browser client sends a preference; this is the only place that decides.
    A client must never be able to present a number it does not own.
    """
    query = (
        supabase.table("user_caller_ids")
        .select("phone_number,status")
        .eq("user_id", user_id)
        .eq("status", "verified")
    )
    if requested:
        query = query.eq("phone_number", requested)
    else:
        query = query.order("is_default", desc=True)

    rows = (query.limit(1).execute().data) or []
    verified = [r for r in rows if (r.get("status") == "verified")]
    if not verified:
        raise CallerIdNotVerified(
            f"no verified caller ID for user {user_id} (requested={requested!r})"
        )
    return str(verified[0]["phone_number"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_telephony_caller_id.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Apply the migration**

Run the SQL in `backend/migrations/024_outbound_calling.sql` against the dev Supabase project (SQL editor or `supabase db execute`). Verify:

```sql
select phone_number from user_caller_ids limit 1;
select twilio_call_sid from outbound_calls limit 1;
select id, public from storage.buckets where id = 'call-recordings';
```

Expected: both selects succeed (zero rows), and the bucket row shows `public = false`.

- [ ] **Step 7: Commit**

```bash
git add backend/migrations/024_outbound_calling.sql \
        backend/app/services/telephony/twilio_client.py \
        backend/app/services/telephony/caller_id.py \
        backend/tests/test_telephony_caller_id.py
git commit -m "feat(calling): verified caller ID store and Twilio verification"
```

---

### Task 3: Access token and calling API

**Files:**
- Create: `backend/app/api/calls.py`
- Modify: `backend/app/api/router.py`
- Create: `backend/tests/test_telephony_token.py`

**Interfaces:**
- Consumes: `get_supabase`, `get_user_id` from `app.deps`; `start_caller_id_verification`, `list_caller_ids` from `app.services.telephony.caller_id`; `telephony_configured` from `app.services.telephony.twilio_client`
- Produces:
  - `mint_voice_access_token(user_id: str, ttl: int = 3600) -> str` in `app/api/calls.py`
  - `GET /api/v1/calls/config` → `{"enabled": bool, "callerIds": [...]}`
  - `POST /api/v1/calls/token` → `{"token": str, "identity": str, "expiresIn": int}`
  - `POST /api/v1/calls/caller-ids` body `{"phoneNumber": str, "label": str | None}` → verification payload
  - `GET /api/v1/calls/caller-ids` → `{"callerIds": [...]}`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_telephony_token.py`:

```python
from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException

from app.api.calls import mint_voice_access_token


class TestMintVoiceAccessToken:
    def _settings(self, settings):
        settings.TWILIO_ACCOUNT_SID = "AC" + "0" * 32
        settings.TWILIO_AUTH_TOKEN = "auth-token"
        settings.TWILIO_API_KEY_SID = "SK" + "0" * 32
        settings.TWILIO_API_KEY_SECRET = "api-secret"
        settings.TWILIO_TWIML_APP_SID = "AP" + "0" * 32

    def test_identity_is_the_vocify_user_id(self):
        with patch("app.api.calls.settings") as settings:
            self._settings(settings)
            token = mint_voice_access_token("11111111-2222-3333-4444-555555555555")

        claims = jwt.decode(token, options={"verify_signature": False})
        assert claims["grants"]["identity"] == "11111111-2222-3333-4444-555555555555"

    def test_grant_points_at_the_twiml_app(self):
        with patch("app.api.calls.settings") as settings:
            self._settings(settings)
            token = mint_voice_access_token("user-1")

        claims = jwt.decode(token, options={"verify_signature": False})
        voice = claims["grants"]["voice"]
        assert voice["outgoing"]["application_sid"] == "AP" + "0" * 32

    def test_incoming_calls_are_not_granted(self):
        # Outbound only: callbacks ring the SDR's real phone, not the browser.
        with patch("app.api.calls.settings") as settings:
            self._settings(settings)
            token = mint_voice_access_token("user-1")

        claims = jwt.decode(token, options={"verify_signature": False})
        assert "incoming" not in claims["grants"]["voice"]

    def test_raises_503_when_twilio_is_not_configured(self):
        with patch("app.api.calls.settings") as settings:
            settings.TWILIO_ACCOUNT_SID = None
            settings.TWILIO_API_KEY_SID = None
            settings.TWILIO_API_KEY_SECRET = None
            settings.TWILIO_TWIML_APP_SID = None
            with pytest.raises(HTTPException) as exc:
                mint_voice_access_token("user-1")

        assert exc.value.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_telephony_token.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api.calls'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/api/calls.py`:

```python
"""Authenticated calling endpoints for the Chrome extension.

The browser never holds Twilio credentials. It asks for a short-lived
AccessToken whose identity is the Vocify user id; the voice webhook later
trusts that identity (Twilio signs it) to resolve the caller ID.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from supabase import Client
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant

from app.config import settings
from app.deps import get_supabase, get_user_id
from app.services.telephony.caller_id import (
    list_caller_ids,
    start_caller_id_verification,
)
from app.services.telephony.twilio_client import telephony_configured
from app.services.telephony.twiml import InvalidPhoneNumber

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calls", tags=["calls"])

TOKEN_TTL_SECONDS = 3600


class CallerIdRequest(BaseModel):
    phoneNumber: str = Field(min_length=6, max_length=32)
    label: Optional[str] = Field(default=None, max_length=64)


def mint_voice_access_token(user_id: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    """Twilio AccessToken with a VoiceGrant scoped to our TwiML App."""
    if not (
        settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_API_KEY_SID
        and settings.TWILIO_API_KEY_SECRET
        and settings.TWILIO_TWIML_APP_SID
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Calling is not configured on this environment",
        )

    token = AccessToken(
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_API_KEY_SID,
        settings.TWILIO_API_KEY_SECRET,
        identity=str(user_id),
        ttl=ttl,
    )
    # incoming_allow stays False: inbound callbacks go to the SDR's own phone.
    token.add_grant(
        VoiceGrant(outgoing_application_sid=settings.TWILIO_TWIML_APP_SID)
    )
    return token.to_jwt()


@router.get("/config")
async def get_calling_config(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Whether calling is available here, plus this user's caller IDs."""
    if not telephony_configured():
        return {"enabled": False, "callerIds": []}
    return {"enabled": True, "callerIds": list_caller_ids(supabase, user_id)}


@router.post("/token")
async def create_voice_token(user_id: str = Depends(get_user_id)):
    return {
        "token": mint_voice_access_token(user_id),
        "identity": str(user_id),
        "expiresIn": TOKEN_TTL_SECONDS,
    }


@router.get("/caller-ids")
async def get_caller_ids(
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    return {"callerIds": list_caller_ids(supabase, user_id)}


@router.post("/caller-ids")
async def create_caller_id(
    body: CallerIdRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
):
    """Start Twilio verification. Twilio calls the number in English, so the
    caller must be shown `verificationCode` to type on the keypad."""
    if not telephony_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Calling is not configured on this environment",
        )
    try:
        return start_caller_id_verification(
            supabase, user_id, body.phoneNumber, body.label
        )
    except InvalidPhoneNumber as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
```

In `backend/app/api/router.py`, add the import alongside the existing router imports and register it after `crm`:

```python
from app.api import calls  # noqa: E402
...
api_router.include_router(calls.router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_telephony_token.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Verify the app still boots and routes are mounted**

Run:

```bash
cd backend && python -c "
from app.main import app
print(sorted(r.path for r in app.routes if '/calls' in getattr(r, 'path', '')))
"
```

Expected: the four `/api/v1/calls/...` paths are listed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/calls.py backend/app/api/router.py \
        backend/tests/test_telephony_token.py
git commit -m "feat(calling): voice access token and caller ID endpoints"
```

---

### Task 4: Twilio webhooks — voice, whisper, caller-ID status

**Files:**
- Create: `backend/app/services/telephony/webhook_signature.py`
- Modify: `backend/app/api/webhooks.py`
- Create: `backend/tests/test_telephony_webhook.py`

**Interfaces:**
- Consumes: `build_outbound_twiml`, `build_whisper_twiml`, `normalize_e164`, `DEFAULT_RECORDING_ANNOUNCEMENT_ES`, `InvalidPhoneNumber` from `app.services.telephony.twiml`; `resolve_caller_id`, `CallerIdNotVerified`, `mark_caller_id_verified`, `mark_caller_id_failed` from `app.services.telephony.caller_id`
- Produces:
  - `verify_twilio_signature(url: str, params: dict[str, str], signature: str, auth_token: str) -> bool`
  - `identity_from_client_from(from_value: str) -> str | None`
  - `POST /webhooks/twilio/voice` → TwiML XML
  - `POST /webhooks/twilio/whisper` → TwiML XML
  - `POST /webhooks/twilio/caller-id-status` → `204`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_telephony_webhook.py`:

```python
from twilio.request_validator import RequestValidator

from app.services.telephony.webhook_signature import (
    identity_from_client_from,
    verify_twilio_signature,
)

AUTH_TOKEN = "test-auth-token"
URL = "https://api.getvocify.com/webhooks/twilio/voice"


class TestVerifyTwilioSignature:
    def test_accepts_a_signature_twilio_would_produce(self):
        params = {"To": "+34600111222", "From": "client:user-1"}
        signature = RequestValidator(AUTH_TOKEN).compute_signature(URL, params)
        assert verify_twilio_signature(URL, params, signature, AUTH_TOKEN) is True

    def test_rejects_a_tampered_body(self):
        params = {"To": "+34600111222", "From": "client:user-1"}
        signature = RequestValidator(AUTH_TOKEN).compute_signature(URL, params)
        tampered = {"To": "+34600999999", "From": "client:user-1"}
        assert verify_twilio_signature(URL, tampered, signature, AUTH_TOKEN) is False

    def test_rejects_a_signature_from_a_different_url(self):
        params = {"To": "+34600111222"}
        signature = RequestValidator(AUTH_TOKEN).compute_signature(
            "https://evil.example/webhooks/twilio/voice", params
        )
        assert verify_twilio_signature(URL, params, signature, AUTH_TOKEN) is False

    def test_rejects_empty_signature(self):
        assert verify_twilio_signature(URL, {}, "", AUTH_TOKEN) is False


class TestIdentityFromClientFrom:
    def test_extracts_identity_from_client_prefix(self):
        assert identity_from_client_from("client:abc-123") == "abc-123"

    def test_returns_none_for_a_pstn_from(self):
        assert identity_from_client_from("+34600111222") is None

    def test_returns_none_for_empty(self):
        assert identity_from_client_from("") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_telephony_webhook.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.telephony.webhook_signature'`

- [ ] **Step 3: Write the signature helper**

Create `backend/app/services/telephony/webhook_signature.py`:

```python
"""Twilio webhook authentication.

Twilio signs the exact URL it requested plus the sorted POST params. Behind a
proxy the request URL seen by FastAPI can differ from the public one, so the
caller must rebuild the URL from BACKEND_PUBLIC_URL rather than trusting
`request.url`.
"""

from __future__ import annotations

import logging
from typing import Optional

from twilio.request_validator import RequestValidator

logger = logging.getLogger(__name__)

CLIENT_PREFIX = "client:"


def verify_twilio_signature(
    url: str,
    params: dict[str, str],
    signature: str,
    auth_token: str,
) -> bool:
    if not signature or not auth_token:
        return False
    try:
        return bool(RequestValidator(auth_token).validate(url, params, signature))
    except Exception as e:  # malformed signature header
        logger.warning("Twilio signature validation error: %s", e)
        return False


def identity_from_client_from(from_value: str) -> Optional[str]:
    """`From=client:<identity>` on calls originated by a Voice SDK client."""
    value = (from_value or "").strip()
    if not value.startswith(CLIENT_PREFIX):
        return None
    identity = value[len(CLIENT_PREFIX):].strip()
    return identity or None
```

- [ ] **Step 4: Add the webhook routes**

In `backend/app/api/webhooks.py`, change the FastAPI responses import to add `Response`:

```python
from fastapi.responses import PlainTextResponse, JSONResponse, Response
```

Then add these imports with the other service imports:

```python
from twilio.twiml.voice_response import VoiceResponse

from app.services.telephony.caller_id import (
    CallerIdNotVerified,
    mark_caller_id_failed,
    mark_caller_id_verified,
    resolve_caller_id,
)
from app.services.telephony.twiml import (
    DEFAULT_RECORDING_ANNOUNCEMENT_ES,
    InvalidPhoneNumber,
    build_outbound_twiml,
    build_whisper_twiml,
    normalize_e164,
)
from app.services.telephony.webhook_signature import (
    identity_from_client_from,
    verify_twilio_signature,
)
```

Append these routes to the same file:

```python
def _twilio_public_url(request: Request) -> str:
    """The URL Twilio signed, rebuilt from config (proxies rewrite the host)."""
    base = (settings.BACKEND_PUBLIC_URL or "").rstrip("/")
    return f"{base}{request.url.path}"


async def _twilio_form(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: str(v) for k, v in form.items()}


def _twilio_authentic(request: Request, params: dict[str, str]) -> bool:
    import os

    skip = os.environ.get("TWILIO_SKIP_SIG_CHECK", "").lower() in ("1", "true", "yes")
    if skip:
        logger.warning("Twilio webhook signature check skipped (dev only)")
        return True
    return verify_twilio_signature(
        _twilio_public_url(request),
        params,
        request.headers.get("X-Twilio-Signature", ""),
        settings.TWILIO_AUTH_TOKEN or "",
    )


def _twiml(xml: str) -> Response:
    return Response(content=xml, media_type="application/xml")


def _reject_twiml(message: str) -> Response:
    response = VoiceResponse()
    response.say(message, language=settings.TWILIO_ANNOUNCEMENT_LANGUAGE)
    response.hangup()
    return _twiml(str(response))


@router.post("/twilio/voice")
async def twilio_voice(request: Request):
    """TwiML App Voice URL. Authorizes the caller ID and dials the prospect.

    `CallerId` arrives from the browser as a *preference*; the authoritative
    check is against `user_caller_ids` for the signed Twilio identity.
    """
    supabase = get_supabase()
    params = await _twilio_form(request)
    if not _twilio_authentic(request, params):
        return PlainTextResponse("Forbidden", status_code=403)

    user_id = identity_from_client_from(params.get("From", ""))
    if not user_id:
        return _reject_twiml("Llamada no autorizada.")

    try:
        to_number = normalize_e164(
            params.get("To", ""),
            default_country_code=settings.CALLING_DEFAULT_COUNTRY_CODE,
        )
        caller_id = resolve_caller_id(supabase, user_id, params.get("CallerId") or None)
    except (InvalidPhoneNumber, CallerIdNotVerified) as e:
        logger.warning("Twilio voice webhook rejected: %s", e)
        return _reject_twiml("Numero no valido o identificador no verificado.")

    call_sid = params.get("CallSid", "")
    base = (settings.BACKEND_PUBLIC_URL or "").rstrip("/")

    # Persisted now because the recording callback arrives minutes later with
    # nothing but this same parent-leg CallSid to correlate on.
    try:
        supabase.table("outbound_calls").insert(
            {
                "user_id": user_id,
                "twilio_call_sid": call_sid,
                "from_number": caller_id,
                "to_number": to_number,
                "hubspot_hub_id": params.get("HubId") or None,
                "hubspot_contact_id": params.get("ContactId") or None,
                "hubspot_deal_id": params.get("DealId") or None,
                "status": "dialing",
            }
        ).execute()
    except Exception as e:
        if "duplicate key" not in str(e).lower() and "23505" not in str(e):
            raise

    return _twiml(
        build_outbound_twiml(
            to=to_number,
            caller_id=caller_id,
            recording_callback_url=f"{base}/webhooks/twilio/recording",
            whisper_url=f"{base}/webhooks/twilio/whisper",
        )
    )


@router.post("/twilio/whisper")
async def twilio_whisper(request: Request):
    """Recording disclosure, played to the prospect only (AEPD 1/2023)."""
    params = await _twilio_form(request)
    if not _twilio_authentic(request, params):
        return PlainTextResponse("Forbidden", status_code=403)
    return _twiml(
        build_whisper_twiml(
            announcement=(
                settings.TWILIO_RECORDING_ANNOUNCEMENT
                or DEFAULT_RECORDING_ANNOUNCEMENT_ES
            ),
            language=settings.TWILIO_ANNOUNCEMENT_LANGUAGE,
        )
    )


@router.post("/twilio/caller-id-status")
async def twilio_caller_id_status(request: Request):
    """Outcome of a caller ID verification call."""
    supabase = get_supabase()
    params = await _twilio_form(request)
    if not _twilio_authentic(request, params):
        return PlainTextResponse("Forbidden", status_code=403)

    phone_number = (params.get("To") or params.get("PhoneNumber") or "").strip()
    verified = (params.get("VerificationStatus") or "").lower() == "success"
    if phone_number:
        if verified:
            mark_caller_id_verified(supabase, phone_number)
        else:
            mark_caller_id_failed(supabase, phone_number)
    return Response(status_code=204)
```

`logger`, `settings`, `Request`, `PlainTextResponse`, `asyncio` and `get_supabase` are already imported in this file. `os` is not imported at module level — this file imports it inside each handler that needs it, so add `import os` inside `_twilio_authentic`. Do not add `Depends`: no handler in `webhooks.py` uses it.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_telephony_webhook.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Smoke-test the voice webhook end to end locally**

With the backend running and `TWILIO_SKIP_SIG_CHECK=1`, and one row in `user_caller_ids` with `status='verified'`:

```bash
curl -s -X POST http://localhost:8888/webhooks/twilio/voice \
  -d 'From=client:<REAL_USER_UUID>' \
  -d 'To=600111222' \
  -d 'CallerId=<VERIFIED_NUMBER_E164>' \
  -d 'CallSid=CA00000000000000000000000000000001'
```

Expected: XML containing `record="record-from-answer-dual"`, `callerId="<VERIFIED_NUMBER_E164>"`, and a `<Number url=".../whisper">+34600111222</Number>`. Then re-run with an unverified `CallerId` and expect the reject TwiML with `<Hangup/>`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/telephony/webhook_signature.py \
        backend/app/api/webhooks.py \
        backend/tests/test_telephony_webhook.py
git commit -m "feat(calling): Twilio voice, whisper and caller-id-status webhooks"
```

---

### Task 5: Recording ingest — store, transcribe, extract

**Files:**
- Modify: `backend/app/services/storage.py`
- Modify: `backend/app/services/pipeline_meta.py`
- Create: `backend/app/services/telephony/call_processor.py`
- Modify: `backend/app/api/webhooks.py`
- Create: `backend/tests/test_telephony_call_processor.py`

**Interfaces:**
- Consumes: `transcribe_bytes` from `app.services.stt_batch`; `sanitize_user_transcript` from `app.services.transcript_sanitize`; `start_extraction_from_transcript` from `app.api.memos`; `pipeline_run`, `persist_pipeline_meta` from `app.services.pipeline_meta`
- Produces:
  - `StorageService.upload_call_recording(audio_bytes, user_id, call_sid) -> str` (returns the storage **path**, not a URL)
  - `StorageService.signed_call_recording_url(path, expires_in) -> str`
  - `CALL_RECORDINGS_BUCKET = "call-recordings"`
  - `download_twilio_recording(recording_url: str) -> bytes` in `call_processor.py`
  - `initiate_vocify_call_memo(supabase, call_row) -> tuple[str | None, bool]`
  - `process_vocify_call_background(memo_id, user_id, call_sid, audio_bytes, duration, supabase) -> None`
  - `POST /webhooks/twilio/recording` → `204`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_telephony_call_processor.py`:

```python
from unittest.mock import patch

from app.services.pipeline_meta import extraction_source_type
from app.services.storage import CALL_RECORDINGS_BUCKET
from app.services.telephony.call_processor import twilio_wav_url


class TestSourceType:
    def test_vocify_call_is_an_accepted_extraction_source(self):
        assert extraction_source_type("vocify_call") == "vocify_call"

    def test_unknown_source_still_falls_back_to_voice_memo(self):
        assert extraction_source_type("nonsense") == "voice_memo"


class TestBucket:
    def test_recordings_live_in_a_dedicated_private_bucket(self):
        # Never 'voice-memos': that bucket is public.
        assert CALL_RECORDINGS_BUCKET == "call-recordings"


class TestTwilioWavUrl:
    def test_appends_wav_because_hubspot_rejects_mp3(self):
        url = twilio_wav_url(
            "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/RE1"
        )
        assert url.endswith(".wav")

    def test_does_not_double_append(self):
        url = twilio_wav_url(
            "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/RE1.wav"
        )
        assert url.count(".wav") == 1

    def test_strips_query_string_before_appending(self):
        url = twilio_wav_url(
            "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/RE1?x=1"
        )
        assert url.endswith("/RE1.wav")


class TestDownloadUsesBasicAuth:
    @patch("app.services.telephony.call_processor.httpx.AsyncClient")
    @patch("app.services.telephony.call_processor.settings")
    def test_authenticates_with_api_key_credentials(self, settings, client_cls):
        import asyncio

        from app.services.telephony.call_processor import download_twilio_recording

        settings.TWILIO_API_KEY_SID = "SK1"
        settings.TWILIO_API_KEY_SECRET = "secret"

        instance = client_cls.return_value.__aenter__.return_value
        response = instance.get.return_value
        response.content = b"RIFF"
        response.raise_for_status.return_value = None

        asyncio.run(
            download_twilio_recording(
                "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/RE1"
            )
        )

        assert client_cls.call_args.kwargs["auth"] == ("SK1", "secret")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_telephony_call_processor.py -v`
Expected: FAIL — `ImportError: cannot import name 'CALL_RECORDINGS_BUCKET'`

- [ ] **Step 3: Extend storage and the source-type allowlist**

In `backend/app/services/pipeline_meta.py`, change `_EXTRACTION_SOURCE_TYPES`:

```python
_EXTRACTION_SOURCE_TYPES = frozenset(
    {"voice_memo", "meeting_transcript", "hubspot_call", "vocify_call"}
)
```

In `backend/app/services/storage.py`, add the module-level constant next to the existing bucket name and two methods to `StorageService`:

```python
# Private, unlike BUCKET_NAME ('voice-memos'). Call audio is personal data:
# HubSpot playback goes through short-lived signed URLs, never a public URL.
CALL_RECORDINGS_BUCKET = "call-recordings"


    async def upload_call_recording(
        self,
        audio_bytes: bytes,
        user_id: str,
        call_sid: str,
    ) -> str:
        """Store a call recording and return its storage path (not a URL)."""
        path = f"{user_id}/{call_sid}.wav"
        self.supabase.storage.from_(CALL_RECORDINGS_BUCKET).upload(
            path=path,
            file=audio_bytes,
            file_options={"content-type": "audio/wav", "upsert": "true"},
        )
        return path

    def signed_call_recording_url(self, path: str, expires_in: int = 3600) -> str:
        """Time-limited URL. Supabase Storage honours Range and returns 206,
        which HubSpot's player requires for seeking."""
        res = self.supabase.storage.from_(CALL_RECORDINGS_BUCKET).create_signed_url(
            path, expires_in
        )
        # supabase-py has used both spellings across versions.
        url = None
        if isinstance(res, dict):
            url = res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
        if not url:
            raise RuntimeError(f"could not sign recording URL for {path}")
        return str(url)
```

- [ ] **Step 4: Write the call processor**

Create `backend/app/services/telephony/call_processor.py`:

```python
"""Turn a finished Twilio call into a Vocify memo.

Mirrors `app/services/hubspot/call_processor.py` deliberately: same statuses,
same STT entry point, same extraction handoff. The difference is provenance —
here Vocify placed the call and owns the audio, so the recording is persisted
(HubSpot will ask us for it later) instead of being discarded after STT.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

import httpx
from supabase import Client

from app.config import settings
from app.logging_config import DOMAIN_MEMO, log_domain
from app.metrics import record_transcription_duration
from app.services.pipeline_meta import persist_pipeline_meta, pipeline_run
from app.services.stt_batch import transcribe_bytes
from app.services.transcript_sanitize import sanitize_user_transcript

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT = 60.0


def twilio_wav_url(recording_url: str) -> str:
    """Twilio serves WAV when the media extension is explicit.

    HubSpot only transcribes .WAV/.FLAC/.MP4, so MP3 is not an option.
    """
    base = (recording_url or "").split("?", 1)[0].rstrip("/")
    if base.endswith(".wav"):
        return base
    return f"{base}.wav"


async def download_twilio_recording(recording_url: str) -> bytes:
    """Twilio recording media requires HTTP basic auth."""
    auth = (
        settings.TWILIO_API_KEY_SID or "",
        settings.TWILIO_API_KEY_SECRET or "",
    )
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, auth=auth) as client:
        response = await client.get(twilio_wav_url(recording_url))
        response.raise_for_status()
        return response.content


async def initiate_vocify_call_memo(
    supabase: Client,
    call_row: dict[str, Any],
) -> Tuple[Optional[str], bool]:
    """Idempotent memo row for a Vocify-placed call. Returns (memo_id, created)."""
    existing_memo_id = call_row.get("memo_id")
    if existing_memo_id:
        return str(existing_memo_id), False

    row = {
        "user_id": call_row["user_id"],
        "audio_url": "",
        "audio_duration": float(call_row.get("recording_duration") or 0.0),
        "status": "transcribing",
        "source": "vocify_call",
        "hubspot_contact_id": call_row.get("hubspot_contact_id"),
        "hubspot_deal_id": call_row.get("hubspot_deal_id"),
        "processing_started_at": datetime.now(timezone.utc).isoformat(),
    }
    ins = supabase.table("memos").insert(row).execute()
    if not ins.data:
        return None, False

    memo_id = str(ins.data[0]["id"])
    supabase.table("outbound_calls").update(
        {"memo_id": memo_id, "status": "recorded"}
    ).eq("twilio_call_sid", call_row["twilio_call_sid"]).execute()
    return memo_id, True


async def process_vocify_call_background(
    memo_id: str,
    user_id: str,
    call_sid: str,
    audio_bytes: bytes,
    duration: float,
    supabase: Client,
) -> None:
    """Transcribe the stored recording and hand off to CRM extraction."""
    t0 = time.perf_counter()
    stages: list = []
    try:
        with pipeline_run() as stages:
            transcript = await transcribe_bytes(
                audio_bytes,
                content_type="audio/wav",
                user_id=user_id,
                diarization=True,
            )
            memo_row = (
                supabase.table("memos")
                .select("id,user_id,hubspot_contact_id,hubspot_deal_id,matched_deal_id")
                .eq("id", memo_id)
                .limit(1)
                .execute()
            )
            memo_data = (memo_row.data or [None])[0] or {
                "id": memo_id,
                "user_id": user_id,
            }
            cleaned = await sanitize_user_transcript(
                transcript, user_id, supabase, memo_data=memo_data
            )
        record_transcription_duration(time.perf_counter() - t0, "vocify_call")
        persist_pipeline_meta(supabase, memo_id, stages)

        from app.api.memos import start_extraction_from_transcript

        await start_extraction_from_transcript(
            memo_id,
            user_id,
            cleaned,
            supabase,
            source_type="vocify_call",
            extra_update={"audio_duration": duration, "error_message": None},
        )
        logger.info(
            "Vocify call transcribed (extraction started)",
            extra=log_domain(
                DOMAIN_MEMO,
                "vocify_call_transcribed",
                memo_id=memo_id,
                call_sid=call_sid,
                transcript_len=len(cleaned),
            ),
        )
    except Exception as e:
        logger.exception(
            "Vocify call processing failed",
            extra=log_domain(
                DOMAIN_MEMO, "vocify_call_failed", memo_id=memo_id, error=str(e)
            ),
        )
        supabase.table("memos").update(
            {
                "status": "failed",
                "error_message": str(e)[:2000],
                "processing_started_at": None,
            }
        ).eq("id", memo_id).execute()
        supabase.table("outbound_calls").update(
            {"status": "failed", "error_message": str(e)[:2000]}
        ).eq("twilio_call_sid", call_sid).execute()
        persist_pipeline_meta(supabase, memo_id, stages)
```

- [ ] **Step 5: Add the recording webhook**

In `backend/app/api/webhooks.py`, add the imports:

```python
from app.services.storage import StorageService
from app.services.telephony.call_processor import (
    download_twilio_recording,
    initiate_vocify_call_memo,
    process_vocify_call_background,
)
```

Then append the route:

```python
@router.post("/twilio/recording")
async def twilio_recording(request: Request):
    """Recording is ready: persist the WAV, then transcribe and extract.

    `CallSid` here is the parent (browser) leg — the same SID the voice webhook
    stored — so it correlates the audio back to its CRM context.
    """
    supabase = get_supabase()
    params = await _twilio_form(request)
    if not _twilio_authentic(request, params):
        return PlainTextResponse("Forbidden", status_code=403)

    call_sid = (params.get("CallSid") or "").strip()
    recording_url = (params.get("RecordingUrl") or "").strip()
    if not call_sid or not recording_url:
        return Response(status_code=204)

    found = (
        supabase.table("outbound_calls")
        .select("*")
        .eq("twilio_call_sid", call_sid)
        .limit(1)
        .execute()
    )
    call_row = (found.data or [None])[0]
    if not call_row:
        logger.warning("Twilio recording for unknown call_sid=%s", call_sid)
        return Response(status_code=204)
    if call_row.get("memo_id"):
        return Response(status_code=204)  # redelivery

    duration = float(params.get("RecordingDuration") or 0) or 1.0
    audio_bytes = await download_twilio_recording(recording_url)
    path = await StorageService(supabase).upload_call_recording(
        audio_bytes, call_row["user_id"], call_sid
    )

    supabase.table("outbound_calls").update(
        {
            "recording_sid": params.get("RecordingSid"),
            "recording_path": path,
            "recording_duration": int(duration),
            "status": "recorded",
        }
    ).eq("twilio_call_sid", call_sid).execute()
    call_row["recording_duration"] = int(duration)

    memo_id, created = await initiate_vocify_call_memo(supabase, call_row)
    if memo_id and created:
        asyncio.create_task(
            process_vocify_call_background(
                memo_id,
                call_row["user_id"],
                call_sid,
                audio_bytes,
                duration,
                supabase,
            )
        )
    return Response(status_code=204)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_telephony_call_processor.py -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Run the full backend suite for regressions**

Run: `cd backend && python -m pytest`
Expected: no new failures versus `main`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/storage.py backend/app/services/pipeline_meta.py \
        backend/app/services/telephony/call_processor.py \
        backend/app/api/webhooks.py \
        backend/tests/test_telephony_call_processor.py
git commit -m "feat(calling): ingest Twilio recordings into the memo pipeline"
```

---

### Task 6: HubSpot call logging and recording provider

**Files:**
- Create: `backend/app/services/hubspot/call_log.py`
- Create: `backend/app/services/hubspot/calling_settings.py`
- Create: `backend/app/api/hubspot_recordings.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/services/telephony/call_processor.py`
- Create: `backend/tests/test_hubspot_call_log.py`

**Interfaces:**
- Consumes: `HubSpotClient` from `app.services.hubspot.client`; `StorageService.signed_call_recording_url`
- Produces:
  - `build_call_properties(*, occurred_at, to_number, from_number, duration_ms, external_id, external_account_id, app_id, owner_id, title, body) -> dict`
  - `log_call_to_hubspot(client, *, properties, contact_id, deal_id) -> str` (returns engagement id)
  - `mark_recording_ready(client, engagement_id) -> None`
  - `register_recording_endpoint(client, app_id, endpoint_url) -> dict` in `calling_settings.py`
  - `GET /public/hubspot/recordings/{external_id}` → `{"authenticatedUrl": str}`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_hubspot_call_log.py`:

```python
import pytest

from app.services.hubspot.call_log import build_call_properties
from app.services.hubspot.calling_settings import recording_endpoint_url


class TestBuildCallProperties:
    def _props(self, **overrides):
        base = dict(
            occurred_at="2026-08-26T09:15:00Z",
            to_number="+34600111222",
            from_number="+34910000000",
            duration_ms=185000,
            external_id="CA0000000000000000000000000000001",
            external_account_id="hub-123",
            app_id="app-456",
            owner_id="777",
            title="Llamada Vocify",
            body="Resumen pendiente de revision.",
        )
        base.update(overrides)
        return build_call_properties(**base)

    def test_source_must_be_integrations_platform(self):
        # Without this exact value HubSpot never asks us for the recording.
        assert self._props()["hs_call_source"] == "INTEGRATIONS_PLATFORM"

    def test_carries_the_four_properties_hubspot_requires(self):
        props = self._props()
        for key in (
            "hs_call_external_id",
            "hs_call_external_account_id",
            "hs_call_app_id",
            "hs_call_source",
        ):
            assert props[key], f"{key} must be set"

    def test_duration_is_milliseconds_as_a_string(self):
        assert self._props()["hs_call_duration"] == "185000"

    def test_marks_the_call_completed(self):
        assert self._props()["hs_call_status"] == "COMPLETED"

    def test_direction_is_outbound(self):
        assert self._props()["hs_call_direction"] == "OUTBOUND"

    def test_omits_owner_when_unknown(self):
        assert "hubspot_owner_id" not in self._props(owner_id=None)

    def test_rejects_missing_external_id(self):
        with pytest.raises(ValueError):
            self._props(external_id="")


class TestRecordingEndpointUrl:
    def test_contains_the_percent_s_placeholder_hubspot_substitutes(self):
        url = recording_endpoint_url("https://api.getvocify.com")
        assert "%s" in url
        assert url.startswith("https://")

    def test_does_not_double_the_slash(self):
        assert "//public" not in recording_endpoint_url("https://api.getvocify.com/")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_hubspot_call_log.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.hubspot.call_log'`

- [ ] **Step 3: Write the HubSpot call log service**

Create `backend/app/services/hubspot/call_log.py`:

```python
"""Log Vocify-placed calls to HubSpot and hand over the recording.

`hs_call_source = INTEGRATIONS_PLATFORM` plus the three external identifiers
are what switch HubSpot from "store a URL" to "ask the app for an authenticated
URL". That inversion is the point: Vocify holds the audio and HubSpot fetches
it, so no third-party telephony API sits between us and our own recordings.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.hubspot.client import HubSpotClient

logger = logging.getLogger(__name__)

# The calling-extensions recordings pipeline is documented against this version.
CALLS_OBJECT_PATH = "/crm/objects/2026-03/calls"
CALLING_EXTENSIONS_BASE = "/crm/extensions/calling/2026-03"


def build_call_properties(
    *,
    occurred_at: str,
    to_number: str,
    from_number: str,
    duration_ms: int,
    external_id: str,
    external_account_id: str,
    app_id: str,
    owner_id: Optional[str],
    title: str,
    body: str,
) -> dict[str, Any]:
    if not external_id:
        raise ValueError("external_id is required for the recordings pipeline")
    if not external_account_id:
        raise ValueError("external_account_id is required")
    if not app_id:
        raise ValueError("app_id is required")

    props: dict[str, Any] = {
        "hs_timestamp": occurred_at,
        "hs_call_title": title,
        "hs_call_body": body,
        "hs_call_duration": str(int(duration_ms)),
        "hs_call_from_number": from_number,
        "hs_call_to_number": to_number,
        "hs_call_status": "COMPLETED",
        "hs_call_direction": "OUTBOUND",
        "hs_call_source": "INTEGRATIONS_PLATFORM",
        "hs_call_app_id": app_id,
        "hs_call_external_id": external_id,
        "hs_call_external_account_id": external_account_id,
    }
    if owner_id:
        props["hubspot_owner_id"] = str(owner_id)
    return props


async def log_call_to_hubspot(
    client: HubSpotClient,
    *,
    properties: dict[str, Any],
    contact_id: Optional[str],
    deal_id: Optional[str],
) -> str:
    """Create the engagement and associate it, returning the engagement id."""
    created = await client.post(CALLS_OBJECT_PATH, data={"properties": properties})
    engagement_id = str((created or {}).get("id") or "")
    if not engagement_id:
        raise RuntimeError("HubSpot did not return a call engagement id")

    for object_type, object_id in (("contacts", contact_id), ("deals", deal_id)):
        if not object_id:
            continue
        try:
            await client.put(
                f"{CALLS_OBJECT_PATH}/{engagement_id}/associations/"
                f"{object_type}/{object_id}"
            )
        except Exception as e:
            logger.warning(
                "Could not associate call %s with %s %s: %s",
                engagement_id, object_type, object_id, e,
            )
    return engagement_id


async def mark_recording_ready(client: HubSpotClient, engagement_id: str) -> None:
    """Tell HubSpot the audio can be fetched and transcribed."""
    await client.post(
        f"{CALLING_EXTENSIONS_BASE}/recordings/ready",
        data={"engagementId": int(engagement_id)},
    )
```

Create `backend/app/services/hubspot/calling_settings.py`:

```python
"""One-time registration of Vocify as HubSpot's recording provider.

Run once per HubSpot app id, not per customer. HubSpot substitutes `%s` in the
registered URL with the engagement's `hs_call_external_id`.
"""

from __future__ import annotations

from typing import Any

from app.services.hubspot.call_log import CALLING_EXTENSIONS_BASE
from app.services.hubspot.client import HubSpotClient

RECORDING_PATH_TEMPLATE = "/public/hubspot/recordings/%s"


def recording_endpoint_url(public_base_url: str) -> str:
    return f"{(public_base_url or '').rstrip('/')}{RECORDING_PATH_TEMPLATE}"


async def register_recording_endpoint(
    client: HubSpotClient,
    app_id: str,
    endpoint_url: str,
) -> dict[str, Any]:
    if "%s" not in endpoint_url:
        raise ValueError("endpoint_url must contain the %s placeholder")
    return await client.post(
        f"{CALLING_EXTENSIONS_BASE}/{app_id}/settings/recording",
        data={"urlToRetrieveAuthedRecording": endpoint_url},
    ) or {}
```

- [ ] **Step 4: Write the public recording endpoint**

Create `backend/app/api/hubspot_recordings.py`:

```python
"""The endpoint HubSpot calls to obtain a playable recording URL.

Unauthenticated by design — HubSpot calls it server-to-server. Authorization is
the pairing of an unguessable Twilio CallSid with the `externalAccountId` of the
hub that owns the call. The URL returned is a short-lived Supabase signed URL,
which honours `Range` and returns `206` so HubSpot's player can seek.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.config import settings
from app.deps import get_supabase
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/hubspot", tags=["hubspot-recordings"])


@router.get("/recordings/{external_id}")
async def get_authenticated_recording(
    external_id: str,
    externalAccountId: str = Query(default=""),
    appId: str = Query(default=""),
    supabase: Client = Depends(get_supabase),
):
    found = (
        supabase.table("outbound_calls")
        .select("recording_path,hubspot_hub_id")
        .eq("twilio_call_sid", external_id)
        .limit(1)
        .execute()
    )
    row = (found.data or [None])[0]
    if not row or not row.get("recording_path"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found"
        )

    hub_id = (row.get("hubspot_hub_id") or "").strip()
    if hub_id and externalAccountId and hub_id != externalAccountId.strip():
        logger.warning(
            "Recording %s requested by hub %s but belongs to %s",
            external_id, externalAccountId, hub_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Wrong account"
        )

    url = StorageService(supabase).signed_call_recording_url(
        row["recording_path"], settings.CALL_RECORDING_URL_TTL_SECONDS
    )
    return {"authenticatedUrl": url}
```

In `backend/app/api/router.py`, add:

```python
from app.api import hubspot_recordings  # noqa: E402
...
api_router.include_router(hubspot_recordings.router)
```

- [ ] **Step 5: Log the call after extraction starts**

In `backend/app/services/telephony/call_processor.py`, add this function and call it at the end of the success path in `process_vocify_call_background`, immediately after `start_extraction_from_transcript`:

```python
async def log_call_engagement(
    supabase: Client,
    call_sid: str,
    duration: float,
) -> None:
    """Create the HubSpot engagement and tell HubSpot the recording is ready.

    Best-effort: a HubSpot failure must not fail the memo, which is already
    reviewable in Vocify.
    """
    # Import from crm, not memos: memos.py has a same-named function that
    # returns a (client, connection_id) tuple. crm.py returns the client and
    # is synchronous — do not await it.
    from app.api.crm import get_hubspot_client_from_connection
    from app.services.hubspot.call_log import (
        build_call_properties,
        log_call_to_hubspot,
        mark_recording_ready,
    )

    found = (
        supabase.table("outbound_calls")
        .select("*")
        .eq("twilio_call_sid", call_sid)
        .limit(1)
        .execute()
    )
    row = (found.data or [None])[0]
    if not row or not row.get("hubspot_contact_id"):
        return

    try:
        client = get_hubspot_client_from_connection(row["user_id"], supabase)
        properties = build_call_properties(
            occurred_at=datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            to_number=row["to_number"],
            from_number=row["from_number"],
            duration_ms=int(duration * 1000),
            external_id=call_sid,
            external_account_id=str(row.get("hubspot_hub_id") or ""),
            app_id=str(settings.HUBSPOT_APP_ID or ""),
            owner_id=None,
            title="Llamada Vocify",
            body="Transcripcion y extraccion disponibles en Vocify.",
        )
        engagement_id = await log_call_to_hubspot(
            client,
            properties=properties,
            contact_id=row.get("hubspot_contact_id"),
            deal_id=row.get("hubspot_deal_id"),
        )
        await mark_recording_ready(client, engagement_id)
        supabase.table("outbound_calls").update(
            {"hubspot_engagement_id": engagement_id, "status": "logged"}
        ).eq("twilio_call_sid", call_sid).execute()
    except Exception as e:
        logger.warning("HubSpot call logging failed for %s: %s", call_sid, e)
```

Add the call site inside the `try` block of `process_vocify_call_background`, after the `start_extraction_from_transcript` await:

```python
        await log_call_engagement(supabase, call_sid, duration)
```

Add `HUBSPOT_APP_ID: Optional[str] = None` to `Settings` in `backend/app/config.py` next to the other `HUBSPOT_*` fields, and `HUBSPOT_APP_ID=` to `.env.example`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_hubspot_call_log.py -v`
Expected: PASS (9 tests)

- [ ] **Step 7: Register the endpoint against the real HubSpot app once**

With `HUBSPOT_APP_ID` set and a developer-scoped token available:

```bash
cd backend && python -c "
import asyncio, os
from app.services.hubspot.client import HubSpotClient
from app.services.hubspot.calling_settings import (
    recording_endpoint_url, register_recording_endpoint,
)
from app.config import settings

async def main():
    client = HubSpotClient(os.environ['HUBSPOT_DEV_TOKEN'])
    url = recording_endpoint_url(settings.BACKEND_PUBLIC_URL)
    print(url)
    print(await register_recording_endpoint(client, settings.HUBSPOT_APP_ID, url))

asyncio.run(main())
"
```

Expected: prints a URL ending in `/public/hubspot/recordings/%s` and a success payload. Record the result in `docs/runbooks/twilio-setup.md` in Task 10.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/hubspot/call_log.py \
        backend/app/services/hubspot/calling_settings.py \
        backend/app/api/hubspot_recordings.py backend/app/api/router.py \
        backend/app/services/telephony/call_processor.py \
        backend/app/config.py .env.example \
        backend/tests/test_hubspot_call_log.py
git commit -m "feat(calling): log calls to HubSpot and serve authed recordings"
```

---

### Task 7: Extension — vendor the SDK and dialer logic

**Files:**
- Create: `scripts/vendor-twilio-sdk.sh`
- Create: `chrome-extension/vendor/twilio-voice-2.18.3.min.js`
- Create: `chrome-extension/lib/dialer.js`
- Create: `chrome-extension/lib/dialer.test.js`
- Modify: `Makefile`

**Interfaces:**
- Consumes: nothing (pure module)
- Produces:
  - `normalizeDialTarget(raw, defaultCountryCode = '34') -> string | null`
  - `canStartCall({ isRecording, isTabCapturing, callState }) -> { ok: boolean, reason: string | null }`
  - `callButtonLabel(callState) -> string`
  - `CALL_STATES` = `{ IDLE, CONNECTING, RINGING, ACTIVE, ENDING }`

- [ ] **Step 1: Vendor the SDK**

`@twilio/voice-sdk` ships a prebuilt UMD bundle at `dist/twilio.min.js` that attaches `globalThis.Twilio.Device`. That is what makes this work without adding a bundler to the extension.

Create `scripts/vendor-twilio-sdk.sh`:

```bash
#!/usr/bin/env bash
# Vendor the Twilio Voice SDK browser bundle into the Chrome extension.
#
# The extension has no build step: manifest.json loads plain ES modules and
# package-chrome-extension.sh ships raw source. MV3 also forbids remote code.
# So we commit Twilio's own prebuilt UMD bundle, which exposes
# globalThis.Twilio.Device.
set -euo pipefail

VERSION="${1:-2.18.3}"
DEST="chrome-extension/vendor/twilio-voice-${VERSION}.min.js"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

( cd "$TMP" && npm pack "@twilio/voice-sdk@${VERSION}" --silent >/dev/null )
tar -xzf "$TMP/twilio-voice-sdk-${VERSION}.tgz" -C "$TMP"

mkdir -p "$(dirname "$DEST")"
cp "$TMP/package/dist/twilio.min.js" "$DEST"

grep -q "root.Twilio" "$DEST" || { echo "unexpected bundle shape" >&2; exit 1; }
echo "vendored $DEST ($(wc -c <"$DEST") bytes)"
```

Run:

```bash
chmod +x scripts/vendor-twilio-sdk.sh && ./scripts/vendor-twilio-sdk.sh 2.18.3
```

Expected: `vendored chrome-extension/vendor/twilio-voice-2.18.3.min.js (302... bytes)`

Add to `Makefile`:

```makefile
vendor-twilio:
	./scripts/vendor-twilio-sdk.sh 2.18.3
```

Verify the packaging script keeps it:

```bash
grep -n "exclude" scripts/package-chrome-extension.sh
```

Expected: no exclusion matches `vendor`. If one does, remove it.

- [ ] **Step 2: Write the failing tests**

Create `chrome-extension/lib/dialer.test.js`:

```javascript
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  CALL_STATES,
  callButtonLabel,
  canStartCall,
  normalizeDialTarget,
} from './dialer.js';

describe('normalizeDialTarget', () => {
  it('passes through E.164', () => {
    assert.equal(normalizeDialTarget('+34600111222'), '+34600111222');
  });

  it('strips the formatting HubSpot contacts arrive with', () => {
    assert.equal(normalizeDialTarget('+34 600 111 222'), '+34600111222');
    assert.equal(normalizeDialTarget('(+34) 600-111.222'), '+34600111222');
  });

  it('adds the default country code to a national number', () => {
    assert.equal(normalizeDialTarget('600111222'), '+34600111222');
  });

  it('drops the national trunk prefix', () => {
    assert.equal(normalizeDialTarget('0600111222'), '+34600111222');
  });

  it('converts a 00 international prefix', () => {
    assert.equal(normalizeDialTarget('0034600111222'), '+34600111222');
  });

  it('honours a non-Spanish default country code', () => {
    assert.equal(normalizeDialTarget('600111222', '351'), '+351600111222');
  });

  it('returns null for junk instead of dialling it', () => {
    assert.equal(normalizeDialTarget(''), null);
    assert.equal(normalizeDialTarget('n/a'), null);
    assert.equal(normalizeDialTarget('600'), null);
    assert.equal(normalizeDialTarget(null), null);
  });
});

describe('canStartCall', () => {
  const idle = { isRecording: false, isTabCapturing: false, callState: CALL_STATES.IDLE };

  it('allows a call when nothing else owns the mic', () => {
    assert.deepEqual(canStartCall(idle), { ok: true, reason: null });
  });

  it('blocks while a voice memo is recording', () => {
    const result = canStartCall({ ...idle, isRecording: true });
    assert.equal(result.ok, false);
    assert.match(result.reason, /nota de voz/i);
  });

  it('blocks while Listen is capturing tab audio', () => {
    const result = canStartCall({ ...idle, isTabCapturing: true });
    assert.equal(result.ok, false);
    assert.match(result.reason, /listen/i);
  });

  it('blocks a second call while one is active', () => {
    const result = canStartCall({ ...idle, callState: CALL_STATES.ACTIVE });
    assert.equal(result.ok, false);
    assert.match(result.reason, /llamada/i);
  });

  it('blocks while a call is still connecting', () => {
    assert.equal(canStartCall({ ...idle, callState: CALL_STATES.CONNECTING }).ok, false);
  });
});

describe('callButtonLabel', () => {
  it('labels every state', () => {
    assert.equal(callButtonLabel(CALL_STATES.IDLE), 'Llamar');
    assert.equal(callButtonLabel(CALL_STATES.CONNECTING), 'Conectando…');
    assert.equal(callButtonLabel(CALL_STATES.RINGING), 'Llamando…');
    assert.equal(callButtonLabel(CALL_STATES.ACTIVE), 'Colgar');
    assert.equal(callButtonLabel(CALL_STATES.ENDING), 'Colgando…');
  });

  it('falls back to Llamar for an unknown state', () => {
    assert.equal(callButtonLabel('bogus'), 'Llamar');
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd chrome-extension && node --test lib/dialer.test.js`
Expected: FAIL — `Cannot find module .../lib/dialer.js`

- [ ] **Step 4: Write the implementation**

Create `chrome-extension/lib/dialer.js`:

```javascript
/**
 * Dialer logic: number normalization and mutual exclusion.
 *
 * Pure module — no chrome.* and no Twilio. The offscreen document owns the
 * Twilio Device; this file owns the decisions, so they stay unit-testable.
 *
 * The mic is a single resource shared with voice memos and Listen, so a call
 * can only start when neither of those holds it.
 */

export const CALL_STATES = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  RINGING: 'ringing',
  ACTIVE: 'active',
  ENDING: 'ending',
};

const SEPARATORS = /[\s().\-/]/g;
const DIGITS_ONLY = /^\d+$/;
const E164 = /^\+[1-9]\d{7,14}$/;

/**
 * Best-effort E.164 for phone numbers coming out of CRM free-text fields.
 * Returns null rather than guessing when the value cannot be a phone number.
 */
export function normalizeDialTarget(raw, defaultCountryCode = '34') {
  if (typeof raw !== 'string') return null;
  let value = raw.replace(SEPARATORS, '').trim();
  if (!value) return null;

  if (value.startsWith('00')) {
    value = `+${value.slice(2)}`;
  } else if (!value.startsWith('+')) {
    if (!DIGITS_ONLY.test(value)) return null;
    value = `+${defaultCountryCode}${value.replace(/^0+/, '')}`;
  }

  return E164.test(value) ? value : null;
}

export function canStartCall({ isRecording, isTabCapturing, callState } = {}) {
  if (isRecording) {
    return { ok: false, reason: 'Para la nota de voz antes de llamar.' };
  }
  if (isTabCapturing) {
    return { ok: false, reason: 'Para Listen antes de llamar.' };
  }
  if (callState && callState !== CALL_STATES.IDLE) {
    return { ok: false, reason: 'Ya hay una llamada en curso.' };
  }
  return { ok: true, reason: null };
}

export function callButtonLabel(callState) {
  switch (callState) {
    case CALL_STATES.CONNECTING:
      return 'Conectando…';
    case CALL_STATES.RINGING:
      return 'Llamando…';
    case CALL_STATES.ACTIVE:
      return 'Colgar';
    case CALL_STATES.ENDING:
      return 'Colgando…';
    default:
      return 'Llamar';
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd chrome-extension && node --test lib/dialer.test.js`
Expected: PASS (18 subtests)

- [ ] **Step 6: Commit**

```bash
git add scripts/vendor-twilio-sdk.sh Makefile \
        chrome-extension/vendor/twilio-voice-2.18.3.min.js \
        chrome-extension/lib/dialer.js chrome-extension/lib/dialer.test.js
git commit -m "feat(extension): vendor Twilio Voice SDK and add dialer logic"
```

---

### Task 8: Extension — Twilio Device in the offscreen document

**Files:**
- Modify: `chrome-extension/offscreen.html`
- Modify: `chrome-extension/offscreen.js`
- Modify: `chrome-extension/background.js`
- Modify: `chrome-extension/lib/api.js`

**Interfaces:**
- Consumes: `CALL_STATES`, `canStartCall` from `lib/dialer.js`; `globalThis.Twilio.Device` from the vendored bundle
- Produces:
  - Service worker → offscreen: `{ target: 'offscreen', type: 'START_CALL', token, to, callerId, contactId, dealId, hubId }` and `{ target: 'offscreen', type: 'HANGUP_CALL' }`
  - Offscreen → service worker: `{ type: 'CALL_STATE', state, error? }` where `state` is a `CALL_STATES` value
  - `api.getCallingConfig()`, `api.createVoiceToken()`, `api.verifyCallerId(phoneNumber, label)` in `lib/api.js`
  - Background state additions: `state.call = { state, to, callerId, error }`
  - Popup → background: `{ type: 'START_CALL', to, callerId }`, `{ type: 'HANGUP_CALL' }`, `{ type: 'GET_CALLING_CONFIG' }`, `{ type: 'VERIFY_CALLER_ID', phoneNumber, label }`

- [ ] **Step 1: Load the vendored bundle in the offscreen document**

In `chrome-extension/offscreen.html`, add the classic script tag **before** the existing module script so `globalThis.Twilio` exists when the module runs:

```html
<body>
  <script src="vendor/twilio-voice-2.18.3.min.js"></script>
  <script src="offscreen.js" type="module"></script>
</body>
```

Verify no CSP change is needed: MV3's default extension-page CSP is `script-src 'self'`, and a packaged file is `'self'`.

- [ ] **Step 2: Add the Device lifecycle to the offscreen document**

In `chrome-extension/offscreen.js`, add at the top with the other imports:

```javascript
import { CALL_STATES } from './lib/dialer.js';
```

Add module state next to the existing `mediaRecorder` / `websocket` declarations:

```javascript
let twilioDevice = null;
let activeCall = null;
```

Add these functions:

```javascript
function reportCallState(state, error) {
  chrome.runtime.sendMessage({ type: 'CALL_STATE', state, error: error || null });
}

async function startCall({ token, to, callerId, contactId, dealId, hubId }) {
  try {
    if (!globalThis.Twilio?.Device) {
      throw new Error('Twilio Voice SDK no cargado');
    }
    // Recreated per call: the AccessToken is short-lived and outbound-only,
    // so there is nothing to keep registered between calls.
    if (twilioDevice) {
      twilioDevice.destroy();
      twilioDevice = null;
    }
    twilioDevice = new globalThis.Twilio.Device(token, {
      codecPreferences: ['opus', 'pcmu'],
      logLevel: 'warn',
    });

    reportCallState(CALL_STATES.CONNECTING);

    // `To` and `CallerId` reach the TwiML App's Voice URL as POST params.
    // CallerId is only a preference — the backend authorizes it.
    activeCall = await twilioDevice.connect({
      params: {
        To: to,
        CallerId: callerId,
        ContactId: contactId || '',
        DealId: dealId || '',
        HubId: hubId || '',
      },
    });

    activeCall.on('ringing', () => reportCallState(CALL_STATES.RINGING));
    activeCall.on('accept', () => reportCallState(CALL_STATES.ACTIVE));
    activeCall.on('disconnect', () => {
      activeCall = null;
      reportCallState(CALL_STATES.IDLE);
    });
    activeCall.on('cancel', () => {
      activeCall = null;
      reportCallState(CALL_STATES.IDLE);
    });
    activeCall.on('error', (err) => {
      activeCall = null;
      reportCallState(CALL_STATES.IDLE, err?.message || 'Error de llamada');
    });
  } catch (error) {
    activeCall = null;
    reportCallState(CALL_STATES.IDLE, error.message || 'No se pudo iniciar la llamada');
  }
}

function hangupCall() {
  reportCallState(CALL_STATES.ENDING);
  try {
    if (activeCall) activeCall.disconnect();
  } catch (_) {
    /* already gone */
  }
  activeCall = null;
  if (twilioDevice) {
    twilioDevice.destroy();
    twilioDevice = null;
  }
  reportCallState(CALL_STATES.IDLE);
}
```

Extend the existing `chrome.runtime.onMessage` switch in the same file:

```javascript
    case 'START_CALL':
      startCall(message);
      break;
    case 'HANGUP_CALL':
      hangupCall();
      break;
```

- [ ] **Step 3: Add the API client methods**

In `chrome-extension/lib/api.js`, add to the exported api object next to `uploadTranscript`:

```javascript
  async getCallingConfig() {
    return request('/calls/config');
  },

  async createVoiceToken() {
    return request('/calls/token', { method: 'POST', body: JSON.stringify({}) });
  },

  async verifyCallerId(phoneNumber, label) {
    return request('/calls/caller-ids', {
      method: 'POST',
      body: JSON.stringify({ phoneNumber, label: label || null }),
    });
  },
```

- [ ] **Step 4: Wire the service worker**

In `chrome-extension/background.js`, add the import:

```javascript
import { CALL_STATES, canStartCall, normalizeDialTarget } from './lib/dialer.js';
```

Initialize call state alongside the other `state` fields:

```javascript
  call: { state: CALL_STATES.IDLE, to: null, callerId: null, error: null },
```

Add the call orchestration:

```javascript
async function startCallFlow({ to, callerId }) {
  const gate = canStartCall({
    isRecording: state.isRecording,
    isTabCapturing: state.isTabCapturing,
    callState: state.call.state,
  });
  if (!gate.ok) return { ok: false, error: gate.reason };

  const target = normalizeDialTarget(to);
  if (!target) return { ok: false, error: 'Numero de telefono no valido.' };

  let token;
  try {
    ({ token } = await api.createVoiceToken());
  } catch (e) {
    return { ok: false, error: 'No se pudo obtener el token de llamada.' };
  }

  await getOffscreenDocument();
  const context = state.context || {};
  chrome.runtime.sendMessage({
    target: 'offscreen',
    type: 'START_CALL',
    token,
    to: target,
    callerId,
    contactId: context.contactId || null,
    dealId: context.objectType === 'deal' ? context.recordId : null,
    hubId: context.hubId || null,
  });

  // updateState (background.js:214) shallow-merges and broadcasts
  // STATE_UPDATED, so `call` must be replaced whole, not mutated.
  updateState({
    call: { state: CALL_STATES.CONNECTING, to: target, callerId, error: null },
  });
  return { ok: true, to: target };
}

function hangupCallFlow() {
  chrome.runtime.sendMessage({ target: 'offscreen', type: 'HANGUP_CALL' });
  updateState({ call: { ...state.call, state: CALL_STATES.ENDING } });
  return { ok: true };
}
```

Handle the offscreen report and the popup messages in the existing `chrome.runtime.onMessage` handler:

```javascript
  if (message.type === 'CALL_STATE') {
    updateState({
      call: {
        ...state.call,
        state: message.state,
        error: message.error || null,
        to: message.state === CALL_STATES.IDLE ? null : state.call.to,
      },
    });
    return;
  }

  if (message.type === 'START_CALL') {
    startCallFlow(message).then(sendResponse);
    return true;
  }

  if (message.type === 'HANGUP_CALL') {
    sendResponse(hangupCallFlow());
    return true;
  }

  if (message.type === 'GET_CALLING_CONFIG') {
    api.getCallingConfig().then(sendResponse).catch(() =>
      sendResponse({ enabled: false, callerIds: [] })
    );
    return true;
  }

  if (message.type === 'VERIFY_CALLER_ID') {
    api
      .verifyCallerId(message.phoneNumber, message.label)
      .then((r) => sendResponse({ ok: true, ...r }))
      .catch((e) => sendResponse({ ok: false, error: e.message }));
    return true;
  }
```

`updateState` and `getOffscreenDocument` both already exist in `background.js` (lines 214 and 318) — do not add new helpers.

- [ ] **Step 5: Verify the extension still loads and existing tests pass**

Run: `cd chrome-extension && node --test lib/*.test.js`
Expected: PASS, no regressions.

Then load the unpacked extension in Chrome and confirm: no service worker errors in `chrome://extensions`, and mic memos plus Listen still work (the offscreen document is shared, so this is the real regression risk).

- [ ] **Step 6: Commit**

```bash
git add chrome-extension/offscreen.html chrome-extension/offscreen.js \
        chrome-extension/background.js chrome-extension/lib/api.js
git commit -m "feat(extension): Twilio Device in offscreen document"
```

---

### Task 9: Extension — dial UI in the side panel

**Files:**
- Modify: `chrome-extension/popup/index.html`
- Modify: `chrome-extension/popup/popup.js`

**Interfaces:**
- Consumes: `CALL_STATES`, `callButtonLabel`, `normalizeDialTarget` from `lib/dialer.js`; background messages `START_CALL`, `HANGUP_CALL`, `GET_CALLING_CONFIG`, `VERIFY_CALLER_ID`; `state.call` and `state.context.contactPhone` from `STATE_UPDATED`
- Produces: no new exports — UI only

- [ ] **Step 1: Expose the contact phone through page context**

The dial target comes from HubSpot. `GET /api/v1/crm/hubspot/contacts/{id}/context` already returns `contactPhone`, but `background.js` drops it when building `enriched`. In `background.js`, add it to the contact branch of the enrichment (the block that sets `contactName` / `contactEmail`):

```javascript
      contactPhone: contactCtx?.contactPhone || null,
```

- [ ] **Step 2: Add the markup**

In `chrome-extension/popup/index.html`, inside `#screen-record` immediately after `#record-context-strip`, add:

```html
<section id="call-section" hidden>
  <div class="call-row">
    <input id="call-number" type="tel" inputmode="tel" placeholder="+34 600 111 222" />
    <select id="call-caller-id" aria-label="Numero desde el que llamas"></select>
    <button id="call-button" type="button">Llamar</button>
  </div>
  <p id="call-status" class="call-status" hidden></p>
  <div id="caller-id-setup" hidden>
    <p class="call-hint">
      Verifica tu numero para que sea el que vean tus prospectos.
      Twilio te llamara en ingles desde un numero de Estados Unidos.
    </p>
    <div class="call-row">
      <input id="caller-id-number" type="tel" placeholder="+34 910 000 000" />
      <button id="caller-id-verify" type="button">Verificar</button>
    </div>
    <p id="caller-id-code" class="call-code" hidden></p>
  </div>
</section>
```

- [ ] **Step 3: Wire the UI**

In `chrome-extension/popup/popup.js`, add the import:

```javascript
import { CALL_STATES, callButtonLabel, normalizeDialTarget } from '../lib/dialer.js';
```

Add element lookups next to the other `document.getElementById` calls, then these functions:

```javascript
let callingConfig = { enabled: false, callerIds: [] };

async function loadCallingConfig() {
  callingConfig = await chrome.runtime.sendMessage({ type: 'GET_CALLING_CONFIG' });
  renderCallSection();
}

function verifiedCallerIds() {
  return (callingConfig.callerIds || []).filter((c) => c.status === 'verified');
}

function renderCallSection() {
  const section = document.getElementById('call-section');
  if (!callingConfig.enabled) {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  const verified = verifiedCallerIds();
  document.getElementById('caller-id-setup').hidden = verified.length > 0;

  const select = document.getElementById('call-caller-id');
  select.hidden = verified.length === 0;
  select.innerHTML = verified
    .map(
      (c) =>
        `<option value="${escapeHtml(c.phoneNumber)}"${c.isDefault ? ' selected' : ''}>` +
        `${escapeHtml(c.label || c.phoneNumber)}</option>`
    )
    .join('');

  // lastBgState (popup.js:1028) is the cached background state.
  const call = lastBgState?.call || { state: CALL_STATES.IDLE };
  const button = document.getElementById('call-button');
  button.textContent = callButtonLabel(call.state);
  button.disabled = verified.length === 0;

  const input = document.getElementById('call-number');
  if (!input.value && lastBgState?.context?.contactPhone) {
    input.value = lastBgState.context.contactPhone;
  }

  const status = document.getElementById('call-status');
  status.hidden = !call.error;
  status.textContent = call.error || '';
}

async function handleCallButton() {
  const call = lastBgState?.call || { state: CALL_STATES.IDLE };
  if (call.state !== CALL_STATES.IDLE) {
    await chrome.runtime.sendMessage({ type: 'HANGUP_CALL' });
    return;
  }

  const raw = document.getElementById('call-number').value;
  const target = normalizeDialTarget(raw);
  const status = document.getElementById('call-status');
  if (!target) {
    status.hidden = false;
    status.textContent = 'Numero no valido.';
    return;
  }

  const result = await chrome.runtime.sendMessage({
    type: 'START_CALL',
    to: target,
    callerId: document.getElementById('call-caller-id').value,
  });
  if (!result?.ok) {
    status.hidden = false;
    status.textContent = result?.error || 'No se pudo iniciar la llamada.';
  }
}

async function handleVerifyCallerId() {
  const phoneNumber = document.getElementById('caller-id-number').value;
  const codeEl = document.getElementById('caller-id-code');
  const result = await chrome.runtime.sendMessage({
    type: 'VERIFY_CALLER_ID',
    phoneNumber,
    label: null,
  });
  codeEl.hidden = false;
  codeEl.textContent = result?.ok
    ? `Te llamamos ahora. Teclea este codigo: ${result.verificationCode}`
    : result?.error || 'No se pudo iniciar la verificacion.';
  if (result?.ok) setTimeout(loadCallingConfig, 20000);
}
```

Register the listeners next to the existing ones, and call `loadCallingConfig()` from `init()`:

```javascript
document.getElementById('call-button').addEventListener('click', handleCallButton);
document
  .getElementById('caller-id-verify')
  .addEventListener('click', handleVerifyCallerId);
```

Hook the repaint into the `STATE_UPDATED` listener (`popup.js:3410`), **not** inside `renderState`:

```javascript
  if (message.type === 'STATE_UPDATED') {
    renderState(message.state);
    // renderState bails out early when its paint keys are unchanged
    // (popup.js:1032), and call state is not part of those keys.
    renderCallSection();
  }
```

- [ ] **Step 4: Manual verification of the whole loop**

With the backend running, a verified caller ID, and a real Twilio TwiML App pointed at the public backend URL:

1. Open a HubSpot contact that has a phone number. Confirm the number prefills.
2. Click **Llamar**. Confirm the button moves through Conectando → Llamando → Colgar.
3. Answer on the target phone. Confirm the Spanish recording disclosure plays to the *called* party and the SDR hears ringback during it.
4. Talk for ~20 seconds, then hang up.
5. Confirm within ~1 minute: a row in `outbound_calls` with `status='logged'` and a `recording_path`; a memo with `source='vocify_call'` reaching `pending_review`; a call engagement on the HubSpot contact timeline with playable audio that can be scrubbed.

If scrubbing does not work, the signed URL is not returning `206` — check `GET /public/hubspot/recordings/{call_sid}` and follow the URL with `curl -H 'Range: bytes=0-1023' -i`.

- [ ] **Step 5: Run all JS tests**

Run: `make test-js`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add chrome-extension/popup/index.html chrome-extension/popup/popup.js \
        chrome-extension/background.js
git commit -m "feat(extension): click-to-call UI with verified caller ID"
```

---

### Task 10: Setup runbook and compliance notes

**Files:**
- Create: `docs/runbooks/twilio-setup.md`

**Interfaces:**
- Consumes: everything built in Tasks 1–9
- Produces: no code

- [ ] **Step 1: Write the runbook**

Create `docs/runbooks/twilio-setup.md`:

```markdown
# Twilio outbound calling — setup

## Twilio console, once per environment

1. **API Key** (Account → API keys & tokens → Create standard key).
   → `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET`
2. **TwiML App** (Voice → TwiML → TwiML Apps → Create).
   Voice Request URL: `https://<BACKEND_PUBLIC_URL>/webhooks/twilio/voice`, method `POST`.
   → `TWILIO_TWIML_APP_SID`
3. Copy Account SID and Auth Token → `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`.
   The Auth Token is used only to validate webhook signatures.
4. **Do not buy a phone number.** Caller ID comes from each user's verified
   number, so there is no number rental and no regulatory bundle.

## HubSpot, once per app

Register the recording endpoint (see Task 6, Step 7). Confirm with:

    GET /crm/extensions/calling/2026-03/{appId}/settings/recording

The registered URL must end in `/public/hubspot/recordings/%s`.

## Local development

Twilio must reach the webhooks, so tunnel the backend (`ngrok http 8888`) and
point the TwiML App at the tunnel. Set `BACKEND_PUBLIC_URL` to the tunnel URL —
the signature check rebuilds the signed URL from it, so a mismatch produces 403.
`TWILIO_SKIP_SIG_CHECK=1` bypasses the check for curl-based testing only.

## Cost per connected minute (Spain, Spanish caller ID)

| Component | $/min |
|---|---|
| PSTN to Spanish mobile, EEA origination | 0.0486 |
| PSTN to Spanish landline | 0.0178 |
| Browser leg (billed separately from voice) | 0.0040 |
| Recording | 0.0025 |
| Storage | 0.0005 /min/month (first 10,000 min free) |
| Deepgram Nova-3 batch | 0.0043 |

Roughly $0.059/min to mobile and $0.029/min to landline. Twilio bills only
answered calls but **rounds each up to the next minute**, so short calls are
disproportionately expensive at SDR volumes.

A Spanish caller ID is what earns the EEA origination rate: the same call with
non-EEA origination is $0.1800/min, 3.7x more. Confirm the live rate with the
Pricing API for a real number before committing to a price:

    GET https://pricing.twilio.com/v2/Voice/Numbers/{destination}?OriginationNumber={spanish_cli}

Two figures were not verifiable from public docs and should be confirmed with
Twilio: whether dual-channel recording bills at 1x or 2x per minute, and the
maximum number of Verified Caller IDs per (sub)account.

## Compliance

- **AEPD Circular 1/2023** requires telling the person at the start of the call
  that it is being recorded and why. `TWILIO_RECORDING_ANNOUNCEMENT` plays to
  the called party via `<Number url>` and, because `record-from-answer-dual`
  starts at answer, the disclosure is inside the recording — which is the proof.
- Recordings must not be reused for purposes beyond the stated one without a
  separate legal basis. The `call-recordings` bucket is private; agree a
  retention period and add a deletion job before rolling out broadly.
- **Orden TDF/149/2025** restricts mobile numbers as caller ID for commercial
  calls. Steer users toward a geographic office number, not a personal mobile.
- Twilio's caller ID verification call is English-only from a US number. The
  side panel must show the code and warn about this, or activation will suffer.
```

- [ ] **Step 2: Verify every referenced env var exists**

Run:

```bash
grep -c TWILIO_ .env.example && \
cd backend && python -c "
from app.config import settings
for k in ('TWILIO_ACCOUNT_SID','TWILIO_AUTH_TOKEN','TWILIO_API_KEY_SID',
          'TWILIO_API_KEY_SECRET','TWILIO_TWIML_APP_SID','HUBSPOT_APP_ID',
          'TWILIO_RECORDING_ANNOUNCEMENT','CALLING_DEFAULT_COUNTRY_CODE',
          'CALL_RECORDING_URL_TTL_SECONDS'):
    assert hasattr(settings, k), k
print('all settings present')
"
```

Expected: `all settings present`

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/twilio-setup.md
git commit -m "docs(calling): Twilio setup runbook, cost model and compliance"
```

---

## Follow-ups (not in this plan)

- **Twilio subaccounts per customer.** Verified caller IDs and usage are per
  (sub)account; the ISV pattern is one subaccount per customer plus the Usage
  Records API for per-customer cost. Required before billing calling usage.
- **Telnyx as a second carrier.** Its verification supports SMS and DTMF
  instead of an English robocall, which is the single biggest onboarding
  friction here. Tasks 1–6 are already shaped so a carrier is swappable behind
  four operations: verify caller ID, place call, receive recording, fetch audio.
- **Recording retention job.** RGPD requires a bounded retention period.
- **Inbound / callbacks.** Today callbacks ring the SDR's own phone and are not
  recorded. Closing that gap means renting a number and forwarding.
- **Salesforce call logging**, mirroring `services/salesforce/sync.py`.
