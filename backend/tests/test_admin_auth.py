from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.deps import verify_master_key


def test_unset_master_key_is_unavailable():
    with patch("app.deps.settings") as settings:
        settings.MASTER_KEY = None
        with pytest.raises(HTTPException) as exc:
            verify_master_key("anything")
        assert exc.value.status_code == 503


def test_blank_master_key_is_unavailable():
    with patch("app.deps.settings") as settings:
        settings.MASTER_KEY = "   "
        with pytest.raises(HTTPException) as exc:
            verify_master_key("   ")
        assert exc.value.status_code == 503


def test_wrong_key_is_unauthorized():
    with patch("app.deps.settings") as settings:
        settings.MASTER_KEY = "correct-key-value"
        with pytest.raises(HTTPException) as exc:
            verify_master_key("wrong")
        assert exc.value.status_code == 401


def test_missing_header_is_unauthorized():
    with patch("app.deps.settings") as settings:
        settings.MASTER_KEY = "correct-key-value"
        with pytest.raises(HTTPException) as exc:
            verify_master_key(None)
        assert exc.value.status_code == 401


def test_matching_key_returns_the_key():
    with patch("app.deps.settings") as settings:
        settings.MASTER_KEY = "correct-key-value"
        assert verify_master_key("correct-key-value") == "correct-key-value"
