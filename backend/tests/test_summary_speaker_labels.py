"""Notes never say S1 / S2: they name the rep and the contact (the model sometimes copies the transcript's marks)."""

from app.services.transcript_turns import without_speaker_labels

TRANSCRIPT = "SPEAKER: S1\nHola, ¿qué tal?\n\nSPEAKER: S2\nBien, gracias.\n"


def test_s2_is_the_contact_by_name_and_s1_the_rep():
    out = without_speaker_labels("- S2 pide un follow-up. S1 queda en llamarle.", TRANSCRIPT, "Marta Ruiz", True)
    assert out == "- Marta Ruiz pide un follow-up. El comercial queda en llamarle."


def test_spanish_articles_still_read_right():
    out = without_speaker_labels("Interesado en lo que hace el equipo de S1.", TRANSCRIPT, None, True)
    assert out == "Interesado en lo que hace el equipo del comercial."


def test_no_name_known_says_the_contact():
    assert without_speaker_labels("The S2 asked for pricing.", TRANSCRIPT.replace("Hola, ¿qué tal?", "Hi"), None, False) == "The contact asked for pricing."


def test_text_is_left_alone_when_the_transcript_has_no_marks():
    assert without_speaker_labels("Samsung S2 tablet", "Hola, ¿qué tal?", "Marta", True) == "Samsung S2 tablet"


def test_a_label_in_brackets_beside_a_name_is_dropped():
    out = without_speaker_labels("- Participan Jaime Moro (S2) y el equipo comercial (S1, Dani).", TRANSCRIPT, "Jaime Moro", True)
    assert out == "- Participan Jaime Moro y el equipo comercial (Dani)."
