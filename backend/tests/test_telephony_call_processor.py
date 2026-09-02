from unittest.mock import AsyncMock, MagicMock, patch

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


class TestAttachHubspotContactByPhone:
    def _row(self, **overrides):
        row = {
            "user_id": "user-1",
            "twilio_call_sid": "CA1",
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
