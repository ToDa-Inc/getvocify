from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_llm_transcript_repair(monkeypatch):
    """The LLM repair of a transcript is a network call: tests of it switch it back on."""
    from app.config import settings

    monkeypatch.setattr(settings, "TRANSCRIPT_SANITIZE_LLM", False)


READING_FLAGS = (
    "INTELLIGENCE_EXTRACT_ENABLED", "PLAYBOOK_OBSERVATIONS_ENABLED", "PLAYBOOK_QUALIFICATION_ENABLED",
    "INTELLIGENCE_CALL_READING_ENABLED", "COACHING_READING_ENABLED", "CALL_FINDINGS_ENABLED",
)


@pytest.fixture(autouse=True)
def _after_call_reading_off(monkeypatch):
    """The after-call reading is on for every company in production (tests/test_reading_defaults.py). A test starts with
    it off, as a company switched off by its own row, and switches on what it describes."""
    from app.config import settings

    for flag in READING_FLAGS:
        monkeypatch.setattr(settings, flag, False)


@pytest.fixture(autouse=True)
def _no_cost_writes():
    """backend/.env can point at a real Supabase; a test must never write memo costs to it."""
    with patch("app.services.usage.ledger._write"):
        yield


@pytest.fixture(autouse=True)
def _no_live_sessions_left_behind():
    """Which reps are live is process-wide: one test's session must not make another's recording wait."""
    from app.services import live_activity

    live_activity._open.clear()
    live_activity._ended_at.clear()
    yield
    live_activity._open.clear()
    live_activity._ended_at.clear()


@pytest.fixture(autouse=True)
def _fresh_auth_email_cache():
    """Emails are cached by user id for minutes: one test's user must not answer for another's."""
    from app.services.company import _AUTH_EMAILS

    _AUTH_EMAILS.clear()
    yield
    _AUTH_EMAILS.clear()


@pytest.fixture(autouse=True)
def _fresh_preview_cache():
    """Previews are cached per memo state for a minute: one test's must not answer for another's."""
    from app.api import memos

    memos._PREVIEW_CACHE.clear()
    yield
    memos._PREVIEW_CACHE.clear()


@pytest.fixture(autouse=True)
def _no_live_help_context_left_behind():
    """Live help keeps what it reads for a short time, process-wide: one test's offer, knowledge or playbook must
    not be what the next test's card finds."""
    from app.services.copilot import live_context, playbook_objections

    live_context.clear()
    playbook_objections._cache.clear()
    playbook_objections._company.clear()
    yield
    live_context.clear()
    playbook_objections._cache.clear()
    playbook_objections._company.clear()
