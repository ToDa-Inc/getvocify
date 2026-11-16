"""The lookups every request repeats are read once, and a change made here is seen at once."""

import asyncio

from app.services import hot_cache
from app.services.company import CompanyService


class Rows:
    def __init__(self, db, table):
        self.db, self.table = db, table

    def select(self, *a, **k):
        return self

    def eq(self, *a):
        return self

    def in_(self, *a):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a):
        return self

    def single(self):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        self.db.reads.append(self.table)

        class R:
            data = self.db.tables.get(self.table, [])

        return R()


class DB:
    def __init__(self, tables):
        self.tables, self.reads = tables, []

    def table(self, name):
        return Rows(self, name)


MEMBER = {"id": "m1", "company_id": "c1", "user_id": "u1", "role": "member", "status": "active", "visibility": "own"}


def test_a_membership_is_read_once_for_a_burst_of_requests():
    db = DB({"company_members": [MEMBER]})
    for _ in range(25):
        assert CompanyService(db).get_membership("u1").company_id == "c1"
    assert db.reads == ["company_members"]


def test_no_membership_is_never_held_so_a_rep_who_just_joined_is_seen():
    db = DB({"company_members": []})
    assert CompanyService(db).get_membership("u1") is None
    db.tables["company_members"] = [MEMBER]
    assert CompanyService(db).get_membership("u1").company_id == "c1"


def test_a_change_to_the_members_is_seen_at_once():
    db = DB({"company_members": [MEMBER]})
    CompanyService(db).get_membership("u1")
    db.tables["company_members"] = [{**MEMBER, "role": "admin"}]

    @hot_cache.changes_members
    def promote():
        pass

    promote()
    assert CompanyService(db).get_membership("u1").role == "admin"


def test_a_caller_changing_its_membership_does_not_change_the_held_one():
    db = DB({"company_members": [MEMBER]})
    CompanyService(db).get_membership("u1").role = "owner"
    assert CompanyService(db).get_membership("u1").role == "member"


def test_an_entry_expires():
    cache = hot_cache.TTLCache(0)
    cache.put("k", 1)
    assert cache.get("k") is None


def test_a_crm_schema_is_read_from_the_database_once():
    from app.services.pipedrive.schema import PipedriveSchemaService

    row = {"properties": [{"key": "title"}], "fetched_at": "2999-01-01T00:00:00+00:00"}
    db = DB({"crm_schemas": row})
    for _ in range(9):
        svc = PipedriveSchemaService.__new__(PipedriveSchemaService)
        svc.supabase, svc.connection_id = db, "conn-1"
        assert asyncio.run(svc._from_db_cache("deals")) == [{"key": "title"}]
    assert db.reads == ["crm_schemas"]
