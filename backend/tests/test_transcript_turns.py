from app.services.transcript_turns import (
    first_name,
    normalize_diarized_transcript,
    parse_transcript_turns,
    prospect_name_from_existing,
    speaker_display_label,
    speaker_prompt_legend,
)

DISPLAY = """Speaker 1
Hola, ángel. Soy Toni, fundador de Vox HIFI.

Speaker 2
Toni. Qué más me has dicho?

Speaker 1
He visto que estás como director de ventas en Drive Solutions."""

RAW = """SPEAKER: S1
Hola, ángel. Soy Toni, fundador de Vox HIFI.

SPEAKER: S2
Toni. Qué más me has dicho?

SPEAKER: S1
He visto que estás como director de ventas en Drive Solutions."""


def test_parses_speaker_1_and_speaker_s1():
    assert len(parse_transcript_turns(DISPLAY)) == 3
    assert len(parse_transcript_turns(RAW)) == 3


def test_drops_duplicated_display_and_raw_copy():
    doubled = f"{DISPLAY}\n\n{RAW}"
    normalized = normalize_diarized_transcript(doubled)
    turns = parse_transcript_turns(normalized)
    assert len(turns) == 3
    assert turns[0]["speaker"] == "S1"
    assert "SPEAKER: S1" in normalized
    assert normalized.count("Hola, ángel") == 1


def test_labels_s1_as_you_and_s2_as_contact_first_name():
    assert speaker_display_label("S1", {"s1": "You", "s2": "Ángel"}) == "You"
    assert speaker_display_label("Speaker 2", {"s1": "You", "s2": "Ángel"}) == "Ángel"
    assert first_name("Ángel Ruiz") == "Ángel"


def test_maps_named_stt_speakers_to_contact_label():
    named = "SPEAKER: JUAN\nSí. Buenas. ¿Qué tal?"
    turns = parse_transcript_turns(named)
    assert turns[0]["speaker"] == "JUAN"
    assert speaker_display_label("JUAN", {"s1": "You", "s2": "Francisco"}) == "Francisco"


def test_speaker_prompt_legend_uses_crm_contact_name():
    legend = speaker_prompt_legend(
        RAW,
        prospect_name_from_existing({"contacts": {"firstname": "María", "lastname": "Ruiz"}}),
    )
    assert "S1" in legend
    assert "María Ruiz" in legend
    assert speaker_prompt_legend("no speakers here at all") == ""
