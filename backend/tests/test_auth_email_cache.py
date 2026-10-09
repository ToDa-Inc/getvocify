"""A memo page lists the same few members on every request: their emails come from the auth
service once, not once per request."""

from types import SimpleNamespace

from app.services.company import CompanyService


class _Auth:
    def __init__(self, emails, fail=()):
        self.emails, self.fail, self.calls = emails, set(fail), []

    @property
    def admin(self):
        return self

    def get_user_by_id(self, uid):
        self.calls.append(uid)
        if uid in self.fail:
            raise RuntimeError("auth is down")
        return SimpleNamespace(user=SimpleNamespace(email=self.emails[uid]))


def _service(auth):
    return CompanyService(SimpleNamespace(auth=auth))


def test_an_email_already_read_is_not_asked_for_again():
    auth = _Auth({"u1": "a@x.com", "u2": "b@x.com"})
    service = _service(auth)
    assert service._auth_emails_by_ids(["u1", "u2"]) == {"u1": "a@x.com", "u2": "b@x.com"}
    assert service._auth_emails_by_ids(["u2", "u1"]) == {"u1": "a@x.com", "u2": "b@x.com"}
    assert auth.calls == ["u1", "u2"]


def test_a_failed_lookup_is_retried_next_time_not_remembered():
    auth = _Auth({"u1": "a@x.com"}, fail=["u1"])
    service = _service(auth)
    assert service._auth_emails_by_ids(["u1"]) == {}
    auth.fail.clear()
    assert service._auth_emails_by_ids(["u1"]) == {"u1": "a@x.com"}
    assert auth.calls == ["u1", "u1"]
