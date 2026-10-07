"""Migration 066_playbooks_v2: the one migration of the playbooks feature (plan section 17).

Text checks run everywhere. The rest runs against a real PostgreSQL (tests/playbooks/pg_support.py: the
VOCIFY_TEST_PG_DSN server, or a throwaway cluster; skipped when there is none): a fresh database, running it twice,
upgrading a database where the old 066-069 were applied, the down migration, the playbooks_live view, the error
convention and the SQL functions that predate it (publish, list, add a type).

What the playbooks SQL functions do for the editor (save draft, pause, delete, knowledge, intake) is covered by the
repository contract suite, test_repository_contract.py, which runs against the same PostgreSQL.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from tests.playbooks import pg_support

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"
UP = MIGRATIONS / "066_playbooks_v2.sql"
DOWN = MIGRATIONS / "066_playbooks_v2.down.sql"
LEGACY = Path(__file__).resolve().parent / "fixtures" / "legacy_066_069.sql"
ACTIVATION = ROOT.parent / "docs" / "superpowers" / "plans" / "2026-09-29-activacion-playbooks-v2.sql"
CO = "11111111-1111-1111-1111-111111111111"


# --- text -------------------------------------------------------------------------------------


def test_one_migration_replaces_066_to_069():
    names = {path.name for path in MIGRATIONS.glob("06[6-9]_*")}
    assert names == {"066_playbooks_v2.sql", "066_playbooks_v2.down.sql"}


def test_the_migration_documents_its_error_convention_and_codes():
    head = UP.read_text(encoding="utf-8").split("BEGIN;")[0]
    assert "ERROR CONVENTION" in head and "RAISE EXCEPTION" in head
    for code in ("stale_draft", "stale_knowledge", "not_published", "not_paused", "not_archived", "not_found", "not_a_draft", "contradiction"):
        assert code in head


def test_the_final_columns_are_declared():
    up = UP.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS label TEXT" in up
    assert "ADD COLUMN IF NOT EXISTS applies_to JSONB" in up
    assert "ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'paused'))" in up
    assert "ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL" in up
    assert "qualification JSONB NOT NULL DEFAULT '[]'::jsonb" in up
    assert "CREATE TABLE IF NOT EXISTS company_sales_knowledge" in up
    assert "DROP COLUMN IF EXISTS paused_version_id" in up and "DROP COLUMN IF EXISTS archived_state" in up
    assert "active_version_id IS NOT NULL" in up.split("CREATE OR REPLACE VIEW playbooks_live")[1].split(";")[0]


def test_full_reset_carries_the_same_functions_view_and_columns():
    up = UP.read_text(encoding="utf-8")
    reset = (ROOT / "full_reset.sql").read_text(encoding="utf-8")
    block = up[up.index("-- ─── updated_at triggers"):up.rindex("COMMIT;")].strip()
    assert block in reset
    assert "state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'paused'))" in reset
    assert "paused_version_id" not in reset and "archived_state" not in reset
    assert "CREATE TABLE IF NOT EXISTS company_sales_knowledge" in reset


def test_publishing_never_copies_columns():
    """publish_playbook_version flips status on the row and points the playbook at it: a new column can not be dropped
    by publishing."""
    up = UP.read_text(encoding="utf-8")
    start = up.index("CREATE OR REPLACE FUNCTION publish_playbook_version")
    end = up.index("CREATE OR REPLACE FUNCTION save_playbook_draft")
    assert "INSERT INTO playbook_versions" not in up[start:end]
    assert "UPDATE playbook_versions SET status = 'published'" in up[start:end]
    start = up.index("CREATE OR REPLACE FUNCTION publish_playbook_motion")
    end = up.index("CREATE OR REPLACE FUNCTION list_playbook_motions")
    assert "INSERT INTO playbook_versions" not in up[start:end]


def test_the_activation_script_says_to_run_the_one_migration():
    text = ACTIVATION.read_text(encoding="utf-8")
    part_a = text.split("PARTE A")[1].split("PARTE B")[0]
    assert "066_playbooks_v2.sql" in part_a
    assert "paused_version_id" not in text and "069_playbook_pause_archive" not in text
    assert "PLAYBOOK_ROUTING_ENABLED" in text.split("PARTE B")[-1]


# --- PostgreSQL: the migration itself ------------------------------------------------------------


def _schema(pg: pg_support.PgClient) -> str:
    """Columns of the playbooks tables, the function definitions and the view, as one comparable text."""
    return pg.sql(
        """
        SELECT string_agg(line, E'\\n' ORDER BY line) FROM (
          SELECT 'col ' || table_name || '.' || column_name || ' ' || data_type || ' ' || is_nullable || ' '
                 || COALESCE(column_default, '') AS line
          FROM information_schema.columns
          WHERE table_schema = 'public'
            AND table_name IN ('playbooks', 'playbook_versions', 'company_sales_knowledge', 'playbook_imports', 'interaction_types')
          UNION ALL
          SELECT 'fn ' || md5(pg_get_functiondef(p.oid)) || ' ' || p.proname
          FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace
            AND (p.proname LIKE 'playbook%' OR p.proname LIKE '%playbook%' OR p.proname LIKE 'company_%' OR p.proname = 'add_interaction_type')
          UNION ALL
          SELECT 'view ' || md5(pg_get_viewdef('playbooks_live'::regclass))
        ) s;
        """
    )


def test_it_applies_to_a_fresh_database_and_a_second_run_changes_nothing(pg_dsn):
    pg = pg_support.PgClient(pg_dsn)
    before = _schema(pg)
    assert "col playbooks.state" in before and "col playbooks.archived_at" in before
    assert "paused_version_id" not in before and "archived_state" not in before
    # The chain from 066 on, run again: 066 alone would put back its own playbook_set_meta/overview, which a
    # later migration (076) replaced.
    for path in [UP, *(MIGRATIONS / name for name in pg_support.SCHEMA_FILES[pg_support.SCHEMA_FILES.index(UP.name) + 1:])]:
        second = pg_support.psql_file(pg_dsn, path)
        assert second.returncode == 0, second.stderr
    assert _schema(pg) == before


def test_full_reset_statements_build_the_same_schema_as_the_migration(pg_dsn, pg_empty_dsn, tmp_path):
    reset = (ROOT / "full_reset.sql").read_text(encoding="utf-8")
    tables_from = reset.index("CREATE TABLE IF NOT EXISTS playbooks (")
    tables_to = reset.index("PRIMARY KEY (company_id, type_key)\n);", tables_from) + len("PRIMARY KEY (company_id, type_key)\n);")
    tail_from = reset.index("-- Migration 066_playbooks_v2")
    tail_to = reset.index("-- DONE!", tail_from)
    script = tmp_path / "full_reset_playbooks.sql"
    script.write_text(reset[tables_from:tables_to] + "\n" + reset[tail_from:tail_to], encoding="utf-8")
    applied = pg_support.psql_file(pg_empty_dsn, script)
    assert applied.returncode == 0, applied.stderr
    assert _schema(pg_support.PgClient(pg_empty_dsn)) == _schema(pg_support.PgClient(pg_dsn))


def test_a_database_with_the_old_066_to_069_is_upgraded_in_place(pg_cluster):
    name = pg_cluster.create_database()
    dsn = pg_cluster.dsn_for(name)
    try:
        for path in (MIGRATIONS / "040_company_playbooks.sql", MIGRATIONS / "055_playbook_goal.sql", LEGACY):
            applied = pg_support.psql_file(dsn, path)
            assert applied.returncode == 0, applied.stderr
        pg = pg_support.PgClient(dsn)
        pg.sql(
            f"""
            INSERT INTO playbooks (id, company_id, sales_motion_key, active_version_id, paused_version_id, archived_at, archived_state) VALUES
              ('a0000000-0000-0000-0000-00000000000a', '{CO}', 'live',      'b0000000-0000-0000-0000-00000000000a', NULL, NULL, NULL),
              ('a0000000-0000-0000-0000-00000000000b', '{CO}', 'paused',    NULL, 'b0000000-0000-0000-0000-00000000000b', NULL, NULL),
              ('a0000000-0000-0000-0000-00000000000c', '{CO}', 'del_live',  NULL, 'b0000000-0000-0000-0000-00000000000c', now(), 'published'),
              ('a0000000-0000-0000-0000-00000000000d', '{CO}', 'del_pause', NULL, 'b0000000-0000-0000-0000-00000000000d', now(), 'paused'),
              ('a0000000-0000-0000-0000-00000000000e', '{CO}', 'del_empty', NULL, NULL, now(), 'draft'),
              ('a0000000-0000-0000-0000-00000000000f', '{CO}', 'draft',     NULL, NULL, NULL, NULL);
            INSERT INTO playbook_versions (id, playbook_id, status) VALUES
              ('b0000000-0000-0000-0000-00000000000a', 'a0000000-0000-0000-0000-00000000000a', 'published'),
              ('b0000000-0000-0000-0000-00000000000b', 'a0000000-0000-0000-0000-00000000000b', 'published'),
              ('b0000000-0000-0000-0000-00000000000c', 'a0000000-0000-0000-0000-00000000000c', 'published'),
              ('b0000000-0000-0000-0000-00000000000d', 'a0000000-0000-0000-0000-00000000000d', 'published'),
              ('b0000000-0000-0000-0000-00000000000f', 'a0000000-0000-0000-0000-00000000000f', 'draft');
            UPDATE playbook_versions SET updated_at = '2026-01-02T03:04:05Z';
            """
        )
        stamped = pg.sql("SELECT updated_at::text FROM playbook_versions LIMIT 1")
        for run in (1, 2):  # the second run is the idempotency check
            applied = pg_support.psql_file(dsn, UP)
            assert applied.returncode == 0, applied.stderr
            rows = pg.sql(
                "SELECT sales_motion_key || ':' || state || ':' || (active_version_id IS NOT NULL)::text || ':' "
                "|| (archived_at IS NOT NULL)::text FROM playbooks ORDER BY 1"
            ).split("\n")
            assert rows == [
                "del_empty:active:false:true",
                "del_live:active:true:true",  # restore brings it back live
                "del_pause:paused:true:true",  # restore brings it back paused
                "draft:active:false:false",
                "live:active:true:false",
                "paused:paused:true:false",
            ], f"run {run}"
            assert pg.sql("SELECT string_agg(column_name, ',' ORDER BY column_name) FROM information_schema.columns "
                          "WHERE table_name = 'playbooks' AND column_name IN ('paused_version_id', 'archived_state')") == ""
            assert pg.sql("SELECT updated_at::text FROM playbook_versions LIMIT 1") == stamped  # never re-stamped
        listed = pg.sql(f"SELECT string_agg(sales_motion_key || ':' || motion_status, ' ' ORDER BY sales_motion_key) FROM list_playbook_motions('{CO}')")
        assert listed == "draft:draft live:published paused:paused"
        assert pg.sql("SELECT string_agg(sales_motion_key, ' ' ORDER BY sales_motion_key) FROM playbooks_live") == "live"
        # and the new functions work on the migrated data: restoring a deleted-while-published type brings it back live
        assert pg.rpc("playbook_set_state", {"p_company": CO, "p_motion": "del_live", "p_action": "restore"}).execute().data == "restore"
        assert pg.sql("SELECT string_agg(sales_motion_key, ' ' ORDER BY sales_motion_key) FROM playbooks_live") == "del_live live"
        assert pg.rpc("playbook_set_state", {"p_company": CO, "p_motion": "del_pause", "p_action": "restore"}).execute().data == "restore"
        assert pg.sql("SELECT string_agg(sales_motion_key, ' ' ORDER BY sales_motion_key) FROM playbooks_live") == "del_live live"
        assert "del_pause:paused" in pg.sql(f"SELECT string_agg(sales_motion_key || ':' || motion_status, ' ') FROM list_playbook_motions('{CO}')")
    finally:
        pg_cluster.drop_database(name)


def test_the_down_migration_runs_on_top_of_the_up_and_the_up_runs_again(pg_dsn):
    pg = pg_support.PgClient(pg_dsn)
    pg.sql(
        f"""
        INSERT INTO playbooks (id, company_id, sales_motion_key, active_version_id, state)
        VALUES ('a0000000-0000-0000-0000-00000000000a', '{CO}', 'discovery', 'b0000000-0000-0000-0000-00000000000a', 'paused');
        INSERT INTO playbook_versions (id, playbook_id, status) VALUES
          ('b0000000-0000-0000-0000-00000000000a', 'a0000000-0000-0000-0000-00000000000a', 'published');
        """
    )
    down = pg_support.psql_file(pg_dsn, DOWN)
    assert down.returncode == 0, down.stderr
    columns = pg.sql("SELECT string_agg(column_name, ',' ORDER BY column_name) FROM information_schema.columns "
                     "WHERE table_name IN ('playbooks', 'playbook_versions') AND column_name IN "
                     "('state', 'archived_at', 'label', 'applies_to', 'updated_at', 'qualification')")
    assert columns == ""
    assert pg.sql("SELECT count(*) FROM pg_proc WHERE proname LIKE 'playbook\\_%'") == "0"
    assert pg.sql("SELECT to_regclass('company_sales_knowledge') IS NULL AND to_regclass('playbooks_live') IS NULL") == "t"
    # a paused playbook is live again, through the 040 functions
    assert pg.sql(f"SELECT sales_motion_key || ':' || motion_status FROM list_playbook_motions('{CO}')") == "discovery:published"
    up = pg_support.psql_file(pg_dsn, UP)
    assert up.returncode == 0, up.stderr


# --- PostgreSQL: the view and the error convention ------------------------------------------------


def test_playbooks_live_is_active_published_and_not_deleted(pg):
    def rpc(name, **params):
        return pg.rpc(name, {f"p_{key}": value for key, value in params.items()}).execute().data

    def live() -> str:
        return pg.sql("SELECT COALESCE(string_agg(sales_motion_key, ' ' ORDER BY sales_motion_key), '') FROM playbooks_live")

    step = [{"step_id": "a", "label": "A", "criterion": "x"}]
    for key in ("one", "two", "three"):
        pg.rpc("playbook_save_draft", {"p_company": CO, "p_motion": key, "p_steps": step, "p_entries": [], "p_qualification": None,
                                       "p_source_id": None, "p_base_updated_at": None}).execute()
    assert live() == ""  # drafts apply to nothing
    for key in ("one", "two", "three"):
        assert pg.rpc("publish_playbook_motion", {"p_company": CO, "p_motion": key}).execute().data.startswith("published:")
    assert live() == "one three two"
    rpc("playbook_set_state", company=CO, motion="one", action="pause")
    assert live() == "three two"
    rpc("playbook_set_state", company=CO, motion="two", action="archive")
    assert live() == "three"
    rpc("playbook_set_state", company=CO, motion="one", action="resume")
    rpc("playbook_set_state", company=CO, motion="two", action="restore")
    assert live() == "one three two"
    # the columns the readers use
    assert pg.sql("SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name = 'playbooks_live'") \
        == "playbook_id,company_id,sales_motion_key,version_id"


def test_business_outcomes_are_raised_with_the_code_as_the_message(pg):
    for call, params, code in (
        ("publish_playbook_motion", {"p_company": CO, "p_motion": "nothing"}, "not_a_draft"),
        ("playbook_set_state", {"p_company": CO, "p_motion": "nothing", "p_action": "pause"}, "not_published"),
        ("playbook_set_state", {"p_company": CO, "p_motion": "nothing", "p_action": "resume"}, "not_paused"),
        ("playbook_set_state", {"p_company": CO, "p_motion": "nothing", "p_action": "restore"}, "not_archived"),
        ("playbook_set_state", {"p_company": CO, "p_motion": "nothing", "p_action": "archive"}, "not_found"),
        ("playbook_set_state", {"p_company": CO, "p_motion": "nothing", "p_action": "explode"}, "invalid_action"),
        ("add_interaction_type", {"p_company": CO, "p_key": "  ", "p_name": "x"}, "empty_type"),
        ("company_knowledge_save", {"p_company": CO, "p_data": {}, "p_source_id": None, "p_base_updated_at": "2026-01-01T00:00:00Z"}, "stale_knowledge"),
    ):
        with pytest.raises(pg_support.RpcError) as caught:
            pg.rpc(call, params).execute()
        assert caught.value.message == code, (call, caught.value.message)


# --- PostgreSQL: the functions that predate 066 (publish, list, add a type) ------------------------


def test_a_text_draft_is_stored_and_publishing_discovery_leaves_qualification_alone(pg):
    saved = pg.sql(f"SELECT save_playbook_draft('{CO}', 'discovery', 'imp-1', 'Confirmar el problema');")
    assert saved == "ready"
    pg.sql(f"SELECT save_playbook_draft('{CO}', 'discovery', 'imp-1', 'Otro texto');")
    assert pg.sql("SELECT count(*) FROM playbook_versions;") == "1"
    assert pg.sql("SELECT active_version_id IS NULL FROM playbooks;") == "t"
    with pytest.raises(pg_support.RpcError) as missing:
        pg.rpc("publish_playbook_motion", {"p_company": CO, "p_motion": "qualification"}).execute()
    assert missing.value.message == "not_a_draft"
    published = pg.rpc("publish_playbook_motion", {"p_company": CO, "p_motion": "discovery"}).execute().data
    assert published.startswith("published:")
    activated = published.split(":", 1)[1]
    assert pg.sql("SELECT active_version_id::text FROM playbooks WHERE sales_motion_key = 'discovery';") == activated
    assert pg.sql(f"SELECT sales_motion_key || ':' || motion_status FROM list_playbook_motions('{CO}') ORDER BY 1;") == "discovery:published"
    assert pg.sql("SELECT count(*) FROM playbooks WHERE sales_motion_key = 'qualification';") == "0"
    assert pg.sql("SELECT entries->0->>'source_ref' FROM playbook_versions;") == "text:imp-1"
    assert pg.sql(f"SELECT add_interaction_type('{CO}', 'renewal', 'Renovación');") == "renewal"
    pg.sql(f"SELECT add_interaction_type('{CO}', 'renewal', 'Renovación');")
    assert pg.sql("SELECT count(*) FROM interaction_types;") == "1"
    listed = pg.sql(f"SELECT string_agg(sales_motion_key || ':' || motion_status, ' ' ORDER BY sales_motion_key) FROM list_playbook_motions('{CO}');")
    assert listed == "discovery:published renewal:missing"
    with pytest.raises(pg_support.RpcError) as none_yet:
        pg.rpc("publish_playbook_motion", {"p_company": CO, "p_motion": "renewal"}).execute()
    assert none_yet.value.message == "not_a_draft"
    pg.sql(f"SELECT save_playbook_draft('{CO}', 'renewal', 'imp-x', 'Nunca descuentes. Siempre cierra.', '[\"siempre/nunca\"]'::jsonb);")
    with pytest.raises(pg_support.RpcError) as contradicted:
        pg.rpc("publish_playbook_motion", {"p_company": CO, "p_motion": "renewal"}).execute()
    assert contradicted.value.message == "contradiction"
    assert pg.sql("SELECT active_version_id IS NULL FROM playbooks WHERE sales_motion_key = 'renewal';") == "t"


def test_two_publishes_leave_one_active_pointer_and_both_versions(pg):
    pg.sql(
        """
        INSERT INTO playbooks (id, company_id, sales_motion_key)
        VALUES ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'discovery');
        INSERT INTO playbook_versions (id, playbook_id) VALUES
          ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'),
          ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa');
        """
    )
    barrier = threading.Barrier(2)
    failures: list[str] = []

    def publish(version: str) -> None:
        barrier.wait(timeout=5)
        done = pg_support.psql(pg.dsn, f"BEGIN; SELECT publish_playbook_version('{version}'); SELECT pg_sleep(0.4); COMMIT;")
        if done.returncode != 0:
            failures.append(done.stderr)

    threads = [
        threading.Thread(target=publish, args=("cccccccc-cccc-cccc-cccc-cccccccccccc",)),
        threading.Thread(target=publish, args=("dddddddd-dddd-dddd-dddd-dddddddddddd",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not failures, failures
    active = pg.sql("SELECT active_version_id::text FROM playbooks;")
    assert active in ("cccccccc-cccc-cccc-cccc-cccccccccccc", "dddddddd-dddd-dddd-dddd-dddddddddddd")
    assert pg.sql("SELECT count(*) FROM playbook_versions WHERE status = 'published';") == "2"
