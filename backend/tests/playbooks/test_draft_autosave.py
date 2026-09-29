"""Playbooks v2, T2: the draft autosaves in place (one row however many saves), a stale editor is
told (409), "Descartar cambios" deletes only the pending draft, and the editor answer says whether
there is a live version and where the playbook came from."""

import copy
import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.playbooks import router as playbooks_router
from app.api.playbooks import set_playbook_store
from app.deps import get_membership, get_supabase
from app.services import feature_flags
from app.services.company import Membership
from app.services.playbooks.store import MemoryPlaybookStore, SupabasePlaybookStore
from app.services.playbooks.versions import StaleDraftError, is_newer, parse_ts, same_instant

BASE = "/api/v1/playbooks/discovery"


def draft(label="Apertura", criterion="Se presenta y pide un minuto", objection=None):
    body = {"steps": [{"label": label, "criterion": criterion}], "objections": []}
    if objection:
        body["objections"] = [{"category": "price", "guidance": objection}]
    return body


class _NoFlags:
    def table(self, _name):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        return type("R", (), {"data": []})()


@pytest.fixture
def client_for():
    store = MemoryPlaybookStore({}, {}, {}, {}, {}, {})
    set_playbook_store(store)
    feature_flags.clear_cache()

    def make(role="owner", company="co-1"):
        app = FastAPI()
        app.include_router(playbooks_router)
        app.dependency_overrides[get_membership] = lambda: Membership(
            id="m", company_id=company, user_id="u", role=role, status="active", sales_role=None,
        )
        app.dependency_overrides[get_supabase] = lambda: _NoFlags()
        return TestClient(app)

    make.store = store
    yield make
    set_playbook_store(None)
    feature_flags.clear_cache()


def js_iso(value: str) -> str:
    """What a browser's Date.toISOString() makes of a server timestamp: milliseconds and a Z."""
    parsed = parse_ts(value)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S.") + f"{parsed.microsecond // 1000:03d}Z"


# --- timestamps ---


def test_timestamps_compare_as_instants_not_strings():
    assert same_instant("2026-09-29T10:00:00.123456+00:00", "2026-09-29T10:00:00.123Z")
    assert same_instant("2026-09-29T12:00:00+02:00", "2026-09-29T10:00:00Z")
    assert same_instant("2026-09-29 10:00:00.5+00:00", "2026-09-29T10:00:00.500Z")
    assert not same_instant("2026-09-29T10:00:00.123Z", "2026-09-29T10:00:00.124Z")
    assert is_newer("2026-09-29T10:00:01+00:00", "2026-09-29T10:00:00.999999Z")
    assert not is_newer("2026-09-29T10:00:00Z", "2026-09-29T10:00:00+00:00")
    assert is_newer("2026-09-29T10:00:00Z", None) and not is_newer(None, "2026-09-29T10:00:00Z")
    assert parse_ts("nonsense") is None
    assert same_instant("nonsense", "nonsense") and not same_instant("nonsense", "other")
    assert parse_ts("2026-09-29T10:00:00.12345+00:00").microsecond == 123450


# --- API on the memory store ---


def test_ten_saves_are_one_draft(client_for):
    client = client_for()
    seen = []
    for i in range(10):
        response = client.put(f"{BASE}/draft", json=draft(criterion=f"Se presenta {i}"))
        assert response.status_code == 200
        seen.append(response.json())
    assert len({body["version_id"] for body in seen}) == 1
    stamps = [body["updated_at"] for body in seen]
    assert all(is_newer(b, a) for a, b in zip(stamps, stamps[1:]))
    assert len(client_for.store._structured) == 1
    got = client.get(f"{BASE}/editor").json()
    assert got["steps"][0]["criterion"] == "Se presenta 9"
    assert got["version_id"] == seen[0]["version_id"]
    assert got["updated_at"] == stamps[-1]
    assert got["source"] == "draft" and got["has_live"] is False and got["source_doc"] is None


def test_the_editor_answer_has_the_contract_fields(client_for):
    client = client_for()
    empty = client.get(f"{BASE}/editor").json()
    assert empty["source"] == "empty" and empty["updated_at"] is None and empty["has_live"] is False
    assert empty["version_id"] is None and empty["steps"] == []
    saved = client.put(f"{BASE}/draft", json=draft()).json()
    assert set(saved) >= {"sales_motion_key", "source", "source_doc", "version_id", "updated_at", "has_live", "steps", "objections", "categories"}


def test_publishing_then_editing_creates_a_new_draft_and_leaves_the_live_version(client_for):
    client = client_for()
    first = client.put(f"{BASE}/draft", json=draft("Apertura")).json()
    assert client.post(f"{BASE}/publish").status_code == 200
    live = client.get(f"{BASE}/editor").json()
    assert live["source"] == "published" and live["has_live"] is True
    assert live["version_id"] == first["version_id"]

    edited = client.put(f"{BASE}/draft", json={**draft("Apertura nueva"), "base_updated_at": live["updated_at"]})
    assert edited.status_code == 200
    body = edited.json()
    assert body["version_id"] != live["version_id"]
    assert body["source"] == "draft" and body["has_live"] is True
    # A rep still reads the live version; the manager reads the draft.
    rep = client_for(role="member").get(f"{BASE}/editor").json()
    assert rep["source"] == "published" and rep["steps"][0]["label"] == "Apertura"
    assert client.get(f"{BASE}/editor").json()["steps"][0]["label"] == "Apertura nueva"
    # More edits keep updating that new draft in place.
    again = client.put(f"{BASE}/draft", json=draft("Apertura nueva 2")).json()
    assert again["version_id"] == body["version_id"]


def test_a_stale_base_is_409_and_changes_nothing(client_for):
    client = client_for()
    one = client.put(f"{BASE}/draft", json=draft("Uno")).json()
    two = client.put(f"{BASE}/draft", json={**draft("Dos"), "base_updated_at": one["updated_at"]})
    assert two.status_code == 200
    stale = client.put(f"{BASE}/draft", json={**draft("Tres"), "base_updated_at": one["updated_at"]})
    assert stale.status_code == 409
    assert stale.json()["detail"] == {"code": "stale_draft"}
    assert client.get(f"{BASE}/editor").json()["steps"][0]["label"] == "Dos"
    ok = client.put(f"{BASE}/draft", json={**draft("Cuatro"), "base_updated_at": two.json()["updated_at"]})
    assert ok.status_code == 200


def test_a_base_that_went_through_a_js_date_still_matches(client_for):
    client = client_for()
    saved = client.put(f"{BASE}/draft", json=draft("Uno")).json()
    ok = client.put(f"{BASE}/draft", json={**draft("Dos"), "base_updated_at": js_iso(saved["updated_at"])})
    assert ok.status_code == 200


def test_a_base_for_a_draft_that_no_longer_exists_is_stale(client_for):
    client = client_for()
    saved = client.put(f"{BASE}/draft", json=draft("Uno")).json()
    assert client.delete(f"{BASE}/draft").status_code == 200
    response = client.put(f"{BASE}/draft", json={**draft("Dos"), "base_updated_at": saved["updated_at"]})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "stale_draft"


def test_a_null_base_never_conflicts(client_for):
    client = client_for()
    client.put(f"{BASE}/draft", json=draft("Uno"))
    assert client.put(f"{BASE}/draft", json={**draft("Dos"), "base_updated_at": None}).status_code == 200


def test_discarding_without_a_live_version_leaves_it_empty(client_for):
    client = client_for()
    client.put(f"{BASE}/draft", json=draft())
    assert client.get("/api/v1/playbooks").json()["motions"]["discovery"] == "draft"
    response = client.delete(f"{BASE}/draft")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "empty" and body["steps"] == [] and body["has_live"] is False
    assert body["updated_at"] is None and body["version_id"] is None
    assert client.get("/api/v1/playbooks").json()["motions"]["discovery"] == "missing"
    assert client.post(f"{BASE}/publish").status_code == 409  # nothing left to publish


def test_discarding_over_a_live_version_returns_to_published(client_for):
    client = client_for()
    live = client.put(f"{BASE}/draft", json=draft("Apertura")).json()
    client.post(f"{BASE}/publish")
    client.put(f"{BASE}/draft", json=draft("Cambio a medias"))
    response = client.delete(f"{BASE}/draft")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "published" and body["has_live"] is True
    assert body["version_id"] == live["version_id"]
    assert body["steps"][0]["label"] == "Apertura"
    assert client.get("/api/v1/playbooks").json()["motions"]["discovery"] == "published"


def test_discarding_never_touches_a_published_version_and_is_idempotent(client_for):
    client = client_for()
    client.put(f"{BASE}/draft", json=draft("Apertura"))
    client.post(f"{BASE}/publish")
    for _ in range(2):
        body = client.delete(f"{BASE}/draft").json()
        assert body["source"] == "published" and body["steps"][0]["label"] == "Apertura"
    assert len(client_for.store._published_versions) == 1


def test_a_member_cannot_save_discard_or_reach_a_draft(client_for):
    client_for().put(f"{BASE}/draft", json=draft())
    rep = client_for(role="member")
    assert rep.put(f"{BASE}/draft", json=draft("Otro")).status_code == 403
    assert rep.delete(f"{BASE}/draft").status_code == 403
    assert client_for().get(f"{BASE}/editor").json()["steps"][0]["label"] == "Apertura"
    assert rep.get(f"{BASE}/editor").json()["source"] == "empty"


def test_the_source_travels_with_the_draft_and_survives_publishing(client_for):
    client = client_for()
    source = client_for.store.save_source("co-1", "discovery", "pdf", "guion-sdr.pdf", "Confirmar el problema")
    saved = client.put(f"{BASE}/draft", json={**draft(), "source_id": source["id"]}).json()
    assert saved["source_doc"] == {"id": source["id"], "kind": "pdf", "name": "guion-sdr.pdf"}
    # A later save that does not repeat the id keeps it.
    kept = client.put(f"{BASE}/draft", json=draft("Apertura 2")).json()
    assert kept["source_doc"]["id"] == source["id"]
    client.post(f"{BASE}/publish")
    assert client.get(f"{BASE}/editor").json()["source_doc"]["name"] == "guion-sdr.pdf"
    assert client_for(role="member").get(f"{BASE}/editor").json()["source_doc"]["name"] == "guion-sdr.pdf"
    # The next draft over the live version still points at it.
    over = client.put(f"{BASE}/draft", json=draft("Apertura 3")).json()
    assert over["source_doc"]["id"] == source["id"]


def test_a_source_id_from_another_company_or_made_up_is_ignored(client_for):
    client = client_for()
    other = client_for.store.save_source("co-2", "discovery", "text", "ajeno", "secreto")
    for bad in (other["id"], "source:nope", "editor:abc", "x"):
        saved = client.put(f"{BASE}/draft", json={**draft(), "source_id": bad}).json()
        assert saved["source_doc"] is None


def test_an_editor_save_clears_a_contradictory_import_gate(client_for):
    client = client_for()
    client.post(
        "/api/v1/playbooks/imports",
        json={"import_id": "imp-c", "kind": "text", "payload": "Nunca descuentes. Siempre cierra.", "sales_motion_key": "discovery"},
    )
    assert client.post(f"{BASE}/publish").status_code == 409
    client.put(f"{BASE}/draft", json=draft())
    assert client.post(f"{BASE}/publish").status_code == 200


# --- SupabasePlaybookStore against an in-memory PostgREST stand-in ---


class _Result:
    def __init__(self, data):
        self.data = data


class FakeDb:
    """Just enough of supabase-py and of the database for the playbook tables: chained filters,
    insert/update/upsert/delete returning rows, the updated_at trigger on playbook_versions and the
    two RPCs the store relies on."""

    def __init__(self):
        self.tables = {"playbooks": [], "playbook_versions": [], "playbook_imports": [], "company_sales_knowledge": []}
        self._clock = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)

    def tick(self) -> str:
        self._clock += timedelta(milliseconds=5)
        return self._clock.isoformat()

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        return _Rpc(self, name, params)


class _Rpc:
    def __init__(self, db, name, params):
        self.db, self.name, self.params = db, name, params

    def execute(self):
        db, params = self.db, self.params
        if self.name == "publish_playbook_motion":
            pb = next((p for p in db.tables["playbooks"] if p["company_id"] == params["p_company"] and p["sales_motion_key"] == params["p_motion"]), None)
            drafts = [v for v in db.tables["playbook_versions"] if pb and v["playbook_id"] == pb["id"] and v["status"] == "draft"]
            if not drafts:
                return _Result("not_a_draft")
            latest = max(drafts, key=lambda v: parse_ts(v["created_at"]))
            latest["status"], latest["updated_at"] = "published", db.tick()
            pb["active_version_id"] = latest["id"]
            return _Result(f"published:{latest['id']}")
        if self.name == "list_playbook_motions":
            rows = []
            for pb in db.tables["playbooks"]:
                if pb["company_id"] != params["p_company"]:
                    continue
                has_draft = any(v["playbook_id"] == pb["id"] and v["status"] == "draft" for v in db.tables["playbook_versions"])
                status = "published" if pb["active_version_id"] else "draft" if has_draft else "missing"
                rows.append({"sales_motion_key": pb["sales_motion_key"], "motion_status": status})
            return _Result(rows)
        raise AssertionError(self.name)


class _Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.op, self.payload, self.filters = "select", None, []
        self._order, self._limit, self._upsert = None, None, {}

    def select(self, *_a, **_k):
        return self

    def eq(self, col, value):
        self.filters.append(lambda row: row.get(col) == value)
        return self

    def in_(self, col, values):
        self.filters.append(lambda row: row.get(col) in list(values))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def upsert(self, payload, on_conflict=None, ignore_duplicates=False):
        self.op, self.payload, self._upsert = "upsert", payload, {"on": on_conflict, "ignore": ignore_duplicates}
        return self

    def delete(self):
        self.op = "delete"
        return self

    def _matching(self):
        rows = [r for r in self.db.tables[self.name] if all(f(r) for f in self.filters)]
        if self._order:
            col, desc = self._order
            rows.sort(key=lambda r: parse_ts(r[col]) or r[col], reverse=desc)
        return rows[: self._limit] if self._limit else rows

    def execute(self):
        db, table = self.db, self.db.tables[self.name]
        if self.op == "select":
            return _Result(copy.deepcopy(self._matching()))
        if self.op == "insert":
            row = dict(self.payload)
            if self.name in ("playbooks", "playbook_versions"):
                row.setdefault("id", str(uuid.uuid4()))
            if self.name == "playbooks":
                row.setdefault("active_version_id", None)
            if self.name == "playbook_versions":
                row.setdefault("status", "draft")
                stamp = db.tick()
                row["created_at"] = row["updated_at"] = stamp
            if self.name == "playbook_imports":
                if any(r["id"] == row["id"] for r in table):
                    raise AssertionError("duplicate import id")
                row["created_at"] = db.tick()
            table.append(row)
            return _Result([copy.deepcopy(row)])
        if self.op == "upsert":
            keys = self._upsert["on"].split(",")
            if self.name == "company_sales_knowledge":  # a real upsert: the trigger stamps updated_at
                match = next((r for r in table if all(r.get(k) == self.payload[k] for k in keys)), None)
                if match is not None:
                    match.update(self.payload)
                    match["updated_at"] = db.tick()
                    return _Result([copy.deepcopy(match)])
                row = {**self.payload, "updated_at": db.tick()}
                table.append(row)
                return _Result([copy.deepcopy(row)])
            if any(all(r.get(k) == self.payload[k] for k in keys) for r in table):
                return _Result([])
            row = {**self.payload, "id": str(uuid.uuid4()), "active_version_id": None}
            table.append(row)
            return _Result([copy.deepcopy(row)])
        if self.op == "update":
            rows = self._matching()
            for row in rows:
                row.update(self.payload)
                if self.name in ("playbook_versions", "company_sales_knowledge"):
                    row["updated_at"] = db.tick()
            return _Result(copy.deepcopy(rows))
        if self.op == "delete":
            rows = self._matching()
            ids = {id(r) for r in rows}
            table[:] = [r for r in table if id(r) not in ids]
            return _Result(copy.deepcopy(rows))
        raise AssertionError(self.op)


@pytest.fixture
def pg():
    db = FakeDb()
    return db, SupabasePlaybookStore(db)


STEPS = [{"step_id": "apertura", "label": "Apertura", "criterion": "Se presenta"}]
ENTRIES = [{"entry_id": "objection:price", "category": "price", "guidance": "ROI", "source_ref": "editor"}]


def rows(db, table, **where):
    return [r for r in db.tables[table] if all(r.get(k) == v for k, v in where.items())]


def test_supabase_ten_saves_are_one_version_row_and_one_editor_import(pg):
    db, store = pg
    versions = [
        store.save_structured_draft("co", "discovery", [{**STEPS[0], "criterion": f"Se presenta {i}"}], ENTRIES)
        for i in range(10)
    ]
    assert len({v["id"] for v in versions}) == 1
    assert len(db.tables["playbook_versions"]) == 1
    imports = rows(db, "playbook_imports", kind="editor")
    assert len(imports) == 1 and imports[0]["id"] == f"editor:{versions[0]['id']}"
    assert "Se presenta 9" in imports[0]["draft"]["text"]
    assert imports[0]["draft"]["contradictions"] == []
    assert db.tables["playbook_versions"][0]["steps"][0]["criterion"] == "Se presenta 9"
    assert is_newer(versions[-1]["updated_at"], versions[0]["updated_at"])
    state = store.editor_snapshot("co", "discovery", include_draft=True)
    assert state["state"] == "draft" and state["has_live"] is False
    assert state["version"]["updated_at"] == versions[-1]["updated_at"]


def test_supabase_publish_then_edit_inserts_a_new_draft(pg):
    db, store = pg
    first = store.save_structured_draft("co", "discovery", STEPS, ENTRIES)
    store.save_structured_draft("co", "discovery", STEPS, ENTRIES)
    store.publish("co", "discovery", "owner")
    live_state = store.editor_snapshot("co", "discovery", include_draft=True)
    assert live_state["state"] == "published" and live_state["has_live"] is True
    edited = store.save_structured_draft(
        "co", "discovery", [{**STEPS[0], "label": "Otra"}], [], base_updated_at=live_state["version"]["updated_at"],
    )
    assert edited["id"] != first["id"]
    assert len(db.tables["playbook_versions"]) == 2
    assert rows(db, "playbook_versions", id=first["id"])[0]["status"] == "published"
    assert len(rows(db, "playbook_imports", kind="editor")) == 2
    state = store.editor_snapshot("co", "discovery", include_draft=True)
    assert state["state"] == "draft" and state["version"]["id"] == edited["id"] and state["has_live"] is True
    assert store.editor_snapshot("co", "discovery", include_draft=False)["state"] == "published"
    store.save_structured_draft("co", "discovery", STEPS, ENTRIES)
    assert len(db.tables["playbook_versions"]) == 2


def test_supabase_stale_draft_raises_and_leaves_the_row(pg):
    db, store = pg
    one = store.save_structured_draft("co", "discovery", STEPS, ENTRIES)
    two = store.save_structured_draft("co", "discovery", [{**STEPS[0], "label": "Dos"}], ENTRIES, base_updated_at=one["updated_at"])
    with pytest.raises(StaleDraftError):
        store.save_structured_draft("co", "discovery", [{**STEPS[0], "label": "Tres"}], ENTRIES, base_updated_at=one["updated_at"])
    assert db.tables["playbook_versions"][0]["steps"][0]["label"] == "Dos"
    store.save_structured_draft("co", "discovery", [{**STEPS[0], "label": "Cuatro"}], ENTRIES, base_updated_at=js_iso(two["updated_at"]))
    assert db.tables["playbook_versions"][0]["steps"][0]["label"] == "Cuatro"


def test_supabase_a_draft_published_meanwhile_is_stale_and_not_overwritten(pg):
    db, store = pg
    one = store.save_structured_draft("co", "discovery", STEPS, ENTRIES)
    store.publish("co", "discovery", "owner")  # another manager published it
    with pytest.raises(StaleDraftError):
        store.save_structured_draft("co", "discovery", [{**STEPS[0], "label": "Tarde"}], ENTRIES, base_updated_at=one["updated_at"])
    assert db.tables["playbook_versions"][0]["steps"][0]["label"] == "Apertura"
    assert len(db.tables["playbook_versions"]) == 1


def test_supabase_a_first_save_over_a_live_version_needs_the_live_updated_at(pg):
    db, store = pg
    store.save_structured_draft("co", "discovery", STEPS, ENTRIES)
    store.publish("co", "discovery", "owner")
    live = store.editor_snapshot("co", "discovery", include_draft=True)["version"]
    with pytest.raises(StaleDraftError):
        store.save_structured_draft("co", "discovery", STEPS, ENTRIES, base_updated_at="2020-01-01T00:00:00Z")
    store.save_structured_draft("co", "discovery", STEPS, ENTRIES, base_updated_at=live["updated_at"])


def test_supabase_discard_deletes_the_pending_draft_and_its_import_only(pg):
    db, store = pg
    live = store.save_structured_draft("co", "discovery", STEPS, ENTRIES)
    store.publish("co", "discovery", "owner")
    draft_v = store.save_structured_draft("co", "discovery", [{**STEPS[0], "label": "Otra"}], ENTRIES)
    assert store.discard_draft("co", "discovery") is True
    assert [v["id"] for v in db.tables["playbook_versions"]] == [live["id"]]
    assert {r["id"] for r in rows(db, "playbook_imports", kind="editor")} == {f"editor:{live['id']}"}
    assert f"editor:{draft_v['id']}" not in {r["id"] for r in db.tables["playbook_imports"]}
    state = store.editor_snapshot("co", "discovery", include_draft=True)
    assert state["state"] == "published" and state["version"]["id"] == live["id"]
    assert store.discard_draft("co", "discovery") is False  # nothing pending: the published one stays
    assert len(db.tables["playbook_versions"]) == 1
    assert store.motions("co") == {"discovery": "published"}


def test_supabase_discard_without_a_live_version_removes_every_draft_row(pg):
    db, store = pg
    playbook = db.table("playbooks").upsert({"company_id": "co", "sales_motion_key": "discovery"}, on_conflict="company_id,sales_motion_key", ignore_duplicates=True).execute().data[0]
    for _ in range(3):  # rows left by the one-row-per-save era
        db.table("playbook_versions").insert({"playbook_id": playbook["id"], "status": "draft", "steps": STEPS, "entries": []}).execute()
    store.save_structured_draft("co", "discovery", STEPS, ENTRIES)
    assert store.discard_draft("co", "discovery") is True
    assert db.tables["playbook_versions"] == []
    assert store.editor_snapshot("co", "discovery", include_draft=True)["state"] == "empty"
    assert store.motions("co") == {"discovery": "missing"}


def test_supabase_an_old_draft_behind_the_live_version_is_not_pending(pg):
    db, store = pg
    playbook = db.table("playbooks").upsert({"company_id": "co", "sales_motion_key": "discovery"}, on_conflict="company_id,sales_motion_key", ignore_duplicates=True).execute().data[0]
    old = db.table("playbook_versions").insert({"playbook_id": playbook["id"], "status": "draft", "steps": STEPS, "entries": []}).execute().data[0]
    store.save_structured_draft("co", "discovery", STEPS, ENTRIES)  # updates `old` (the only draft)
    assert store.publish("co", "discovery", "owner")
    stale_row = db.table("playbook_versions").insert({"playbook_id": playbook["id"], "status": "draft", "steps": [], "entries": []}).execute().data[0]
    # Make it older than the live version, as a draft left behind before a publish.
    rows(db, "playbook_versions", id=stale_row["id"])[0]["created_at"] = "2020-01-01T00:00:00+00:00"
    state = store.editor_snapshot("co", "discovery", include_draft=True)
    assert state["state"] == "published" and state["version"]["id"] == old["id"]
    fresh = store.save_structured_draft("co", "discovery", STEPS, ENTRIES)
    assert fresh["id"] not in (old["id"], stale_row["id"])
    assert store.discard_draft("co", "discovery") is True
    assert {v["id"] for v in db.tables["playbook_versions"]} == {old["id"], stale_row["id"]}


def test_supabase_source_is_stored_and_read_back_and_travels_across_publishing(pg):
    db, store = pg
    source = store.save_source("co", "discovery", "audio", "dictado.webm", "Hola, esto es el guion")
    row = rows(db, "playbook_imports", id=source["id"])[0]
    assert source["id"].startswith("source:")
    assert row["kind"] == "audio" and row["status"] == "ready" and row["company_id"] == "co"
    assert row["draft"]["text"] == "Hola, esto es el guion" and row["draft"]["name"] == "dictado.webm"
    assert row["draft"]["source_ref"]
    assert row["playbook_id"] == db.tables["playbooks"][0]["id"]
    assert db.tables["playbook_versions"] == []  # a source is not a version

    v1 = store.save_structured_draft("co", "discovery", STEPS, ENTRIES, source_id=source["id"])
    assert rows(db, "playbook_imports", id=f"editor:{v1['id']}")[0]["draft"]["source_id"] == source["id"]
    store.save_structured_draft("co", "discovery", STEPS, ENTRIES)  # keeps it
    assert store.editor_snapshot("co", "discovery", include_draft=True)["source"] == {
        "id": source["id"], "kind": "audio", "name": "dictado.webm",
    }
    store.publish("co", "discovery", "owner")
    assert store.editor_snapshot("co", "discovery", include_draft=False)["source"]["id"] == source["id"]
    v2 = store.save_structured_draft("co", "discovery", STEPS, ENTRIES)  # first edit over live
    assert v2["id"] != v1["id"]
    assert store.editor_snapshot("co", "discovery", include_draft=True)["source"]["id"] == source["id"]
    assert store.get_source("other-co", source["id"]) is None
    assert store.get_source("co", "editor:whatever") is None
    other = store.save_source("co", "discovery", "text", "n", "t")
    store.save_structured_draft("co", "discovery", STEPS, ENTRIES, source_id=other["id"])
    assert store.editor_snapshot("co", "discovery", include_draft=True)["source"]["id"] == other["id"]


def test_supabase_a_source_of_another_company_is_ignored(pg):
    db, store = pg
    foreign = store.save_source("co-2", "discovery", "text", "ajeno", "secreto")
    store.save_structured_draft("co", "discovery", STEPS, ENTRIES, source_id=foreign["id"])
    assert store.editor_snapshot("co", "discovery", include_draft=True)["source"] is None


def test_supabase_editor_with_no_playbook_row_is_empty(pg):
    _db, store = pg
    assert store.editor_snapshot("co", "discovery", include_draft=True) == {
        "state": "empty", "version": None, "has_live": False, "source": None,
    }
    assert store.editor_version("co", "discovery", include_draft=True) == ("empty", None)
    assert store.discard_draft("co", "discovery") is False


def test_the_migration_adds_updated_at_and_a_trigger():
    from pathlib import Path

    migrations = Path(__file__).resolve().parents[2] / "migrations"
    up = (migrations / "066_playbook_draft_autosave.sql").read_text()
    down = (migrations / "066_playbook_draft_autosave.down.sql").read_text()
    assert "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()" in up
    assert "BEFORE UPDATE ON playbook_versions" in up
    assert "DROP COLUMN IF EXISTS updated_at" in down
    reset = (Path(__file__).resolve().parents[2] / "full_reset.sql").read_text()
    assert "playbook_versions_updated_at" in reset
