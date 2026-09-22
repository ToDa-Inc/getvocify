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

