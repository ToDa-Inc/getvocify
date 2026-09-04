import pytest

from app.services.telephony.call_screening import classify_call_outcome


class TestClassifyCallOutcome:
    def test_single_speaker_is_voicemail(self):
        transcript = (
            "S1: Hola, no puedo atender ahora mismo. "
            "Deja tu mensaje después del tono.\n"
            "S1: Gracias."
        )
        assert classify_call_outcome(transcript, duration=45.0) == "voicemail"

    def test_short_two_speaker_call_is_no_response(self):
        transcript = (
            "S1: Hola, buenos días.\n"
            "S2: Diga.\n"
            "S1: Llamo de Vocify.\n"
            "S2: Ahora no puedo."
        )
        assert classify_call_outcome(transcript, duration=20.0) == "no_response"

    def test_two_speakers_but_secondary_too_brief_is_no_response(self):
        transcript = (
            "S1: Hola, le llamo de Vocify para comentarle nuestra solución "
            "de transcripción comercial y cómo podemos ayudarle con HubSpot.\n"
            "S2: No.\n"
            "S1: Entiendo, gracias."
        )
        assert classify_call_outcome(transcript, duration=40.0) == "no_response"

    def test_real_conversation_is_connected(self):
        transcript = (
            "S1: Hola Toni, te llamo de Vocify.\n"
            "S2: Hola, cuéntame.\n"
            "S1: Quería saber si tenéis proceso para registrar llamadas.\n"
            "S2: Sí, ahora usamos notas manuales en HubSpot.\n"
            "S1: Perfecto, podemos automatizar eso.\n"
            "S2: Me interesa, mándame info."
        )
        assert classify_call_outcome(transcript, duration=55.0) == "connected"

    def test_empty_transcript_is_no_response(self):
        assert classify_call_outcome("", duration=10.0) == "no_response"

    def test_undiarized_monologue_is_voicemail(self):
        transcript = "Deje su mensaje después del tono y le devolveremos la llamada."
        assert classify_call_outcome(transcript, duration=35.0) == "voicemail"

    def test_production_speaker_block_format_is_connected(self):
        """sanitize_user_transcript serializes turns as 'SPEAKER: S1\\ntext'
        blocks (see transcript_turns.serialize_transcript_turns), not the
        's1: text' inline shorthand used in the other fixtures above. This
        locks in that the real pipeline output classifies correctly.
        """
        transcript = (
            "SPEAKER: S1\n"
            "Hola Toni, te llamo de Vocify.\n\n"
            "SPEAKER: S2\n"
            "Hola, cuéntame.\n\n"
            "SPEAKER: S1\n"
            "Quería saber si tenéis proceso para registrar llamadas.\n\n"
            "SPEAKER: S2\n"
            "Sí, ahora usamos notas manuales en HubSpot, me interesa que me mandes info."
        )
        assert classify_call_outcome(transcript, duration=55.0) == "connected"

    def test_production_speaker_block_single_speaker_is_voicemail(self):
        transcript = (
            "SPEAKER: S1\n"
            "Hola, no puedo atender ahora mismo. Deja tu mensaje después del tono."
        )
        assert classify_call_outcome(transcript, duration=45.0) == "voicemail"
