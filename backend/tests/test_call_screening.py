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

    def test_two_speakers_but_secondary_too_brief_is_connected_after_30s(self):
        """Twilio already marks no-answer. A 40s two-party call must be extracted
        even when diarization gives the other side almost no words."""
        transcript = (
            "S1: Hola, le llamo de Vocify para comentarle nuestra solución "
            "de transcripción comercial y cómo podemos ayudarle con HubSpot.\n"
            "S2: No.\n"
            "S1: Entiendo, gracias."
        )
        assert classify_call_outcome(transcript, duration=40.0) == "connected"

    def test_imbalanced_diarization_on_long_call_is_connected(self):
        """15 Sep 2026 demo: 102s, S1=12 words / S2=190 words, two people talking.
        The 10% secondary-word ratio used to emit no_response."""
        s1 = "SPEAKER: S1\nVale. ¿Sí? Hola, ¿hablo con Tony? ¿Con Tony? Sí, hola.\n\n"
        s2 = "SPEAKER: S2\n" + ("Escuchas la llamada de Marcos. " * 32)
        assert classify_call_outcome(s1 + s2, duration=102.0) == "connected"

    def test_empty_transcript_stays_no_response_even_after_30s(self):
        assert classify_call_outcome("", duration=102.0) == "no_response"

    def test_long_single_speaker_without_voicemail_is_connected(self):
        transcript = (
            "SPEAKER: S1\n"
            "Hola Toni te llamo de Vocify para enseñarte cómo registramos "
            "las llamadas y actualizamos HubSpot al colgar. "
            "Hoy vemos la extensión, el dialer y los campos del deal."
        )
        assert classify_call_outcome(transcript, duration=90.0) == "connected"

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

    def test_collapsed_s1_conversation_is_connected(self):
        """Deepgram labeled only S1; the text is still a two-way discovery call."""
        transcript = (
            "SPEAKER: S1\n"
            "¿Hola?\n"
            "Hola, buenas tardes. Disculpe que le estoy molestando.\n"
            "¿Usted ahora mismo está con Zoho?\n"
            "Sí.\n"
            "¿Qué tipo de venta está realizando usted?\n"
            "B2B, outbound calls de oficina.\n"
            "Vale, ok, un equipo de SDRs, ¿no?\n"
            "Sí, SDRs y BDRs.\n"
            "¿Y usted es el vicepresidente de ventas?\n"
            "Sí, claro.\n"
            "De acuerdo, en dos semanas hablamos. Chao."
        )
        assert classify_call_outcome(transcript, duration=63.0) == "connected"
