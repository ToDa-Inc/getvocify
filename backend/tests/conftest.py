from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_ledger_writes():
    """backend/.env can point at a real Supabase; a test must never write cost rows to it."""
    with patch("app.services.usage.ledger._insert"):
        yield
