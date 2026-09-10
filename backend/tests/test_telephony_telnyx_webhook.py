"""Park-and-bridge Telnyx voice webhook.

Fixture envelope matches Telnyx Voice API webhooks (`call.initiated` +
`state=parked`) with `custom_headers` and `from` = SIP username.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import nacl.encoding
import nacl.signing
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from app.api import webhooks
from app.api.webhooks import router as webhooks_router
from app.services.telephony.telnyx_client import TelnyxClient

USER_ID = "11111111-1111-1111-1111-111111111111"
SIP_USERNAME = "userabc"
PARKED_ID = "v3:parked-leg"
PSTN_ID = "v3:pstn-leg"
SESSION_ID = "428c31b6-abf3-3bc1-b7f4-5013ef9657c1"
VERIFIED_CLI = "+34910000000"
PROSPECT = "+34600111222"

# Telnyx outbound-dialer / Voice API envelope: parked WebRTC leg.
PARKED_INITIATED = {
    "data": {
        "record_type": "event",
        "event_type": "call.initiated",
        "id": "0ccc7b54-4df3-4bca-a65a-3da1ecc777f0",
        "occurred_at": "2018-02-02T22:25:27.521992Z",
        "payload": {
            "call_control_id": PARKED_ID,
            "connection_id": "7267xxxxxxxxxxxxxx",
            "call_leg_id": "d14dbcee-880b-11eb-8204-02420a0f7568",
            "call_session_id": SESSION_ID,
            "client_state": None,
            "from": SIP_USERNAME,
            "to": PROSPECT,
            "direction": "incoming",
            "state": "parked",
            "custom_headers": [
                {
                    "header_name": "X-Vocify-Caller-Id",
                    "header_value": VERIFIED_CLI,
                },
                {
                    "header_name": "X-Vocify-Contact-Id",
                    "header_value": "123",
                },
                {
                    "header_name": "X-Vocify-Deal-Id",
                    "header_value": "456",
                },
            ],
        },
    },
    "meta": {
        "attempt": 1,
        "delivered_to": "https://api.getvocify.com/webhooks/telnyx/voice",
    },
}

PSTN_ANSWERED = {
    "data": {
        "record_type": "event",
        "event_type": "call.answered",
        "id": "1ddd8c65-5ef4-4cdb-b76b-4eb2fdd888f1",
        "occurred_at": "2018-02-02T22:25:29.000000Z",
        "payload": {
            "call_control_id": PSTN_ID,
            "connection_id": "7267xxxxxxxxxxxxxx",
            "call_leg_id": "e25eccff-990c-22fc-9315-13531b1f8679",
            "call_session_id": SESSION_ID,
            "from": VERIFIED_CLI,
            "to": PROSPECT,
            "direction": "outgoing",
        },
    },
    "meta": {"attempt": 1, "delivered_to": "https://api.getvocify.com/webhooks/telnyx/voice"},
}


class FakeQuery:
    """Minimal supabase-py chain; includes JSONB `contains` for provider_state."""

    def __init__(self, store: list[dict]):
        self.store = store
        self._filters: list[tuple[str, object]] = []
        self._contains: list[tuple[str, object]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._mutation: dict | None = None
        self._mutation_type: str | None = None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def contains(self, column, value):
        self._contains.append((column, value))
        return self

    def order(self, column, desc=False, **_k):
        self._order = (column, desc)
        return self

    def limit(self, n, *_a, **_k):
        self._limit = n
        return self

    def insert(self, row):
        self._mutation_type = "insert"
        self._mutation = row
        return self

    def update(self, row):
        self._mutation_type = "update"
        self._mutation = row
        return self

    def _matches(self, row: dict) -> bool:
        for column, value in self._filters:
            if row.get(column) != value:
                return False
        for column, value in self._contains:
            cell = row.get(column)
            if not isinstance(cell, dict) or not isinstance(value, dict):
                return False
            if any(cell.get(k) != v for k, v in value.items()):
                return False
        return True

    def _filtered_rows(self) -> list[dict]:
        rows = [r for r in self.store if self._matches(r)]
        if self._order is not None:
            column, desc = self._order
            rows = sorted(
                rows, key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc
            )
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows

    def execute(self):
        if self._mutation_type == "update":
            matched = self._filtered_rows()
            for row in matched:
                row.update(self._mutation or {})
            return SimpleNamespace(data=list(matched))
        if self._mutation_type == "insert":
            row = dict(self._mutation or {})
            self.store.append(row)
            return SimpleNamespace(data=[row])
        return SimpleNamespace(data=self._filtered_rows())


def _fake_supabase(tables: dict[str, list[dict]]):
    stores: dict[str, list[dict]] = {
        name: [dict(r) for r in rows] for name, rows in tables.items()
    }

    def make_table(name: str) -> FakeQuery:
        return FakeQuery(stores.setdefault(name, []))

    client = MagicMock()
    client.table.side_effect = make_table
    return client, stores


def _keys():
    signing = nacl.signing.SigningKey.generate()
    pub = signing.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()
    return signing, pub


def _signed_headers(signing, body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    signature = base64.b64encode(
        signing.sign(f"{timestamp}|".encode() + body).signature
    ).decode()
    return {
        "telnyx-timestamp": timestamp,
        "telnyx-signature-ed25519": signature,
        "content-type": "application/json",
    }


def _test_client() -> TestClient:
    app = FastAPI()
    app.include_router(webhooks_router, prefix="/webhooks")
    return TestClient(app)


def _event_body(event: dict) -> bytes:
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


def _parked(*, to: str | None = None, sip: str | None = None, headers=None) -> dict:
    event = copy.deepcopy(PARKED_INITIATED)
    payload = event["data"]["payload"]
    if to is not None:
        payload["to"] = to
    if sip is not None:
        payload["from"] = sip
    if headers is not None:
        payload["custom_headers"] = headers
    return event


def _credential_tables(*, caller_ids=None):
    tables = {
        "user_telephony_credentials": [
            {
                "user_id": USER_ID,
                "provider": "telnyx",
                "sip_username": SIP_USERNAME,
            }
        ],
        "user_caller_ids": caller_ids
        if caller_ids is not None
        else [
            {
                "user_id": USER_ID,
                "phone_number": VERIFIED_CLI,
                "status": "verified",
                "is_default": True,
            }
        ],
    }
    return tables


def _post(event: dict, *, signing, pub: str, supabase, telnyx, **setting_overrides):
    body = _event_body(event)
    settings = {
        "TELNYX_PUBLIC_KEY": pub,
        "CALLING_PROVIDER": "telnyx",
        "CALLING_DEFAULT_COUNTRY_CODE": "34",
        "CALLING_RECORDING_ANNOUNCEMENT_ENABLED": False,
        "TELNYX_RINGBACK_URL": "https://api.example/static/call-ringback.wav",
        "TELNYX_RING_WATCHDOG_SECS": 0,
        **setting_overrides,
    }
    with (
        patch("app.api.webhooks.get_supabase", return_value=supabase),
        patch("app.api.webhooks.telnyx_rest", return_value=telnyx, create=True),
        patch.multiple(webhooks.settings, **settings),
    ):
        return _test_client().post(
            "/webhooks/telnyx/voice",
            content=body,
            headers=_signed_headers(signing, body),
        )


class TestTelnyxVoiceSignature:
    def test_bad_signature_is_forbidden_and_does_not_dial(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(_credential_tables())
        telnyx = MagicMock()
        body = _event_body(PARKED_INITIATED)
        with (
            patch("app.api.webhooks.get_supabase", return_value=supabase),
            patch("app.api.webhooks.telnyx_rest", return_value=telnyx, create=True),
            patch.object(webhooks.settings, "TELNYX_PUBLIC_KEY", pub),
        ):
            resp = _test_client().post(
                "/webhooks/telnyx/voice",
                content=body,
                headers={
                    "telnyx-timestamp": str(int(time.time())),
                    "telnyx-signature-ed25519": "not-a-real-signature",
                    "content-type": "application/json",
                },
            )

        assert resp.status_code == 403
        telnyx.dial.assert_not_called()
        assert stores.get("outbound_calls", []) == []

    def test_twilio_provider_accepts_signature_and_does_not_dial(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(_credential_tables())
        telnyx = MagicMock()

        resp = _post(
            PARKED_INITIATED,
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
            CALLING_PROVIDER="twilio",
        )

        assert resp.status_code == 204
        telnyx.dial.assert_not_called()
        assert stores.get("outbound_calls", []) == []

    def test_client_disconnect_on_body_is_204(self):
        request = MagicMock()
        request.body = AsyncMock(side_effect=ClientDisconnect())
        resp = asyncio.run(webhooks.telnyx_voice(request, BackgroundTasks()))
        assert resp.status_code == 204


class TestTelnyxParkedInitiated:
    def test_unknown_sip_hangs_up_parked_and_does_not_insert(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase({})
        telnyx = MagicMock()

        resp = _post(PARKED_INITIATED, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)

        assert resp.status_code == 204
        telnyx.hangup.assert_called_once_with(PARKED_ID)
        telnyx.dial.assert_not_called()
        assert stores.get("outbound_calls", []) == []

    def test_emergency_to_hangs_up_and_does_not_dial(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(_credential_tables())
        telnyx = MagicMock()

        resp = _post(
            _parked(to="112"),
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
        )

        assert resp.status_code == 204
        telnyx.hangup.assert_called_once_with(PARKED_ID)
        telnyx.dial.assert_not_called()
        assert stores.get("outbound_calls", []) == []

    def test_unverified_cli_hangs_up_and_does_not_dial(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(
            _credential_tables(
                caller_ids=[
                    {
                        "user_id": "22222222-2222-2222-2222-222222222222",
                        "phone_number": "+34699999999",
                        "status": "verified",
                    }
                ]
            )
        )
        telnyx = MagicMock()

        resp = _post(
            _parked(
                headers=[
                    {
                        "header_name": "X-Vocify-Caller-Id",
                        "header_value": "+34699999999",
                    }
                ]
            ),
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
        )

        assert resp.status_code == 204
        telnyx.hangup.assert_called_once_with(PARKED_ID)
        telnyx.dial.assert_not_called()
        assert stores.get("outbound_calls", []) == []

    def test_happy_parked_inserts_and_dials_resolved_cli_without_bridge_intent(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(_credential_tables())
        http = MagicMock()
        http.post.return_value.status_code = 200
        http.post.return_value.content = b'{"data":{"call_control_id":"v3:pstn-leg"}}'
        http.post.return_value.json.return_value = {
            "data": {"call_control_id": PSTN_ID}
        }
        http.post.return_value.raise_for_status = lambda: None
        telnyx = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)

        resp = _post(PARKED_INITIATED, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)

        assert resp.status_code == 204
        dial_calls = [
            call
            for call in http.post.call_args_list
            if call.args and call.args[0] == "/calls"
        ]
        assert len(dial_calls) == 1
        body = dial_calls[0].kwargs["json"]
        assert body["from"] == VERIFIED_CLI
        assert body["to"] == PROSPECT
        assert body["link_to"] == PARKED_ID
        assert "bridge_intent" not in body
        row = stores["outbound_calls"][0]
        assert row["carrier"] == "telnyx"
        assert row["carrier_call_id"] == PARKED_ID
        assert row["from_number"] == VERIFIED_CLI
        assert row["to_number"] == PROSPECT
        assert row["hubspot_contact_id"] == "123"
        assert row["hubspot_deal_id"] == "456"
        assert row["hubspot_hub_id"] is None
        assert row["provider_state"] == {
            "parked_id": PARKED_ID,
            "pstn_id": PSTN_ID,
            "session_id": SESSION_ID,
        }

    def test_sip_uri_from_still_resolves_to_credential_user(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(_credential_tables())
        telnyx = MagicMock()
        telnyx.dial.return_value = {"call_control_id": PSTN_ID}

        resp = _post(
            _parked(sip="sip:userabc@sip.telnyx.com"),
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
        )

        assert resp.status_code == 204
        telnyx.hangup.assert_not_called()
        telnyx.dial.assert_called_once()
        assert telnyx.dial.call_args.kwargs["caller_id"] == VERIFIED_CLI
        assert telnyx.dial.call_args.kwargs["link_to"] == PARKED_ID
        assert stores["outbound_calls"][0]["user_id"] == USER_ID

    def test_dial_failure_after_insert_hangs_up_parked(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(_credential_tables())
        telnyx = MagicMock()
        telnyx.dial.side_effect = RuntimeError("telnyx dial failed")

        resp = _post(PARKED_INITIATED, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)

        assert resp.status_code == 204
        telnyx.hangup.assert_called_once_with(PARKED_ID)
        assert stores["outbound_calls"][0]["carrier_call_id"] == PARKED_ID
        assert stores["outbound_calls"][0]["status"] == "failed"
        assert stores["outbound_calls"][0]["provider_state"]["parked_id"] == PARKED_ID
        assert "pstn_id" not in stores["outbound_calls"][0]["provider_state"]

        telnyx.reset_mock()
        again = _post(PARKED_INITIATED, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)
        assert again.status_code == 204
        telnyx.dial.assert_not_called()
        telnyx.hangup.assert_not_called()

    def test_pstn_initiated_with_e164_from_does_not_hang_up(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase(_credential_tables())
        telnyx = MagicMock()
        telnyx.dial.return_value = {"call_control_id": PSTN_ID}

        first = _post(PARKED_INITIATED, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)
        assert first.status_code == 204
        telnyx.reset_mock()

        pstn_initiated = copy.deepcopy(PARKED_INITIATED)
        pstn_initiated["data"]["payload"]["from"] = PROSPECT
        pstn_initiated["data"]["payload"]["to"] = VERIFIED_CLI
        pstn_initiated["data"]["payload"]["call_control_id"] = PSTN_ID
        pstn_initiated["data"]["payload"]["state"] = "parked"

        resp = _post(pstn_initiated, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)

        assert resp.status_code == 204
        telnyx.hangup.assert_not_called()
        telnyx.dial.assert_not_called()

    def test_redelivery_skips_dial_when_pstn_id_already_set(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase(_credential_tables())
        telnyx = MagicMock()
        telnyx.dial.return_value = {"call_control_id": PSTN_ID}

        first = _post(PARKED_INITIATED, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)
        assert first.status_code == 204
        assert telnyx.dial.call_count == 1
        telnyx.reset_mock()

        resp = _post(PARKED_INITIATED, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)

        assert resp.status_code == 204
        telnyx.dial.assert_not_called()
        telnyx.hangup.assert_not_called()


class TestTelnyxAnsweredBridge:
    def test_answered_announcement_off_bridges_dual_wav(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "user_id": USER_ID,
                        "carrier": "telnyx",
                        "carrier_call_id": PARKED_ID,
                        "status": "dialing",
                        "provider_state": {"parked_id": PARKED_ID, "pstn_id": PSTN_ID},
                    }
                ]
            }
        )
        http = MagicMock()
        http.post.return_value.status_code = 200
        http.post.return_value.content = b""
        http.post.return_value.raise_for_status = lambda: None
        telnyx = TelnyxClient(api_key="KEY", connection_id="CONN", http=http)

        resp = _post(
            PSTN_ANSWERED,
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
            CALLING_RECORDING_ANNOUNCEMENT_ENABLED=False,
        )

        assert resp.status_code == 204
        assert http.post.call_count == 2
        assert http.post.call_args_list[0].args[0] == (
            f"/calls/{PARKED_ID}/actions/playback_stop"
        )
        path = http.post.call_args_list[1].args[0]
        assert path == f"/calls/{PARKED_ID}/actions/bridge"
        body = http.post.call_args_list[1].kwargs["json"]
        assert body["call_control_id"] == PSTN_ID
        assert body["record"] == "record-from-answer"
        assert body["record_channels"] == "dual"
        assert body["record_format"] == "wav"

    def test_answered_bridges_when_row_keyed_by_parked_id_only(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "user_id": USER_ID,
                        "carrier": "telnyx",
                        "carrier_call_id": PARKED_ID,
                        "status": "dialing",
                        "provider_state": {
                            "parked_id": PARKED_ID,
                            "session_id": SESSION_ID,
                        },
                    }
                ]
            }
        )
        telnyx = MagicMock()

        resp = _post(
            PSTN_ANSWERED,
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
            CALLING_RECORDING_ANNOUNCEMENT_ENABLED=False,
        )

        assert resp.status_code == 204
        telnyx.bridge.assert_called_once_with(PARKED_ID, PSTN_ID)

    def test_parked_leg_answered_does_not_bridge(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "user_id": USER_ID,
                        "carrier": "telnyx",
                        "carrier_call_id": PARKED_ID,
                        "status": "dialing",
                        "provider_state": {
                            "parked_id": PARKED_ID,
                            "pstn_id": PSTN_ID,
                            "session_id": SESSION_ID,
                        },
                    }
                ]
            }
        )
        telnyx = MagicMock()
        parked_answered = copy.deepcopy(PSTN_ANSWERED)
        parked_answered["data"]["payload"]["call_control_id"] = PARKED_ID

        resp = _post(
            parked_answered,
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
            CALLING_RECORDING_ANNOUNCEMENT_ENABLED=False,
        )

        assert resp.status_code == 204
        telnyx.bridge.assert_not_called()
        telnyx.speak.assert_not_called()
        telnyx.playback_start.assert_not_called()

    def test_answered_announcement_speaks_then_speak_ended_bridges(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "user_id": USER_ID,
                        "carrier": "telnyx",
                        "carrier_call_id": PARKED_ID,
                        "status": "dialing",
                        "provider_state": {
                            "parked_id": PARKED_ID,
                            "pstn_id": PSTN_ID,
                        },
                    }
                ]
            }
        )
        telnyx = MagicMock()

        answered = _post(
            PSTN_ANSWERED,
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
            CALLING_RECORDING_ANNOUNCEMENT_ENABLED=True,
        )
        assert answered.status_code == 204
        telnyx.speak.assert_called_once()
        assert telnyx.speak.call_args.args[0] == PSTN_ID
        telnyx.bridge.assert_not_called()

        speak_ended = {
            "data": {
                "event_type": "call.speak.ended",
                "payload": {
                    "call_control_id": PSTN_ID,
                    "call_session_id": SESSION_ID,
                },
            }
        }
        resp = _post(
            speak_ended,
            signing=signing,
            pub=pub,
            supabase=supabase,
            telnyx=telnyx,
            CALLING_RECORDING_ANNOUNCEMENT_ENABLED=True,
        )
        assert resp.status_code == 204
        telnyx.bridge.assert_called_once_with(PARKED_ID, PSTN_ID)


class TestTelnyxHangup:
    def test_parked_hangup_tears_down_pstn(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "user_id": USER_ID,
                        "carrier": "telnyx",
                        "carrier_call_id": PARKED_ID,
                        "status": "dialing",
                        "provider_state": {
                            "parked_id": PARKED_ID,
                            "pstn_id": PSTN_ID,
                        },
                    }
                ]
            }
        )
        telnyx = MagicMock()
        hangup = {
            "data": {
                "event_type": "call.hangup",
                "payload": {
                    "call_control_id": PARKED_ID,
                    "call_session_id": SESSION_ID,
                    "hangup_cause": "originator_cancel",
                },
            }
        }

        resp = _post(hangup, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)

        assert resp.status_code == 204
        telnyx.hangup.assert_called_once_with(PSTN_ID)

    def test_parked_hangup_without_pstn_does_not_rehangup_ended_leg(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "user_id": USER_ID,
                        "carrier": "telnyx",
                        "carrier_call_id": PARKED_ID,
                        "status": "failed",
                        "provider_state": {"parked_id": PARKED_ID},
                    }
                ]
            }
        )
        telnyx = MagicMock()
        hangup = {
            "data": {
                "event_type": "call.hangup",
                "payload": {
                    "call_control_id": PARKED_ID,
                    "call_session_id": SESSION_ID,
                    "hangup_cause": "originator_cancel",
                },
            }
        }

        with patch(
            "app.api.webhooks.log_missed_call_activity",
            new_callable=AsyncMock,
        ) as missed:
            resp = _post(
                hangup, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx
            )

        assert resp.status_code == 204
        telnyx.hangup.assert_not_called()
        missed.assert_called_once()

    def test_pstn_busy_hangs_up_parked_with_user_busy(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "user_id": USER_ID,
                        "carrier": "telnyx",
                        "carrier_call_id": PARKED_ID,
                        "status": "dialing",
                        "provider_state": {
                            "parked_id": PARKED_ID,
                            "pstn_id": PSTN_ID,
                        },
                    }
                ]
            }
        )
        telnyx = MagicMock()
        hangup = {
            "data": {
                "event_type": "call.hangup",
                "payload": {
                    "call_control_id": PSTN_ID,
                    "call_session_id": SESSION_ID,
                    "hangup_cause": "user_busy",
                    "sip_hangup_cause": "486",
                    "hangup_source": "unknown",
                },
            }
        }

        with patch(
            "app.api.webhooks.log_missed_call_activity",
            new_callable=AsyncMock,
        ) as missed:
            resp = _post(
                hangup, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx
            )

        assert resp.status_code == 204
        telnyx.playback_stop.assert_called_once_with(PARKED_ID)
        telnyx.hangup.assert_called_once_with(PARKED_ID, cause="USER_BUSY")
        assert missed.await_count == 1
        assert stores["outbound_calls"][0]["call_disposition"] == "busy"
        assert stores["outbound_calls"][0]["provider_state"]["pstn_hangup"] == {
            "cause": "user_busy",
            "sip": "486",
            "source": "unknown",
        }

    def test_call_cost_merges_onto_provider_state_after_busy(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "user_id": USER_ID,
                        "carrier": "telnyx",
                        "carrier_call_id": PARKED_ID,
                        "status": "logged",
                        "call_disposition": "busy",
                        "provider_state": {
                            "parked_id": PARKED_ID,
                            "pstn_id": PSTN_ID,
                            "pstn_hangup": {
                                "cause": "user_busy",
                                "sip": "486",
                                "source": "unknown",
                            },
                        },
                    }
                ]
            }
        )
        telnyx = MagicMock()
        cost = {
            "data": {
                "event_type": "call.cost",
                "payload": {
                    "call_control_id": PSTN_ID,
                    "call_session_id": SESSION_ID,
                    "total_cost": "0.0000",
                    "billed_duration_secs": 0,
                    "cost_parts": [
                        {"type": "sip-trunking", "cost": "0.0000"},
                        {"type": "call-control", "cost": "0.0000", "rate": "0.00200"},
                    ],
                },
            }
        }

        resp = _post(cost, signing=signing, pub=pub, supabase=supabase, telnyx=telnyx)

        assert resp.status_code == 204
        state = stores["outbound_calls"][0]["provider_state"]
        assert state["pstn_hangup"]["cause"] == "user_busy"
        assert state["pstn_cost"] == {
            "total": "0.0000",
            "billed_duration_secs": 0,
            "parts": [
                {"type": "sip-trunking", "cost": "0.0000"},
                {"type": "call-control", "cost": "0.0000", "rate": "0.00200"},
            ],
        }


RECORDING_ID = "rec-1"


def _close_created_task(coro, *args, **kwargs):
    if hasattr(coro, "close"):
        coro.close()
    return MagicMock()


def _recording_saved(**payload_overrides) -> dict:
    payload = {
        "call_control_id": PARKED_ID,
        "call_session_id": SESSION_ID,
        "client_state": None,
        "recording_id": RECORDING_ID,
        "recording_started_at": "2018-02-02T22:20:27.521992Z",
        "recording_ended_at": "2018-02-02T22:21:27.521992Z",
        "channels": "dual",
        "format": "wav",
    }
    payload.update(payload_overrides)
    return {"data": {"event_type": "call.recording.saved", "payload": payload}}


def _recorded_row(**overrides) -> dict:
    row = {
        "user_id": USER_ID,
        "carrier": "telnyx",
        "carrier_call_id": PARKED_ID,
        "status": "dialing",
        "memo_id": None,
        "hubspot_contact_id": "123",
        "provider_state": {
            "parked_id": PARKED_ID,
            "pstn_id": PSTN_ID,
            "session_id": SESSION_ID,
        },
    }
    row.update(overrides)
    return row


class TestTelnyxRecordingSaved:
    def test_recording_saved_uploads_and_starts_memo_pipeline(self):
        signing, pub = _keys()
        supabase, stores = _fake_supabase({"outbound_calls": [_recorded_row()]})
        telnyx = MagicMock()

        with (
            patch(
                "app.api.webhooks.download_telnyx_recording",
                new_callable=AsyncMock,
                return_value=b"RIFF....",
            ) as download,
            patch(
                "app.api.webhooks.StorageService.upload_call_recording",
                new_callable=AsyncMock,
                return_value=f"{USER_ID}/{PARKED_ID}.wav",
            ) as upload,
            patch(
                "app.api.webhooks.attach_hubspot_contact_by_phone",
                new_callable=AsyncMock,
                side_effect=lambda _sb, row: row,
            ),
            patch(
                "app.api.webhooks.initiate_vocify_call_memo",
                new_callable=AsyncMock,
                return_value=("memo-1", True),
            ) as initiate,
            patch(
                "app.api.webhooks.process_vocify_call_background",
                new_callable=AsyncMock,
            ) as process,
            patch(
                "app.api.webhooks.asyncio.create_task",
                side_effect=_close_created_task,
            ) as create_task,
        ):
            resp = _post(
                _recording_saved(),
                signing=signing,
                pub=pub,
                supabase=supabase,
                telnyx=telnyx,
            )

        assert resp.status_code == 204
        download.assert_awaited_once_with(RECORDING_ID)
        upload.assert_awaited_once()
        initiate.assert_awaited_once()
        create_task.assert_called_once()
        process.assert_called_once()
        assert process.call_args.args[0] == "memo-1"
        assert process.call_args.args[1] == USER_ID
        assert process.call_args.args[2] == PARKED_ID
        assert process.call_args.args[3] == b"RIFF...."
        row = stores["outbound_calls"][0]
        assert row["recording_sid"] == RECORDING_ID
        assert row["recording_path"] == f"{USER_ID}/{PARKED_ID}.wav"
        assert row["recording_duration"] == 60
        assert row["status"] == "recorded"

    def test_recording_saved_redelivery_with_memo_id_is_noop(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase(
            {"outbound_calls": [_recorded_row(memo_id="already")]}
        )
        telnyx = MagicMock()

        with patch(
            "app.api.webhooks.download_telnyx_recording",
            new_callable=AsyncMock,
        ) as download:
            resp = _post(
                _recording_saved(),
                signing=signing,
                pub=pub,
                supabase=supabase,
                telnyx=telnyx,
            )

        assert resp.status_code == 204
        download.assert_not_called()

    def test_recording_saved_unknown_call_is_204(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase({"outbound_calls": []})
        telnyx = MagicMock()

        with patch(
            "app.api.webhooks.download_telnyx_recording",
            new_callable=AsyncMock,
        ) as download:
            resp = _post(
                _recording_saved(),
                signing=signing,
                pub=pub,
                supabase=supabase,
                telnyx=telnyx,
            )

        assert resp.status_code == 204
        download.assert_not_called()

    def test_recording_saved_finds_row_by_pstn_id(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase({"outbound_calls": [_recorded_row()]})
        telnyx = MagicMock()

        with (
            patch(
                "app.api.webhooks.download_telnyx_recording",
                new_callable=AsyncMock,
                return_value=b"RIFF....",
            ) as download,
            patch(
                "app.api.webhooks.StorageService.upload_call_recording",
                new_callable=AsyncMock,
                return_value=f"{USER_ID}/{PARKED_ID}.wav",
            ),
            patch(
                "app.api.webhooks.attach_hubspot_contact_by_phone",
                new_callable=AsyncMock,
                side_effect=lambda _sb, row: row,
            ),
            patch(
                "app.api.webhooks.initiate_vocify_call_memo",
                new_callable=AsyncMock,
                return_value=("memo-1", True),
            ),
            patch(
                "app.api.webhooks.process_vocify_call_background",
                new_callable=AsyncMock,
            ),
            patch(
                "app.api.webhooks.asyncio.create_task",
                side_effect=_close_created_task,
            ),
        ):
            resp = _post(
                _recording_saved(call_control_id=PSTN_ID),
                signing=signing,
                pub=pub,
                supabase=supabase,
                telnyx=telnyx,
            )

        assert resp.status_code == 204
        download.assert_awaited_once_with(RECORDING_ID)

    def test_recording_saved_finds_row_by_client_state(self):
        signing, pub = _keys()
        supabase, _ = _fake_supabase(
            {"outbound_calls": [_recorded_row(carrier_call_id="client-state-1")]}
        )
        telnyx = MagicMock()

        with (
            patch(
                "app.api.webhooks.download_telnyx_recording",
                new_callable=AsyncMock,
                return_value=b"RIFF....",
            ) as download,
            patch(
                "app.api.webhooks.StorageService.upload_call_recording",
                new_callable=AsyncMock,
                return_value=f"{USER_ID}/client-state-1.wav",
            ),
            patch(
                "app.api.webhooks.attach_hubspot_contact_by_phone",
                new_callable=AsyncMock,
                side_effect=lambda _sb, row: row,
            ),
            patch(
                "app.api.webhooks.initiate_vocify_call_memo",
                new_callable=AsyncMock,
                return_value=("memo-1", True),
            ),
            patch(
                "app.api.webhooks.process_vocify_call_background",
                new_callable=AsyncMock,
            ),
            patch(
                "app.api.webhooks.asyncio.create_task",
                side_effect=_close_created_task,
            ),
        ):
            resp = _post(
                _recording_saved(
                    call_control_id="v3:unknown-leg",
                    client_state="client-state-1",
                ),
                signing=signing,
                pub=pub,
                supabase=supabase,
                telnyx=telnyx,
            )

        assert resp.status_code == 204
        download.assert_awaited_once_with(RECORDING_ID)


class TestTelnyxRingWatchdog:
    def test_watchdog_hangs_parked_if_still_dialing_and_not_bridged(self):
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "user_id": USER_ID,
                        "carrier": "telnyx",
                        "carrier_call_id": PARKED_ID,
                        "status": "dialing",
                        "provider_state": {
                            "parked_id": PARKED_ID,
                            "pstn_id": PSTN_ID,
                        },
                    }
                ]
            }
        )
        telnyx = MagicMock()
        with patch("app.api.webhooks.telnyx_rest", return_value=telnyx):
            asyncio.run(
                webhooks._hangup_if_still_ringing(
                    supabase, PARKED_ID, delay_secs=0
                )
            )
        telnyx.hangup.assert_called_once_with(PARKED_ID, cause="TIMEOUT")

    def test_watchdog_skips_bridged_call(self):
        supabase, _ = _fake_supabase(
            {
                "outbound_calls": [
                    {
                        "user_id": USER_ID,
                        "carrier": "telnyx",
                        "carrier_call_id": PARKED_ID,
                        "status": "dialing",
                        "provider_state": {
                            "parked_id": PARKED_ID,
                            "pstn_id": PSTN_ID,
                            "bridged": True,
                        },
                    }
                ]
            }
        )
        telnyx = MagicMock()
        with patch("app.api.webhooks.telnyx_rest", return_value=telnyx):
            asyncio.run(
                webhooks._hangup_if_still_ringing(
                    supabase, PARKED_ID, delay_secs=0
                )
            )
        telnyx.hangup.assert_not_called()
