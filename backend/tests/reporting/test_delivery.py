"""F13 delivery: one report per period, and a failed email keeps the bell."""

import os
from datetime import datetime, timezone

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-delivery-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-delivery-32")

import shutil
import socket
import subprocess
import tempfile
import threading
from pathlib import Path

import pytest

from app.services.reporting.delivery import claim_report_statement, deliver_report, period_bounds, send_report_email
from app.services.reporting.resend_sender import ResendReportSender
from app.api.reports import bell_items

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "048_reports_notifications.sql"
COMPANY = "88888888-8888-8888-8888-888888888888"
USER = "99999999-9999-9999-9999-999999999999"


class Sender:
    def __init__(self, fail: Exception | None = None):
        self.sent = []
        self.remote = {}
        self.fail = fail

    def send(self, key: str) -> None:
        if self.fail:
            error = self.fail
            self.fail = None
            if isinstance(error, TimeoutError):
                self.remote[key] = "msg-1"
            raise error
        self.sent.append(key)
        self.remote[key] = "msg-1"

    def reconcile(self, key: str):
        return self.remote.get(key)


def test_the_bell_counts_only_unread_rows_for_this_user():
    rows = [
        {"id": "n1", "report_id": "r1", "user_id": USER, "read_at": None},
        {"id": "n2", "report_id": "r2", "user_id": USER, "read_at": "2026-09-22T10:00:00Z"},
        {"id": "n3", "report_id": "r3", "user_id": "other", "read_at": None},
    ]
    bell = bell_items(rows, USER)
    assert bell["unread"] == 1
    assert bell["items"] == [{"id": "n1", "report_id": "r1"}]


def test_dst_is_one_period_and_a_failed_email_keeps_the_notification():
    before = datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc)
    after = datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc)
    nxt = datetime(2026, 3, 30, 0, 30, tzinfo=timezone.utc)
    assert period_bounds(before, "Europe/Madrid")[0] == period_bounds(after, "Europe/Madrid")[0]
    assert period_bounds(nxt, "Europe/Madrid")[0] != period_bounds(before, "Europe/Madrid")[0]
    report = {"id": "report-1", "revision": 1}
    sender = Sender(fail=RuntimeError("resend"))
    failed = deliver_report(report=report, channel="email", existing=None, sender=sender, allowed=True)
    assert failed["delivery_status"] == "failed"
    assert failed["notification"]["kept"] is True
    assert failed["idempotency_key"] == "report-1:r1:email"
    assert sender.sent == []
    denied = deliver_report(report=report, channel="email", existing=None, sender=sender, allowed=False)
    assert denied["delivery_status"] == "skipped"
    assert sender.sent == []


class FakeResendClient:
    def __init__(self):
        self.calls: list[dict] = []

    async def send_email(self, to, subject, html, from_email=None, idempotency_key=None):
        self.calls.append(
            {"to": to, "subject": subject, "html": html, "from_email": from_email, "idempotency_key": idempotency_key}
        )
        return {"id": "msg-resend-1"}


def test_send_report_email_passes_idempotency_key_into_sender_send_once():
    report = {"id": "report-1", "revision": 1}
    sender = Sender()
    first = send_report_email(report, sender)
    assert first["delivery_status"] == "sent"
    assert sender.sent == ["report-1:r1:email"]
    second = send_report_email(report, sender, existing=first)
    assert second["replayed"] is True
    assert sender.sent == ["report-1:r1:email"]


def test_resend_adapter_passes_idempotency_key_and_replay_skips_send():
    report = {"id": "report-1", "revision": 1}
    fake = FakeResendClient()
    sender = ResendReportSender(
        fake,
        to="rep@example.com",
        subject="Tu resumen",
        html="<p>Actividad del día</p>",
    )
    first = deliver_report(report=report, channel="email", existing=None, sender=sender, allowed=True)
    assert first["delivery_status"] == "sent"
    assert len(fake.calls) == 1
    assert fake.calls[0]["idempotency_key"] == "report-1:r1:email"
    assert "report-1:r1:email" not in fake.calls[0]["html"]
    second = deliver_report(report=report, channel="email", existing=first, sender=sender, allowed=True)
    assert second["replayed"] is True
    assert second["delivery_status"] == "sent"
    assert len(fake.calls) == 1


def test_a_timeout_is_reconciled_instead_of_sending_again():
    report = {"id": "report-1", "revision": 1}
    sender = Sender(fail=TimeoutError("resend"))
    uncertain = deliver_report(report=report, channel="email", existing=None, sender=sender, allowed=True)
    assert uncertain["delivery_status"] == "uncertain"
    again = deliver_report(report=report, channel="email", existing=uncertain, sender=sender, allowed=True)
    assert again["replayed"] is True
    assert again["delivery_status"] == "sent"
    assert sender.sent == []


def _pg_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    return env


def _psql(dsn: str, sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True, text=True, timeout=20, check=False, env=_pg_env(),
    )


def test_two_workers_insert_one_report_for_the_period():
    initdb = shutil.which("initdb")
    postgres = shutil.which("postgres")
    if not initdb or not postgres or not shutil.which("psql"):
        pytest.skip("No hay PostgreSQL aislado")
    datadir = Path(tempfile.mkdtemp(prefix="vocify-report-"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    init = subprocess.run(
        [initdb, "-D", str(datadir), "--auth=trust", "--no-instructions", "-U", "vocify", "--encoding=UTF8", "--locale=C"],
        capture_output=True, text=True, check=False, env=_pg_env(),
    )
    if init.returncode != 0:
        shutil.rmtree(datadir, ignore_errors=True)
        pytest.skip(init.stderr[-300:])
    log_path = datadir / "pg.log"
    proc = subprocess.Popen(
        [postgres, "-D", str(datadir), "-p", str(port), "-h", "127.0.0.1", "-k", str(datadir)],
        stdout=log_path.open("w"), stderr=subprocess.STDOUT, env=_pg_env(),
    )
    dsn = f"postgresql://vocify@127.0.0.1:{port}/postgres"
    try:
        for _ in range(40):
            if proc.poll() is not None:
                pytest.skip((log_path.read_text() if log_path.exists() else "")[-300:])
            if _psql(dsn, "SELECT 1;").returncode == 0:
                break
            import time
            time.sleep(0.15)
        applied = subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(MIGRATION)],
            capture_output=True, text=True, timeout=20, check=False, env=_pg_env(),
        )
        assert applied.returncode == 0, applied.stderr
        start, _end = period_bounds(datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc), "Europe/Madrid")
        statement = claim_report_statement(
            company_id=COMPANY,
            user_id=USER,
            scope="self",
            period_start=start.isoformat(),
            report_type="daily",
        )
        errors = []

        def write():
            result = _psql(dsn, statement)
            if result.returncode != 0:
                errors.append(result.stderr)

        threads = [threading.Thread(target=write) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        counted = _psql(dsn, "SELECT count(*) FROM reports;")
        assert "1" in counted.stdout
    finally:
        proc.terminate()
        proc.wait(timeout=8)
        shutil.rmtree(datadir, ignore_errors=True)
