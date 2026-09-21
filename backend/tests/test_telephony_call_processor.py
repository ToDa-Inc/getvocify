from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

    def test_rewrites_us1_host_to_ireland_when_region_is_set(self):
        with patch("app.services.telephony.call_processor.settings") as settings:
            settings.TWILIO_EDGE = "dublin"
            settings.TWILIO_REGION = "ie1"
            url = twilio_wav_url(
                "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/RE1"
            )
        assert url.startswith("https://api.dublin.ie1.twilio.com/")
        assert url.endswith(".wav")


class TestDownloadUsesBasicAuth:
    @patch("app.services.telephony.call_processor.httpx.AsyncClient")
    @patch("app.services.telephony.call_processor.settings")
    def test_authenticates_with_api_key_credentials(self, settings, client_cls):
        import asyncio

        from app.services.telephony.call_processor import download_twilio_recording

        settings.TWILIO_API_KEY_SID = "SK1"
        settings.TWILIO_API_KEY_SECRET = "secret"

        instance = client_cls.return_value.__aenter__.return_value
        response = MagicMock()
        response.content = b"RIFF"
        response.raise_for_status.return_value = None
        instance.get = AsyncMock(return_value=response)

        asyncio.run(
            download_twilio_recording(
                "https://api.twilio.com/2010-04-01/Accounts/AC1/Recordings/RE1"
            )
        )

        assert client_cls.call_args.kwargs["auth"] == ("SK1", "secret")


class TestDownloadTelnyxRecording:
    @pytest.mark.asyncio
    async def test_download_telnyx_recording_uses_wav_url(self):
        from app.services.telephony.call_processor import download_telnyx_recording

        wav_url = "https://s3.example.com/rec-1.wav"
        telnyx = MagicMock()
        telnyx.get_recording.return_value = {"download_urls": {"wav": wav_url}}

        instance = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.content = b"RIFF...."
        response.raise_for_status.return_value = None
        instance.get = AsyncMock(return_value=response)

        with (
            patch(
                "app.services.telephony.call_processor.telnyx_rest",
                return_value=telnyx,
            ),
            patch("app.services.telephony.call_processor.httpx.AsyncClient") as client_cls,
            patch("app.services.telephony.call_processor.settings") as settings,
        ):
            settings.TELNYX_API_KEY = "KEY"
            client_cls.return_value.__aenter__.return_value = instance
            audio = await download_telnyx_recording("rec-1")

        assert audio.startswith(b"RIFF")
        telnyx.get_recording.assert_called_once_with("rec-1")
        assert client_cls.call_args.kwargs["headers"]["Authorization"] == "Bearer KEY"
        instance.get.assert_awaited_once_with(wav_url)

    @pytest.mark.asyncio
    async def test_download_telnyx_recording_fails_when_wav_url_missing(self):
        from app.services.telephony.call_processor import download_telnyx_recording

        telnyx = MagicMock()
        telnyx.get_recording.return_value = {
            "download_urls": {"mp3": "https://s3.example.com/rec-1.mp3"}
        }
        instance = MagicMock()
        instance.get = AsyncMock()

        with (
            patch(
                "app.services.telephony.call_processor.telnyx_rest",
                return_value=telnyx,
            ),
            patch("app.services.telephony.call_processor.httpx.AsyncClient") as client_cls,
            patch("app.services.telephony.call_processor.settings") as settings,
        ):
            settings.TELNYX_API_KEY = "KEY"
            client_cls.return_value.__aenter__.return_value = instance
            with pytest.raises(ValueError, match="download_urls.wav"):
                await download_telnyx_recording("rec-1")

        instance.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_download_telnyx_recording_refreshes_expired_url(self):
        from app.services.telephony.call_processor import download_telnyx_recording

        telnyx = MagicMock()
        telnyx.get_recording.side_effect = [
            {"download_urls": {"wav": "https://s3.example.com/old.wav"}},
            {"download_urls": {"wav": "https://s3.example.com/new.wav"}},
        ]
        expired = MagicMock()
        expired.status_code = 403
        expired.content = b""
        refreshed = MagicMock()
        refreshed.status_code = 200
        refreshed.content = b"RIFF...."
        refreshed.raise_for_status.return_value = None
        instance = MagicMock()
        instance.get = AsyncMock(side_effect=[expired, refreshed])

        with (
            patch(
                "app.services.telephony.call_processor.telnyx_rest",
                return_value=telnyx,
            ),
            patch("app.services.telephony.call_processor.httpx.AsyncClient") as client_cls,
            patch("app.services.telephony.call_processor.settings") as settings,
        ):
            settings.TELNYX_API_KEY = "KEY"
            client_cls.return_value.__aenter__.return_value = instance
            audio = await download_telnyx_recording("rec-1")

        assert audio.startswith(b"RIFF")
        assert telnyx.get_recording.call_count == 2
        assert [c.args[0] for c in instance.get.await_args_list] == [
            "https://s3.example.com/old.wav",
            "https://s3.example.com/new.wav",
        ]


class TestAttachHubspotContactByPhone:
    def _row(self, **overrides):
        row = {
            "user_id": "user-1",
            "carrier_call_id": "CA1",
            "to_number": "+34648739267",
            "hubspot_contact_id": None,
        }
        row.update(overrides)
        return row

    def test_unique_phone_hit_is_persisted(self):
        import asyncio
        from types import SimpleNamespace

        from app.services.telephony.call_processor import attach_hubspot_contact_by_phone

        store = [self._row()]
        supabase = MagicMock()
        table = MagicMock()
        supabase.table.return_value = table
        table.update.return_value = table
        table.eq.return_value = table
        table.execute.return_value = SimpleNamespace(data=store)

        hit = MagicMock()
        hit.id = "hs-42"

        with patch(
            "app.api.crm.get_hubspot_client_from_connection", return_value=MagicMock()
        ), patch(
            "app.services.hubspot.search.HubSpotSearchService"
        ) as search_cls:
            search_cls.return_value.find_contacts_by_phone = AsyncMock(return_value=[hit])
            out = asyncio.run(attach_hubspot_contact_by_phone(supabase, store[0]))

        assert out["hubspot_contact_id"] == "hs-42"
        table.update.assert_called_once()
        assert table.update.call_args.args[0]["hubspot_contact_id"] == "hs-42"

    def test_ambiguous_or_empty_hits_leave_contact_unset(self):
        import asyncio

        from app.services.telephony.call_processor import attach_hubspot_contact_by_phone

        row = self._row()
        supabase = MagicMock()
        with patch(
            "app.api.crm.get_hubspot_client_from_connection", return_value=MagicMock()
        ), patch(
            "app.services.hubspot.search.HubSpotSearchService"
        ) as search_cls:
            search_cls.return_value.find_contacts_by_phone = AsyncMock(
                return_value=[MagicMock(id="a"), MagicMock(id="b")]
            )
            out = asyncio.run(attach_hubspot_contact_by_phone(supabase, row))

        assert out["hubspot_contact_id"] is None
        supabase.table.assert_not_called()

    def test_skips_lookup_when_contact_already_set(self):
        import asyncio

        from app.services.telephony.call_processor import attach_hubspot_contact_by_phone

        row = self._row(hubspot_contact_id="already")
        supabase = MagicMock()
        with patch("app.api.crm.get_hubspot_client_from_connection") as get_client:
            out = asyncio.run(attach_hubspot_contact_by_phone(supabase, row))

        assert out["hubspot_contact_id"] == "already"
        get_client.assert_not_called()

    def test_prefers_named_mobile_when_several_contacts_share_the_number(self):
        import asyncio
        from types import SimpleNamespace

        from app.services.telephony.call_processor import attach_hubspot_contact_by_phone

        store = [self._row()]
        supabase = MagicMock()
        table = MagicMock()
        supabase.table.return_value = table
        table.update.return_value = table
        table.eq.return_value = table
        table.execute.return_value = SimpleNamespace(data=store)

        generic = MagicMock(
            id="generic",
            properties={
                "firstname": "Contact",
                "lastname": "at Papernest",
                "phone": "+34648739267",
                "mobilephone": None,
            },
        )
        named = MagicMock(
            id="toni",
            properties={
                "firstname": "Toni",
                "lastname": "Mora",
                "phone": None,
                "mobilephone": "+34648739267",
            },
        )
        with patch(
            "app.api.crm.get_hubspot_client_from_connection", return_value=MagicMock()
        ), patch(
            "app.services.hubspot.search.HubSpotSearchService"
        ) as search_cls:
            search_cls.return_value.find_contacts_by_phone = AsyncMock(
                return_value=[generic, named]
            )
            out = asyncio.run(attach_hubspot_contact_by_phone(supabase, store[0]))

        assert out["hubspot_contact_id"] == "toni"


class TestLogCallEngagement:
    def test_keeps_the_call_logged_when_recording_ready_fails(self):
        import asyncio
        from types import SimpleNamespace

        from app.services.telephony.call_processor import log_call_engagement

        row = {
            "user_id": "u1",
            "to_number": "+34600000000",
            "from_number": "+34900000000",
            "hubspot_contact_id": "755",
            "hubspot_deal_id": None,
            "hubspot_engagement_id": None,
        }
        supabase = MagicMock()
        table = MagicMock()
        supabase.table.return_value = table
        table.select.return_value = table
        table.update.return_value = table
        table.eq.return_value = table
        table.limit.return_value = table
        table.execute.return_value = SimpleNamespace(data=[row])

        updates = []

        def capture_update(payload):
            updates.append(payload)
            return table

        table.update.side_effect = capture_update

        with patch(
            "app.services.telephony.call_processor._company_hubspot_connection",
            return_value={"metadata": {"portal_id": "147506535"}},
        ), patch(
            "app.api.crm.get_hubspot_client_from_connection", return_value=MagicMock()
        ), patch(
            "app.services.telephony.call_processor._hubspot_owner_id_for_caller",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.services.telephony.call_processor.settings"
        ) as settings, patch(
            "app.services.hubspot.call_log.log_call_to_hubspot",
            new=AsyncMock(return_value="519000"),
        ), patch(
            "app.services.hubspot.call_log.mark_recording_ready",
            new=AsyncMock(side_effect=RuntimeError("Unable to access recording")),
        ):
            settings.HUBSPOT_APP_ID = "app-1"
            asyncio.run(log_call_engagement(supabase, "CAxxx", 12.0))

        assert any(
            u.get("hubspot_engagement_id") == "519000" and u.get("status") == "logged"
            for u in updates
        )

    def test_links_hubspot_engagement_to_vocify_memo(self):
        import asyncio
        from types import SimpleNamespace

        from app.services.telephony.call_processor import log_call_engagement

        row = {
            "user_id": "u1",
            "memo_id": "memo-1",
            "to_number": "+34600000000",
            "from_number": "+34900000000",
            "hubspot_contact_id": "755",
            "hubspot_deal_id": None,
            "hubspot_engagement_id": None,
        }
        supabase = MagicMock()
        table = MagicMock()
        supabase.table.return_value = table
        table.select.return_value = table
        table.update.return_value = table
        table.eq.return_value = table
        table.is_.return_value = table
        table.limit.return_value = table
        table.execute.return_value = SimpleNamespace(data=[row])

        updates = []

        def capture_update(payload):
            updates.append(payload)
            return table

        table.update.side_effect = capture_update

        with patch(
            "app.services.telephony.call_processor._company_hubspot_connection",
            return_value={"metadata": {"portal_id": "147506535"}},
        ), patch(
            "app.api.crm.get_hubspot_client_from_connection", return_value=MagicMock()
        ), patch(
            "app.services.telephony.call_processor._hubspot_owner_id_for_caller",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.services.telephony.call_processor.settings"
        ) as settings, patch(
            "app.services.hubspot.call_log.log_call_to_hubspot",
            new=AsyncMock(return_value="519000"),
        ), patch(
            "app.services.hubspot.call_log.mark_recording_ready",
            new=AsyncMock(return_value=None),
        ):
            settings.HUBSPOT_APP_ID = "app-1"
            asyncio.run(log_call_engagement(supabase, "CAxxx", 12.0))

        assert any(u.get("hubspot_engagement_id") == "519000" for u in updates)

    def test_resolves_and_caches_missing_portal_id(self):
        import asyncio
        from types import SimpleNamespace
        from app.services.hubspot.account_info import HubSpotAccountContext
        from app.services.telephony.call_processor import log_call_engagement

        row = {
            "user_id": "u1",
            "to_number": "+34600000000",
            "from_number": "+34900000000",
            "hubspot_contact_id": "755",
            "hubspot_deal_id": None,
            "hubspot_engagement_id": None,
        }
        supabase = MagicMock()
        table = MagicMock()
        supabase.table.return_value = table
        table.select.return_value = table
        table.update.return_value = table
        table.eq.return_value = table
        table.limit.return_value = table
        table.execute.return_value = SimpleNamespace(data=[row])

        updates = []
        table.update.side_effect = lambda payload: updates.append(payload) or table

        conn_row = {"id": "conn-1", "metadata": {}}

        with patch(
            "app.services.telephony.call_processor._company_hubspot_connection",
            return_value=conn_row,
        ), patch(
            "app.api.crm.get_hubspot_client_from_connection", return_value=MagicMock()
        ), patch(
            "app.services.hubspot.account_info.resolve_account_context",
            new=AsyncMock(return_value=HubSpotAccountContext(portal_id="999888", region="eu1")),
        ), patch(
            "app.services.telephony.call_processor._hubspot_owner_id_for_caller",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.services.telephony.call_processor.settings"
        ) as settings, patch(
            "app.services.hubspot.call_log.log_call_to_hubspot",
            new=AsyncMock(return_value="519001"),
        ), patch(
            "app.services.hubspot.call_log.mark_recording_ready",
            new=AsyncMock(return_value=None),
        ):
            settings.HUBSPOT_APP_ID = "app-1"
            asyncio.run(log_call_engagement(supabase, "CAxxx", 10.0))

        # Must have updated outbound_calls with resolved portal_id and logged engagement
        assert any(u.get("hubspot_hub_id") == "999888" for u in updates)
        assert any(u.get("hubspot_engagement_id") == "519001" for u in updates)
        # Must have persisted updated metadata to crm_connections
        assert any(u.get("metadata", {}).get("portal_id") == "999888" for u in updates)


class TestMissedCallLogging:
    def test_resolves_and_caches_missing_portal_id_on_missed_call(self):
        import asyncio
        from types import SimpleNamespace
        from app.services.hubspot.account_info import HubSpotAccountContext
        from app.services.telephony.call_processor import log_missed_call_activity

        row = {
            "user_id": "u1",
            "carrier_call_id": "CA-no-answer",
            "to_number": "+34686985664",
            "from_number": "+34648739267",
            "hubspot_contact_id": "864833756353",
            "hubspot_deal_id": None,
            "hubspot_engagement_id": None,
            "memo_id": None,
            "status": "dialing",
        }
        supabase = MagicMock()
        table = MagicMock()
        supabase.table.return_value = table
        table.select.return_value = table
        table.update.return_value = table
        table.eq.return_value = table
        table.limit.return_value = table
        table.execute.return_value = SimpleNamespace(data=[row])

        updates = []
        table.update.side_effect = lambda payload: updates.append(payload) or table

        conn_row = {"id": "conn-1", "metadata": {}}

        with patch(
            "app.services.telephony.call_processor._company_hubspot_connection",
            return_value=conn_row,
        ), patch(
            "app.api.crm.get_hubspot_client_from_connection", return_value=MagicMock()
        ), patch(
            "app.services.hubspot.account_info.resolve_account_context",
            new=AsyncMock(return_value=HubSpotAccountContext(portal_id="147506535", region="eu1")),
        ), patch(
            "app.services.telephony.call_processor._hubspot_owner_id_for_caller",
            new=AsyncMock(return_value=None),
        ), patch(
            "app.services.telephony.call_processor.settings"
        ) as settings, patch(
            "app.services.hubspot.call_log.log_call_to_hubspot",
            new=AsyncMock(return_value="520001"),
        ):
            settings.HUBSPOT_APP_ID = "app-1"
            asyncio.run(log_missed_call_activity(supabase, "CA-no-answer", "no-answer"))

        assert any(u.get("hubspot_hub_id") == "147506535" for u in updates)
        assert any(u.get("hubspot_engagement_id") == "520001" for u in updates)
        assert any(u.get("metadata", {}).get("portal_id") == "147506535" for u in updates)

