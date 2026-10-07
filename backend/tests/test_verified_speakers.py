from app.services.transcript_sanitize import (
    keep_verified_speakers,
    prepare_transcript_for_extraction,
    speakers_are_verified,
)

# In a desktop meeting S1 is the mic (the rep) and S2/S3 are the meeting audio.
# Here the prospect introduces themselves as founder, which the phone-call
# heuristic reads as the rep's pitch and would swap.
MEETING = (
    "SPEAKER: S1\nBuenas, ¿qué tal?\n\n"
    "SPEAKER: S2\nSoy Toni, fundador de Motor de Ventas, te llamo luego.\n\n"
    "SPEAKER: S3\nYo me encargo de HubSpot.\n\n"
    "SPEAKER: S1\nPerfecto, os paso la demo."
)


def _speakers(text: str) -> list[str]:
    return [line.split(": ")[1] for line in text.splitlines() if line.startswith("SPEAKER: ")]


def test_verified_meeting_keeps_rep_and_every_other_speaker():
    text, _ = prepare_transcript_for_extraction(MEETING, speakers_verified=True, spoken_language="es")
    assert _speakers(text) == ["S1", "S2", "S3", "S1"]


def test_unverified_heuristic_still_runs_for_other_sources():
    text, _ = prepare_transcript_for_extraction(MEETING, spoken_language="es")
    assert _speakers(text) != ["S1", "S2", "S3", "S1"]


def test_later_pass_may_fix_words_but_not_speakers():
    before = "SPEAKER: S1\nhola\n\nSPEAKER: S2\nkedamos el martes"
    after = "SPEAKER: S2\nHola.\n\nSPEAKER: S1\nQuedamos el martes."
    assert keep_verified_speakers(before, after) == "SPEAKER: S1\nHola.\n\nSPEAKER: S2\nQuedamos el martes."


def test_restructured_pass_is_rejected():
    before = "SPEAKER: S1\nhola\n\nSPEAKER: S2\nbien"
    assert keep_verified_speakers(before, "SPEAKER: S1\nhola bien") == before


def test_only_channel_capture_counts_as_verified():
    assert speakers_are_verified({"speakers": "channels"})
    assert not speakers_are_verified({"provider": "upload"})
    assert not speakers_are_verified(None)


def test_rep_notes_reach_the_prompt_only_when_written():
    from app.services.extraction import build_extraction_prompt

    with_notes = build_extraction_prompt("SPEAKER: S1\nhola", source_context="meeting_transcript", user_notes="Decide Jorge")
    assert "REP'S OWN NOTES" in with_notes and "Decide Jorge" in with_notes
    assert "REP'S OWN NOTES" not in build_extraction_prompt("SPEAKER: S1\nhola", user_notes="  ")


def test_two_channel_calls_get_their_words_repaired_and_keep_their_speakers(monkeypatch):
    import asyncio

    from app.services import transcript_patch as tp
    from app.services import transcript_sanitize as ts

    async def fix(text, *_a, **_k):
        return tp.PatchResult(text=text.replace("la demo", "la demostración"), edits=[("la demo", "la demostración")])

    monkeypatch.setattr("app.services.transcript_patch.patch_transcript", fix)
    text, _ = asyncio.run(ts.prepare_transcript_for_extraction_async(MEETING, speakers_verified=True, spoken_language="es"))
    assert "la demostración" in text
    assert _speakers(text) == ["S1", "S2", "S3", "S1"]
