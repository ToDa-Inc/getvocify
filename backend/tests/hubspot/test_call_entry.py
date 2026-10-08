"""A call placed through Vocify is one HubSpot entry: the Call carries the write-up, no separate Note."""

import asyncio
from contextlib import asynccontextmanager

from app.services.hubspot.call_entry import (
    CALL_BODY_ACTION,
    mark_call_body_written,
    pending_call_body,
    write_to_placed_call,
)


class _Query:
    def __init__(self, table, op, values=None):
        self.table, self.op, self.values, self.filters = table, op, values, []

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append(lambda row: row.get(column) == value)
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, _):
        return self

    def execute(self):
        rows = [row for row in self.table.rows if all(f(row) for f in self.filters)]
        if self.op == "update":
            for row in rows:
                row.update(self.values)
        return type("Result", (), {"data": [dict(row) for row in rows]})()


class _Table:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_):
        return _Query(self, "select")

    def update(self, values):
        return _Query(self, "update", values)


class FakeDb:
    def __init__(self, **tables):
        self.tables = {name: _Table(rows) for name, rows in tables.items()}

    def table(self, name):
        return self.tables[name]


class FakeUpdates:
    """crm_updates.track as sync uses it: the row is written with whatever data the block set."""

    def __init__(self, db):
        self.db = db

    @asynccontextmanager
    async def track(self, *, memo_id, user_id, crm_connection_id, action_type, resource_type):
        class Tracked:
            data = None
            resource_id = None

        tracked = Tracked()
        yield tracked
        self.db.tables["crm_updates"].rows.append(
            {
                "id": f"u{len(self.db.tables['crm_updates'].rows) + 1}",
                "memo_id": memo_id,
                "action_type": action_type,
                "resource_type": resource_type,
                "status": "success",
                "data": tracked.data,
                "resource_id": tracked.resource_id,
            }
        )


class FakeClient:
    def __init__(self, on_patch=None):
        self.patches = []
        self.on_patch = on_patch

    async def patch(self, endpoint, data):
        self.patches.append((endpoint, data))


def db(engagement_id=None, memo_id="memo-1"):
    return FakeDb(
        outbound_calls=[{"carrier_call_id": "CA1", "memo_id": memo_id, "hubspot_engagement_id": engagement_id}],
        crm_updates=[],
    )


def write(fake, client, body="<p>Resumen</p>"):
    return asyncio.run(
        write_to_placed_call(
            supabase=fake,
            client=client,
            crm_updates=FakeUpdates(fake),
            memo_id="memo-1",
            user_id="rep-1",
            connection_id="conn-1",
            body=body,
        )
    )


def test_the_write_up_goes_on_the_logged_call():
    fake, client = db(engagement_id="519000"), FakeClient()
    assert write(fake, client) is True
    assert client.patches == [("/crm/v3/objects/calls/519000", {"properties": {"hs_call_body": "<p>Resumen</p>"}})]
    row = fake.tables["crm_updates"].rows[0]
    assert (row["action_type"], row["resource_type"], row["resource_id"]) == (CALL_BODY_ACTION, "call", "519000")


def test_saved_before_the_call_is_logged_it_waits_for_the_call():
    fake, client = db(engagement_id=None), FakeClient()
    assert write(fake, client) is True
    assert client.patches == []
    assert pending_call_body(fake, "memo-1")[1] == "<p>Resumen</p>"


def test_the_waiting_write_up_is_used_once_the_call_is_logged():
    fake = db(engagement_id=None)
    write(fake, FakeClient())
    update_id, body = pending_call_body(fake, "memo-1")
    mark_call_body_written(fake, update_id, "519000")
    assert pending_call_body(fake, "memo-1") is None
    assert fake.tables["crm_updates"].rows[0]["resource_id"] == "519000"


def test_a_call_logged_while_saving_still_gets_the_write_up():
    fake = db(engagement_id=None)

    class LoggedMeanwhile(FakeUpdates):
        @asynccontextmanager
        async def track(self, **kwargs):
            async with super().track(**kwargs) as tracked:
                yield tracked
            # log_call_engagement ran between reading the call and saving the write-up.
            fake.tables["outbound_calls"].rows[0]["hubspot_engagement_id"] = "519000"

    client = FakeClient()
    asyncio.run(
        write_to_placed_call(
            supabase=fake, client=client, crm_updates=LoggedMeanwhile(fake),
            memo_id="memo-1", user_id="rep-1", connection_id="conn-1", body="<p>Resumen</p>",
        )
    )
    assert [endpoint for endpoint, _ in client.patches] == ["/crm/v3/objects/calls/519000"]
    assert pending_call_body(fake, "memo-1") is None


def test_a_memo_that_is_not_a_placed_call_keeps_its_note():
    fake, client = db(engagement_id="519000", memo_id="other-memo"), FakeClient()
    assert write(fake, client) is False
    assert client.patches == []
    assert fake.tables["crm_updates"].rows == []


def test_a_lost_outcome_merged_into_the_write_up_stays_recorded_once_written():
    fake = db(engagement_id=None)
    asyncio.run(
        write_to_placed_call(
            supabase=fake, client=FakeClient(), crm_updates=FakeUpdates(fake),
            memo_id="memo-1", user_id="rep-1", connection_id="conn-1", body="<p>Perdido</p>",
            extra_data={"outcome_note_merged": True},
        )
    )
    update_id, _ = pending_call_body(fake, "memo-1")
    mark_call_body_written(fake, update_id, "519000")
    assert fake.tables["crm_updates"].rows[0]["data"] == {
        "outcome_note_merged": True, "engagement_id": "519000", "pending": False,
    }
