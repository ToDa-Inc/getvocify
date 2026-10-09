from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_llm_transcript_repair(monkeypatch):
    """The LLM repair of a transcript is a network call: tests of it switch it back on."""
    from app.config import settings

    monkeypatch.setattr(settings, "TRANSCRIPT_SANITIZE_LLM", False)


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
