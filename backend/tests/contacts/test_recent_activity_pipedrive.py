"""The Pipedrive part of recent activity: a person's notes and activities become interactions with ids the summary can cite."""

import asyncio

from app.services.contacts.recent_activity import read_pipedrive_activity


class FakePipedrive:
    def __init__(self, notes, activities, fail=()):
        self.payloads = {"/notes": {"data": notes}, "/activities": {"data": activities}}
        self.fail = fail
        self.calls = []

    async def get(self, path, *, version="v2", params=None):
        self.calls.append((path, version, params))
        if path in self.fail:
            raise RuntimeError("boom")
        return self.payloads[path]


NOTES = [
    {"id": 5, "content": "<p>Wants <b>pricing</b> for 12 seats</p>", "add_time": "2026-11-05 14:03:22", "update_time": "2026-11-05 15:00:00"},
    {"id": 6, "content": "", "add_time": "2026-11-05 14:03:22"},
]
ACTIVITIES = [
    {"id": 9, "type": "call", "subject": "Discovery", "note": "Talked about the pilot", "done": True, "add_time": "2026-11-01T10:00:00Z"},
    {"id": 10, "type": "task", "subject": "Send proposal", "done": False, "add_time": "2026-11-02T10:00:00Z"},
]


def test_notes_and_activities_become_cited_interactions():
    client = FakePipedrive(NOTES, ACTIVITIES)
    items, sources = asyncio.run(read_pipedrive_activity(client, "77"))
    by_id = {i["id"]: i for i in items}
    assert sources == {"notes": "read", "activities": "read"}
    assert by_id["pipedrive:note:5"]["text"] == "Wants pricing for 12 seats"
    assert by_id["pipedrive:note:5"]["occurred_at"] == "2026-11-05T15:00:00Z"
    assert by_id["pipedrive:call:9"]["text"] == "Discovery — Talked about the pilot"
    assert by_id["pipedrive:task:10"]["text"] == "Send proposal — open"
    assert "pipedrive:note:6" not in by_id  # an empty note says nothing
    assert ("/notes", "v1", {"person_id": "77", "sort": "add_time DESC", "limit": 50}) in client.calls


def test_one_kind_failing_never_hides_the_other():
    items, sources = asyncio.run(read_pipedrive_activity(FakePipedrive(NOTES, ACTIVITIES, fail={"/activities"}), "77"))
    assert sources == {"notes": "read", "activities": "failed"}
    assert [i["id"] for i in items] == ["pipedrive:note:5"]
