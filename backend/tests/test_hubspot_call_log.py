from app.services.hubspot.call_log import (
    hubspot_call_body_for_disposition,
    hubspot_call_status_for_disposition,
    normalize_twilio_dial_status,
)


class TestCallLogDisposition:
    def test_normalize_twilio_dial_status(self):
        assert normalize_twilio_dial_status("no-answer") == "no_answer"
        assert normalize_twilio_dial_status("busy") == "busy"
        assert normalize_twilio_dial_status("completed") == "connected"

    def test_hubspot_status_mapping(self):
        assert hubspot_call_status_for_disposition("busy") == "BUSY"
        assert hubspot_call_status_for_disposition("connected") == "COMPLETED"
        assert hubspot_call_status_for_disposition("voicemail") == "COMPLETED"

    def test_hubspot_body_mapping(self):
        assert "Buzon de voz" in hubspot_call_body_for_disposition("voicemail")
        assert hubspot_call_body_for_disposition("no_answer") == "Sin respuesta."
