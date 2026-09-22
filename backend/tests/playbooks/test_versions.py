"""F08: one active playbook version, and a meeting keeps the version it started with."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-playbooks-32b+")

import pytest

from app.services.playbooks.versions import (
    can_publish,
    get_published_playbook,
    snapshot_for_capture,
    validate_entries,
)

PLAYBOOK = {"id": "pb-1", "company_id": "co-1", "sales_motion_key": "discovery", "active_version_id": "pv-2"}
V1 = {"id": "pv-1", "status": "published", "steps": [{"step_id": "pain", "label": "Confirmar problema", "criterion": "El prospecto confirma un problema concreto"}], "entries": []}
V2 = {"id": "pv-2", "status": "published", "steps": [{"step_id": "next", "label": "Siguiente paso", "criterion": "Hay un siguiente paso concreto"}], "entries": []}


def test_capture_keeps_the_version_fixed_at_the_start():
    assert snapshot_for_capture("pv-1", "pv-2") == "pv-1"
    assert get_published_playbook(PLAYBOOK, [V1, V2], version_id="pv-1")["version_id"] == "pv-1"
    assert get_published_playbook(PLAYBOOK, [V1, V2])["version_id"] == "pv-2"


def test_member_cannot_publish_and_an_entry_needs_a_source():
    assert can_publish("member") is False
    assert can_publish("owner") is True
    with pytest.raises(ValueError):
        validate_entries([{"entry_id": "e1", "source_ref": "  "}])


def test_unpublished_playbook_is_explicitly_absent():
    draft = {**PLAYBOOK, "active_version_id": None}
    assert get_published_playbook(draft, [{**V1, "status": "draft"}]) is None


def test_publishing_discovery_does_not_activate_another_motion_and_a_member_cannot():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import playbooks as playbooks_api
    from app.api.playbooks import router as playbooks_router
    from app.deps import get_membership
    from app.services.company import Membership

    playbooks_api._MOTIONS.clear()
    role = {"value": "owner"}
    app = FastAPI()
    app.include_router(playbooks_router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co", user_id="u", role=role["value"], status="active",
    )
    client = TestClient(app)
    created = client.post(
        "/api/v1/playbooks/imports",
        json={
            "import_id": "imp-discovery",
            "kind": "text",
            "payload": "Confirmar el problema antes del precio.",
            "sales_motion_key": "discovery",
        },
    )
    assert created.status_code == 200
    assert created.json()["published"] is False
    missing = client.post("/api/v1/playbooks/qualification/publish")
    assert missing.status_code == 409
    published = client.post("/api/v1/playbooks/discovery/publish")
    assert published.status_code == 200
    motions = published.json()["motions"]
    assert motions["discovery"] == "published"
    assert motions.get("qualification") != "published"
    listed = client.get("/api/v1/playbooks")
    assert listed.status_code == 200
    assert listed.json()["motions"]["discovery"] == "published"
    role["value"] = "member"
    denied = client.post("/api/v1/playbooks/discovery/publish")
    assert denied.status_code == 403
    assert playbooks_api._MOTIONS["co"]["discovery"] == "published"


def test_two_publishes_leave_one_active_pointer_and_both_versions(tmp_path=None):
    import os
    import shutil
    import socket
    import subprocess
    import tempfile
    import threading
    from pathlib import Path

    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres:
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-pb-"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    subprocess.run(
        [initdb, "-D", str(datadir), "--auth=trust", "--no-instructions", "-U", "vocify", "--encoding=UTF8", "--locale=C"],
        check=True, env=env, capture_output=True,
    )
    log = open(datadir / "pg.log", "w")
    proc = subprocess.Popen(
        [postgres, "-D", str(datadir), "-p", str(port), "-h", "127.0.0.1", "-k", str(datadir)],
        stdout=log, stderr=subprocess.STDOUT, env=env,
    )
    dsn = f"postgresql://vocify@127.0.0.1:{port}/postgres"

    def psql(sql: str):
        return subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-c", sql],
            capture_output=True, text=True, env=env, check=False,
        )

    try:
        for _ in range(40):
            if psql("SELECT 1;").returncode == 0:
                break
        migration = Path(__file__).resolve().parents[2] / "migrations" / "040_company_playbooks.sql"
        applied = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(migration)],
            capture_output=True, text=True, env=env, check=False,
        )
        assert applied.returncode == 0, applied.stderr
        seed = psql(
            """
            INSERT INTO playbooks (id, company_id, sales_motion_key)
            VALUES ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'discovery');
            INSERT INTO playbook_versions (id, playbook_id) VALUES
              ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'),
              ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa');
            """
        )
        assert seed.returncode == 0, seed.stderr
        barrier = threading.Barrier(2)

        def publish(version: str) -> None:
            barrier.wait(timeout=5)
            result = psql(
                f"BEGIN; SELECT publish_playbook_version('{version}'); SELECT pg_sleep(0.4); COMMIT;"
            )
            assert result.returncode == 0, result.stderr

        threads = [
            threading.Thread(target=publish, args=("cccccccc-cccc-cccc-cccc-cccccccccccc",)),
            threading.Thread(target=publish, args=("dddddddd-dddd-dddd-dddd-dddddddddddd",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        active = psql("SELECT active_version_id::text FROM playbooks;")
        published = psql("SELECT count(*) FROM playbook_versions WHERE status = 'published';")
        assert active.returncode == 0
        assert "cccccccc-cccc-cccc-cccc-cccccccccccc" in active.stdout or "dddddddd-dddd-dddd-dddd-dddddddddddd" in active.stdout
        assert active.stdout.count("cccc-cccc-cccc-cccc") + active.stdout.count("dddd-dddd-dddd-dddd") == 1
        assert "2" in published.stdout
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)


def test_a_text_draft_is_stored_and_publishing_discovery_leaves_qualification_alone():
    import os
    import shutil
    import socket
    import subprocess
    import tempfile
    from pathlib import Path

    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres:
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-pb-draft-"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    subprocess.run(
        [initdb, "-D", str(datadir), "--auth=trust", "--no-instructions", "-U", "vocify", "--encoding=UTF8", "--locale=C"],
        check=True, env=env, capture_output=True,
    )
    log = open(datadir / "pg.log", "w")
    proc = subprocess.Popen(
        [postgres, "-D", str(datadir), "-p", str(port), "-h", "127.0.0.1", "-k", str(datadir)],
        stdout=log, stderr=subprocess.STDOUT, env=env,
    )
    dsn = f"postgresql://vocify@127.0.0.1:{port}/postgres"
    company = "11111111-1111-1111-1111-111111111111"

    def psql(sql: str):
        return subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql],
            capture_output=True, text=True, env=env, check=False,
        )

    try:
        for _ in range(40):
            if psql("SELECT 1;").returncode == 0:
                break
        migration = Path(__file__).resolve().parents[2] / "migrations" / "040_company_playbooks.sql"
        applied = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(migration)],
            capture_output=True, text=True, env=env, check=False,
        )
        assert applied.returncode == 0, applied.stderr
        saved = psql(
            f"SELECT save_playbook_draft('{company}', 'discovery', 'imp-1', 'Confirmar el problema');"
        )
        assert saved.returncode == 0, saved.stderr
        assert saved.stdout.strip() == "ready"
        again = psql(
            f"SELECT save_playbook_draft('{company}', 'discovery', 'imp-1', 'Otro texto');"
        )
        assert again.returncode == 0, again.stderr
        assert psql("SELECT count(*) FROM playbook_versions;").stdout.strip() == "1"
        assert psql(
            "SELECT CASE WHEN active_version_id IS NULL THEN 'still-draft' ELSE 'already-active' END FROM playbooks;"
        ).stdout.strip() == "still-draft"
        missing = psql(f"SELECT publish_playbook_motion('{company}', 'qualification');")
        assert missing.stdout.strip() == "not_a_draft"
        published = psql(f"SELECT publish_playbook_motion('{company}', 'discovery');")
        assert published.stdout.strip() == "published"
        assert psql(
            "SELECT CASE WHEN active_version_id IS NOT NULL THEN 'now-active' ELSE 'still-empty' END "
            "FROM playbooks WHERE sales_motion_key = 'discovery';"
        ).stdout.strip() == "now-active"
        listed = psql(
            f"SELECT sales_motion_key || ':' || motion_status FROM list_playbook_motions('{company}') ORDER BY 1;"
        )
        assert listed.stdout.strip() == "discovery:published"
        assert psql(
            "SELECT count(*) FROM playbooks WHERE sales_motion_key = 'qualification';"
        ).stdout.strip() == "0"
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)


def test_the_publish_route_asks_postgres_for_one_motion_only():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.playbooks import router as playbooks_router
    from app.api.playbooks import set_playbook_store
    from app.deps import get_membership
    from app.services.company import Membership
    from app.services.playbooks.store import SupabasePlaybookStore

    class Result:
        def __init__(self, data):
            self.data = data

        def execute(self):
            return self

    class Client:
        def __init__(self):
            self.calls = []
            self.motions = {}

        def table(self, _name):
            class Chain:
                def select(self, *_args, **_kwargs):
                    return self

                def eq(self, *_args, **_kwargs):
                    return self

                def limit(self, *_args, **_kwargs):
                    return self

                def execute(self):
                    return Result([])

            return Chain()

        def rpc(self, name, params):
            self.calls.append((name, params))
            if name == "save_playbook_draft":
                self.motions[params["p_motion"]] = "draft"
                return Result("ready")
            if name == "list_playbook_motions":
                return Result([
                    {"sales_motion_key": key, "motion_status": status}
                    for key, status in self.motions.items()
                ])
            if name == "publish_playbook_motion":
                if self.motions.get(params["p_motion"]) != "draft":
                    return Result("not_a_draft")
                self.motions[params["p_motion"]] = "published"
                return Result("published")
            raise AssertionError(name)

    database = Client()
    set_playbook_store(SupabasePlaybookStore(database))
    app = FastAPI()
    app.include_router(playbooks_router)
    app.dependency_overrides[get_membership] = lambda: Membership(
        id="m", company_id="co", user_id="u", role="owner", status="active",
    )
    client = TestClient(app)
    try:
        created = client.post(
            "/api/v1/playbooks/imports",
            json={
                "import_id": "imp-discovery",
                "kind": "text",
                "payload": "Confirmar el problema antes del precio.",
                "sales_motion_key": "discovery",
            },
        )
        assert created.status_code == 200
        assert client.post("/api/v1/playbooks/qualification/publish").status_code == 409
        published = client.post("/api/v1/playbooks/discovery/publish")
        assert published.status_code == 200
        assert published.json()["motions"]["discovery"] == "published"
        assert "qualification" not in published.json()["motions"]
        assert [
            params["p_motion"]
            for name, params in database.calls
            if name == "publish_playbook_motion"
        ] == ["discovery"]
    finally:
        set_playbook_store(None)

