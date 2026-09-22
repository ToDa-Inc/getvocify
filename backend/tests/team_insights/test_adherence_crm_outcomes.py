"""F15: GET /team/adherence sets crm_coverage and win counts from observations."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-team-crm-32")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-team-crm-32")

from datetime import datetime, timezone

from app.services.team_insights.aggregate import load_team_adherence_inputs, team_adherence
from app.services.team_insights.outcomes import adherence_crm_outcomes

COMPANY = "co-crm-1"
USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_WEEK = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, name: str, *, fail: bool = False):
        self._store = store
        self._name = name
        self._fail = fail
        self._filters: list[tuple[str, object]] = []
        self._in_filters: list[tuple[str, list]] = []
        self._limit: int | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def in_(self, column, values):
        self._in_filters.append((column, list(values)))
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def order(self, _column: str):
        return self

    def execute(self):
        if self._fail:
            raise RuntimeError("observations read failed")
        rows = list(self._store.tables.get(self._name, []))
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self._in_filters:
            allowed = {str(v) for v in values}
            rows = [row for row in rows if str(row.get(column)) in allowed]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(rows)


class _Supabase:
    def __init__(self, tables: dict[str, list[dict]], *, fail_observations: bool = False):
        self.tables = tables
        self._fail_observations = fail_observations

    def table(self, name: str):
        return _Query(self, name, fail=self._fail_observations and name == "team_outcome_observations")


def _observation(
    *,
    connection_id: str,
    deal_id: str,
    status: str,
    observed_at: str,
    owner_user_id: str | None = None,
    attribution: str = "assigned",
) -> dict:
    return {
        "company_id": COMPANY,
        "connection_id": connection_id,
        "deal_id": deal_id,
        "status": status,
        "owner_user_id": owner_user_id,
        "attribution": attribution,
        "observed_at": observed_at,
    }


def _minimal_store(observations: list[dict] | None = None) -> _Supabase:
    tables: dict[str, list[dict]] = {
        "memos": [],
        "memo_scores": [],
        "interaction_patterns": [],
        "playbooks": [],
        "company_members": [],
        "user_profiles": [],
        "team_outcome_observations": observations if observations is not None else [],
    }
    return _Supabase(tables)


def test_no_observations_means_unavailable_not_zero():
    inputs = load_team_adherence_inputs(_minimal_store(), COMPANY)
    body = team_adherence(role="admin", **inputs)
    assert body["crm_coverage"] == "unavailable"
    assert body["won"] is None
    assert body["lost"] is None
    assert body["unresolved_wins"] == 0


def test_observation_read_failure_is_unavailable_not_zero():
    inputs = load_team_adherence_inputs(_minimal_store(), COMPANY)
    inputs["outcome_observations"] = None
    body = team_adherence(role="admin", **inputs)
    assert body["crm_coverage"] == "unavailable"
    assert body["won"] is None
    assert body["lost"] is None


def test_latest_observation_per_deal_and_partial_coverage():
    history = [
        _observation(
            connection_id="crm-A",
            deal_id="deal-1",
            status="won",
            observed_at="2026-09-20T12:00:00Z",
            owner_user_id=USER_A,
            attribution="assigned",
        ),
        _observation(
            connection_id="crm-A",
            deal_id="deal-1",
            status="open",
            observed_at="2026-09-22T12:00:00Z",
            owner_user_id=USER_A,
            attribution="assigned",
        ),
        _observation(
            connection_id="crm-A",
            deal_id="deal-2",
            status="won",
            observed_at="2026-09-21T12:00:00Z",
            owner_user_id=None,
            attribution="unresolved",
        ),
        _observation(
            connection_id="crm-A",
            deal_id="deal-3",
            status="lost",
            observed_at="2026-09-21T12:00:00Z",
            owner_user_id=USER_B,
            attribution="assigned",
        ),
    ]
    assert adherence_crm_outcomes(history) == {
        "crm_coverage": "partial",
        "won": 1,
        "lost": 1,
        "unresolved_wins": 1,
    }


def test_user_filter_counts_only_that_owner():
    history = [
        _observation(
            connection_id="crm-A",
            deal_id="deal-1",
            status="won",
            observed_at="2026-09-22T12:00:00Z",
            owner_user_id=USER_A,
            attribution="assigned",
        ),
        _observation(
            connection_id="crm-A",
            deal_id="deal-2",
            status="won",
            observed_at="2026-09-22T12:00:00Z",
            owner_user_id=USER_B,
            attribution="assigned",
        ),
        _observation(
            connection_id="crm-A",
            deal_id="deal-3",
            status="won",
            observed_at="2026-09-22T12:00:00Z",
            owner_user_id=None,
            attribution="unresolved",
        ),
    ]
    scoped = adherence_crm_outcomes(history, user_id=USER_A)
    assert scoped["crm_coverage"] == "partial"
    assert scoped["won"] == 1
    assert scoped["lost"] == 0
    assert scoped["unresolved_wins"] == 0


def test_loader_attaches_observations_for_adherence():
    store = _minimal_store(
        [
            _observation(
                connection_id="crm-A",
                deal_id="deal-9",
                status="won",
                observed_at=_WEEK.isoformat(),
                owner_user_id=USER_A,
                attribution="assigned",
            ),
        ]
    )
    inputs = load_team_adherence_inputs(store, COMPANY)
    body = team_adherence(role="admin", **inputs)
    assert body["crm_coverage"] == "partial"
    assert body["won"] == 1
    assert body["lost"] == 0
    assert body["unresolved_wins"] == 0


def test_loader_observation_failure_stays_unavailable():
    store = _Supabase(
        {
            "memos": [],
            "memo_scores": [],
            "interaction_patterns": [],
            "playbooks": [],
            "company_members": [],
            "user_profiles": [],
            "team_outcome_observations": [],
        },
        fail_observations=True,
    )
    inputs = load_team_adherence_inputs(store, COMPANY)
    body = team_adherence(role="admin", **inputs)
    assert body["crm_coverage"] == "unavailable"
    assert body["won"] is None
