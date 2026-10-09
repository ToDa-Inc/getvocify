"""The actor belongs to one request. Scope is decided by the server's role, never by the words asked."""

import asyncio

import pytest

from app.services.crm_copilot.actor import AskActor, ScopeError, bind_actor, current_actor, visible_user_ids


class Members:
    def __init__(self, ids):
        self.ids = ids

    def list_members(self, company_id):
        return [{"user_id": i, "status": "active"} for i in self.ids]


def test_a_member_sees_only_themselves_even_if_they_name_a_teammate():
    actor = AskActor(user_id="u1", company_id="co", role="member")
    assert visible_user_ids(actor, Members(["u1", "u2"])) == ["u1"]
    with pytest.raises(ScopeError):
        visible_user_ids(actor, Members(["u1", "u2"]), requested_user_id="u2")


def test_an_admin_sees_the_company_or_one_member_of_it():
    actor = AskActor(user_id="u1", company_id="co", role="admin")
    assert sorted(visible_user_ids(actor, Members(["u1", "u2"]))) == ["u1", "u2"]
    assert visible_user_ids(actor, Members(["u1", "u2"]), requested_user_id="u2") == ["u2"]
    with pytest.raises(ScopeError):
        visible_user_ids(actor, Members(["u1", "u2"]), requested_user_id="outsider")


def test_a_member_asking_for_themselves_is_fine():
    actor = AskActor(user_id="u1", company_id="co", role="member")
    assert visible_user_ids(actor, Members(["u1"]), requested_user_id="u1") == ["u1"]


@pytest.mark.asyncio
async def test_two_concurrent_requests_keep_their_own_actor():
    seen = {}

    async def request(name, delay):
        bind_actor(AskActor(user_id=name, company_id=f"co-{name}", role="member"))
        await asyncio.sleep(delay)
        seen[name] = current_actor().user_id

    await asyncio.gather(
        asyncio.create_task(request("a", 0.02)),
        asyncio.create_task(request("b", 0.0)),
    )
    assert seen == {"a": "a", "b": "b"}


def test_no_actor_is_an_error_not_a_default_member():
    from app.services.crm_copilot import actor as actor_module

    token = actor_module._current.set(None)
    try:
        with pytest.raises(ScopeError):
            current_actor()
    finally:
        actor_module._current.reset(token)
