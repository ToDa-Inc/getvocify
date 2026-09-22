"""F11 brief: a voicemail is skipped, and a missing score does not invent advice."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-briefs-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-briefs-32b+")

from app.services.coaching.briefs import absent_brief, aggregate_brief

PATTERNS = [{
    "input_revision": "rev-4",
    "superseded": False,
    "evidence_refs": ["ev-1", "ev-2", "ev-3", "ev-4"],
}]


def test_a_missing_row_is_not_a_running_job_or_a_missing_playbook():
    brief = absent_brief()
    assert brief["status"] == "pending"
    assert brief["reason"] == "not_started"
    assert brief["waiting"] is False
    assert brief["strength"] is None
    assert brief["sections"] == []
    for screening in ("voicemail", "no_response"):
        brief = aggregate_brief(
            screening=screening,
            score=None,
            patterns=PATTERNS,
            playbook_present=True,
            job_error=False,
            input_revision="rev-4",
            audio_available=False,
        )
        assert brief["status"] == "skipped"
        assert brief["waiting"] is False
        assert brief["sections"] == []


def test_ready_objections_without_a_score_stay_partial():
    brief = aggregate_brief(
        screening=None,
        score=None,
        patterns=PATTERNS,
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=False,
    )
    assert brief["status"] == "partial"
    assert brief["reason"] == "score_pending"
    assert brief["sections"] == [{"kind": "objections", "evidence_refs": ["ev-1", "ev-2", "ev-3"]}]
    assert brief["strength"] is None
    assert brief["audio_available"] is False


def test_missing_playbook_is_unavailable_and_a_job_error_is_failed():
    missing = aggregate_brief(
        screening=None,
        score={"input_revision": "rev-4", "status": "ready", "value": 8, "strengths": ["Sigue así"]},
        patterns=PATTERNS,
        playbook_present=False,
        job_error=False,
        input_revision="rev-4",
        audio_available=True,
    )
    assert missing["status"] == "unavailable"
    assert missing["reason"] == "missing_playbook"
    assert missing["strength"] is None
    failed = aggregate_brief(
        screening=None,
        score={"status": "pending", "input_revision": "rev-4"},
        patterns=[],
        playbook_present=True,
        job_error=True,
        input_revision="rev-4",
        audio_available=False,
    )
    assert failed["status"] == "failed"
    assert failed["waiting"] is False


def test_an_old_score_is_not_mixed_with_the_current_revision():
    brief = aggregate_brief(
        screening=None,
        score={
            "input_revision": "rev-3",
            "status": "ready",
            "value": 9,
            "strengths": ["Cerró el siguiente paso"],
            "improvements": ["Preguntó tarde"],
        },
        patterns=PATTERNS,
        playbook_present=True,
        job_error=False,
        input_revision="rev-4",
        audio_available=True,
    )
    assert brief["status"] == "partial"
    assert brief["strength"] is None
    assert brief["improvement"] is None
    assert brief["sections"][0]["evidence_refs"] == ["ev-1", "ev-2", "ev-3"]
