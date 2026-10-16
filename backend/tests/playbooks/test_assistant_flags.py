"""The playbook assistant ships dark: both flags exist, are off by default and reach the frontend."""

from app.config import settings
from app.services.feature_flags import CLIENT_FLAGS, PLAYBOOK_ASSISTANT_FLAGS


def test_assistant_flags_are_client_flags():
    assert PLAYBOOK_ASSISTANT_FLAGS == ("PLAYBOOK_ASSISTANT_ENABLED", "PLAYBOOK_SUCCESS_RATE_ENABLED")
    for flag in PLAYBOOK_ASSISTANT_FLAGS:
        assert flag in CLIENT_FLAGS


def test_assistant_flags_are_off_by_default():
    assert settings.PLAYBOOK_ASSISTANT_ENABLED is False
    assert settings.PLAYBOOK_SUCCESS_RATE_ENABLED is False
