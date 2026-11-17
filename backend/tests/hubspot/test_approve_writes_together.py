"""Approving a call writes HubSpot steps that do not depend on each other at the same time.

On 2026-11-17 an island approval (memo b6ec835c) took 2.25 s, ~1.5 s of it HubSpot calls strictly in turn:
contact read and update, the contact's company, the contact's tasks, the task, the note. The note lists the
fields written on the contact, so it still waits for the contact; the company lookup and the tasks do not.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.models.memo import MemoExtraction
from app.services.commitment_tasks import CommitmentTask
from app.services.hubspot.associations import HubSpotAssociationService
from app.services.hubspot.contacts import HubSpotContactService
from app.services.hubspot.sync import HubSpotSyncService
from app.services.hubspot.tasks import HubSpotTasksService

MADRID = ZoneInfo("Europe/Madrid")
CALL_BACK = CommitmentTask("com-1", "call", "Llamar a Elsa el jueves", datetime(2026, 11, 19, 10, 0, tzinfo=MADRID))


class Clock:
    def __init__(self):
        self.spans: dict[str, list[float]] = {}

    @asynccontextmanager
    async def span(self, name):
        loop = asyncio.get_running_loop()
        start = loop.time()
        await asyncio.sleep(0.05)
        yield
        self.spans[name] = [start, loop.time()]

    def overlap(self, a, b):
        (a0, a1), (b0, b1) = self.spans[a], self.spans[b]
        return a0 < b1 and b0 < a1


class Contact:
    def __init__(self, properties):
        self.properties = properties


class Contacts(HubSpotContactService):
    def __init__(self, clock):
        super().__init__(client=None, search=None)
        self.clock, self.updated = clock, []

    async def get(self, contact_id, properties=None):
        async with self.clock.span("contact_read"):
            return Contact({"firstname": "Elsa", "jobtitle": ""})

    async def update(self, contact_id, props):
        async with self.clock.span("contact_update"):
            self.updated.append(dict(props))


class Associations(HubSpotAssociationService):
    def __init__(self, clock):
        super().__init__(client=None)
        self.clock = clock

    async def get_associations(self, from_type, object_id, to_type, *a, **k):
        if (from_type, to_type) == ("contacts", "companies"):
            async with self.clock.span("company_lookup"):
                return ["CO1"]
        return []


class Tasks(HubSpotTasksService):
    def __init__(self, clock):
        super().__init__(client=None)
        self.clock, self.created = clock, []

    async def list_tasks_for_contact(self, contact_id, properties=None):
        return []

    async def list_tasks_for_deal(self, deal_id, properties=None):
        return []

    async def create_task(self, subject, due_date, deal_id=None, contact_id=None, company_id=None,
                          body=None, priority="MEDIUM", task_type="TODO", hubspot_owner_id=None):
        async with self.clock.span("task"):
            self.created.append({"subject": subject, "contact_id": contact_id, "company_id": company_id})
            return f"T-{len(self.created)}"


class Client:
    def __init__(self, clock, note_fails=False):
        self.clock, self.note_fails, self.notes = clock, note_fails, []

    async def get(self, path, params=None):
        return {"results": []}

    async def post(self, path, data=None):
        if path == "/crm/v3/objects/notes":
            async with self.clock.span("note"):
                if self.note_fails:
                    raise RuntimeError("HubSpot refused the note")
                self.notes.append(data)
                return {"id": "N-1"}
        return {}


class Tracked:
    data = None
    resource_id = None
    response = None


class Updates:
    def __init__(self):
        self.actions = []

    @asynccontextmanager
    async def track(self, **k):
        self.actions.append(k["action_type"])
        yield Tracked()

    async def get_memo_updates(self, memo_id):
        return []

    def __getattr__(self, _name):
        async def _call(*_a, **_k):
            return None
        return _call


async def _approve(note_fails=False):
    clock = Clock()
    contacts, tasks, client = Contacts(clock), Tasks(clock), Client(clock, note_fails)
    svc = HubSpotSyncService(
        client=client,
        contacts=contacts,
        companies=None,
        deals=None,
        associations=Associations(clock),
        tasks=tasks,
        crm_updates=Updates(),
        supabase=None,
    )
    result = await svc.sync_memo(
        memo_id=uuid4(),
        user_id="u-1",
        connection_id="conn-1",
        extraction=MemoExtraction(contactName="Elsa Martinez", summary="Elsa quiere una demo.", contactRole="CEO"),
        contact_id="C1",
        skip_deal=True,
        allowed_contact_fields=["jobtitle"],
        allowed_company_fields=[],
        allowed_line_item_fields=[],
        transcript="Rep: Hola Elsa. Elsa: Hola.",
        commitment_tasks=[CALL_BACK],
    )
    return result, clock, contacts, tasks, client


@pytest.mark.asyncio
async def test_the_company_is_found_while_the_contact_is_written_and_the_task_while_the_note_is():
    result, clock, contacts, tasks, client = await _approve()

    assert clock.overlap("company_lookup", "contact_read")
    assert clock.overlap("task", "note")
    # The same writes as when they ran in turn.
    assert contacts.updated == [{"jobtitle": "CEO"}]
    assert result.company_id == "CO1"
    assert tasks.created == [{"subject": CALL_BACK.text, "contact_id": "C1", "company_id": "CO1"}]
    assert result.commitment_task_ids == {"com-1": "T-1"}
    assert len(client.notes) == 1
    # The note still lists what was written on the contact: it waits for that write.
    assert clock.spans["note"][0] >= clock.spans["contact_update"][1]


@pytest.mark.asyncio
async def test_a_refused_note_does_not_lose_the_task():
    result, _clock, _contacts, tasks, client = await _approve(note_fails=True)

    assert client.notes == []
    assert tasks.created == [{"subject": CALL_BACK.text, "contact_id": "C1", "company_id": "CO1"}]
    assert result.commitment_task_ids == {"com-1": "T-1"}
