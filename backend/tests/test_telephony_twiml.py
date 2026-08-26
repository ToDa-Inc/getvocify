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

    def test_strips_national_trunk_prefix(self):
        assert normalize_e164("0600111222") == "+34600111222"

    def test_rejects_country_code_without_plus_or_double_zero(self):
        with pytest.raises(InvalidPhoneNumber):
            normalize_e164("34600111222")

    def test_accepts_nine_digit_national_starting_with_country_code_digits(self):
        # 9-digit national numbers whose first two digits happen to be "34"
        # leave only 7 digits after a hypothetical country-code split — accepted.
        assert normalize_e164("341234567") == "+34341234567"

    def test_rejects_portugal_country_code_without_plus_or_double_zero(self):
        with pytest.raises(InvalidPhoneNumber):
            normalize_e164("351600111222", "351")

    def test_accepts_portuguese_national_starting_with_country_code_digits(self):
        # 9-digit national starting with "351" leaves 6 digits after split — accepted.
        assert normalize_e164("351234567", "351") == "+351351234567"

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
