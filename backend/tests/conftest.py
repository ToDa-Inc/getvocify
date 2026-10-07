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
