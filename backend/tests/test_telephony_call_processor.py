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
