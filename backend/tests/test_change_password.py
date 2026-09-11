import pytest
from pydantic import ValidationError

from app.api.auth import ChangePasswordRequest


def test_change_password_requires_eight_char_new_password():
    with pytest.raises(ValidationError):
        ChangePasswordRequest(current_password="old-pass", new_password="short")


def test_change_password_accepts_valid_pair():
    body = ChangePasswordRequest(current_password="old-pass", new_password="new-pass1")
    assert body.new_password == "new-pass1"
