from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_cost_writes():
    """backend/.env can point at a real Supabase; a test must never write memo costs to it."""
    with patch("app.services.usage.ledger._write"):
        yield
