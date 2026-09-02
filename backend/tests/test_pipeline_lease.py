import time
import unittest

from app.services.pipeline_lease import (
    LEASE_SECONDS,
    _LIVE,
    _guard,
    acquire_pipeline_run,
    reap_expired_leases,
    release_pipeline_run,
    reset_pipeline_leases,
)


class _Result:
    def __init__(self, data):
        self.data = data


class _HeldClient:
    """CAS miss: another run already holds the row."""

    def table(self, _name):
        return self

    def update(self, _payload):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def or_(self, *_args, **_kwargs):
        return self

    def select(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return _Result([])


class _WriteButEmptyReturningClient:
    """PostgREST PATCH + or() filter: row is updated, RETURNING is [].

    After the write, pipeline_run_id is no longer null and started_at is
    no longer older than the cutoff, so Prefer: return=representation
    re-applies the filter and comes back empty. That is not a CAS miss.
    """

    def __init__(self):
        self.row = {"pipeline_run_id": None, "pipeline_run_started_at": None}
        self._pending = None
        self._selecting = False

    def table(self, _name):
        return self

    def update(self, payload):
        self._pending = payload
        self._selecting = False
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def or_(self, *_args, **_kwargs):
        return self

    def select(self, *_args, **_kwargs):
        self._selecting = True
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._selecting:
            self._selecting = False
            return _Result([dict(self.row)])
        if self._pending is not None:
            self.row.update(self._pending)
            self._pending = None
        return _Result([])


class PipelineLeaseTests(unittest.TestCase):
    def setUp(self):
        reset_pipeline_leases()

    def tearDown(self):
        reset_pipeline_leases()

    def test_acquire_idle(self):
        run_id = acquire_pipeline_run(None, "memo-1", "extract")
        self.assertTrue(run_id)

    def test_refuse_held(self):
        first = acquire_pipeline_run(None, "memo-1", "extract")
        second = acquire_pipeline_run(None, "memo-1", "recovery")
        self.assertTrue(first)
        self.assertIsNone(second)

    def test_release_then_acquire(self):
        first = acquire_pipeline_run(None, "memo-1", "extract")
        release_pipeline_run(None, "memo-1", first)
        second = acquire_pipeline_run(None, "memo-1", "extract")
        self.assertTrue(second)
        self.assertNotEqual(first, second)

    def test_expire_allows_new_run(self):
        first = acquire_pipeline_run(None, "memo-1", "extract")
        with _guard:
            _LIVE["memo-1"] = (first, time.monotonic() - LEASE_SECONDS - 1)
        second = acquire_pipeline_run(None, "memo-1", "extract")
        self.assertTrue(second)
        self.assertNotEqual(first, second)

    def test_reap_expired(self):
        first = acquire_pipeline_run(None, "memo-1", "extract")
        with _guard:
            _LIVE["memo-1"] = (first, time.monotonic() - LEASE_SECONDS - 1)
        self.assertEqual(reap_expired_leases(), 1)
        third = acquire_pipeline_run(None, "memo-1", "recovery")
        self.assertTrue(third)

    def test_db_cas_miss_releases_in_process(self):
        run_id = acquire_pipeline_run(_HeldClient(), "memo-1", "extract")
        self.assertIsNone(run_id)
        retry = acquire_pipeline_run(None, "memo-1", "extract")
        self.assertTrue(retry)

    def test_acquire_when_update_writes_but_returning_is_empty(self):
        client = _WriteButEmptyReturningClient()
        run_id = acquire_pipeline_run(client, "memo-1", "extract")
        self.assertTrue(run_id)
        self.assertEqual(client.row.get("pipeline_run_id"), run_id)


if __name__ == "__main__":
    unittest.main()
