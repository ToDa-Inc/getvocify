"""Ask turns stay idempotent, and a changed contact does not receive the old write."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-ask-32bytes+")

import pytest

from app.services.crm_copilot.web_sessions import (
    TurnConflict,
    UncertainOperation,
    accept_turn,
    confirm_operation,
)


def test_an_unavailable_crm_is_not_an_empty_answer():
    from app.services.crm_copilot.web_sessions import payload_from_turn

    plain = payload_from_turn("Marina queda el jueves.", {})
    assert "envelope" not in plain
    blocked = payload_from_turn("No pude leer el CRM.", {"crm_coverage": "unavailable"})
    assert blocked["envelope"]["coverage"] == "unavailable"
    assert blocked["envelope"]["items"] == []
    assert blocked["text"] == "No pude leer el CRM."
    confirm = payload_from_turn(
        "¿Creo la nota?",
        {"copilot": {"pending_id": "op-1", "revision": 3, "pending_args": {"contact_id": "contact-a"}}},
        kind="confirm",
    )
    assert confirm["confirmation"] == {
        "operation_id": "op-1",
        "revision": 3,
        "contact_id": "contact-a",
    }
    missing = payload_from_turn(
        "¿Sigo?",
        {"copilot": {"pending_id": "op-1", "pending_args": {}}},
        kind="confirm",
    )
    assert "confirmation" not in missing


def test_a_tool_call_line_is_not_part_of_the_answer():
    from app.services.crm_copilot.web_sessions import public_answer

    assert public_answer("Marina queda el jueves.") == "Marina queda el jueves."
    assert public_answer("Marina queda el jueves.\ntool_call get_contact id=abc") == "Marina queda el jueves."


def test_repeating_a_client_turn_returns_the_same_turn():
    store = {}
    first = accept_turn(store, conversation_id="conv-1", client_turn_id="web-2", text="¿Qué sigue?")
    second = accept_turn(store, conversation_id="conv-1", client_turn_id="web-2", text="otra pregunta")
    assert first["turn_id"] == second["turn_id"]
    assert first["status"] == "pending"
    assert second["replayed"] is True
    assert second["text"] == "¿Qué sigue?"
    assert len(store) == 1


def test_changing_contact_before_confirm_writes_nothing():
    operation = {
        "operation_id": "op-1",
        "revision": 3,
        "contact_id": "contact-a",
        "applied": False,
        "status": "proposed",
    }
    with pytest.raises(TurnConflict):
        confirm_operation(operation, operation_id="op-1", revision=3, contact_id="contact-b")
    assert operation["applied"] is False


def test_an_uncertain_remote_result_is_not_retried_blindly():
    operation = {
        "operation_id": "op-1",
        "revision": 3,
        "contact_id": "contact-a",
        "applied": False,
        "status": "uncertain",
    }
    with pytest.raises(UncertainOperation):
        confirm_operation(operation, operation_id="op-1", revision=3, contact_id="contact-a")
    assert operation["applied"] is False


def test_a_repeated_ask_turn_is_one_row_and_another_user_is_separate():
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
    datadir = Path(tempfile.mkdtemp(prefix="vocify-ask-"))
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
    user = "11111111-1111-1111-1111-111111111111"
    company = "22222222-2222-2222-2222-222222222222"
    other = "33333333-3333-3333-3333-333333333333"

    def psql(sql: str):
        return subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql],
            capture_output=True, text=True, env=env, check=False,
        )

    try:
        for _ in range(40):
            if psql("SELECT 1;").returncode == 0:
                break
        migration = Path(__file__).resolve().parents[2] / "migrations" / "041_copilot_web_sessions.sql"
        applied = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(migration)],
            capture_output=True, text=True, env=env, check=False,
        )
        assert applied.returncode == 0, applied.stderr
        first = psql(
            "SELECT turn_id || '|' || body || '|' || replayed::text FROM save_ask_turn("
            f"'{company}', '{user}', 'conv-1', 'web-2', '¿Qué sigue?');"
        )
        assert first.returncode == 0, first.stderr
        second = psql(
            "SELECT turn_id || '|' || body || '|' || replayed::text FROM save_ask_turn("
            f"'{company}', '{user}', 'conv-1', 'web-2', 'otra pregunta');"
        )
        assert second.returncode == 0, second.stderr
        first_id, first_body, first_replayed = first.stdout.strip().split("|")
        second_id, second_body, second_replayed = second.stdout.strip().split("|")
        assert first_id == second_id
        assert first_body == second_body == "¿Qué sigue?"
        assert first_replayed == "false"
        assert second_replayed == "true"
        assert psql("SELECT count(*) FROM copilot_web_turns;").stdout.strip() == "1"
        stranger = psql(
            f"SELECT turn_id FROM save_ask_turn('{company}', '{other}', 'conv-1', 'web-2', 'privado');"
        )
        assert stranger.stdout.strip() != first_id
        assert psql("SELECT count(*) FROM copilot_web_turns;").stdout.strip() == "2"
        assert psql(
            f"SELECT company_id::text FROM copilot_web_turns WHERE user_id = '{user}';"
        ).stdout.strip() == company
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)
