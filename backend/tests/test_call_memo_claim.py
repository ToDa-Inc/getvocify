"""One memo per Vocify call, whichever arrives first: the desktop's live transcript or Twilio's recording."""

from app.services.telephony.call_memo_claim import claim_call_memo, find_user_call


class _Query:
    def __init__(self, table, op, values=None):
        self.table, self.op, self.values, self.filters = table, op, values, []

    def select(self, *_):
        return self

    def eq(self, column, value):
        self.filters.append(lambda row: row.get(column) == value)
        return self

    def is_(self, column, value):
        assert value == "null"
        self.filters.append(lambda row: row.get(column) is None)
        return self

    def limit(self, _):
        return self

    def execute(self):
        rows = [row for row in self.table.rows if all(f(row) for f in self.filters)]
        if self.op == "update":
            for row in rows:
                row.update(self.values)
        if self.op == "delete":
            self.table.rows = [row for row in self.table.rows if row not in rows]
        return type("Result", (), {"data": [dict(row) for row in rows]})()


class _Table:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_):
        return _Query(self, "select")

    def update(self, values):
        return _Query(self, "update", values)

    def delete(self):
        return _Query(self, "delete")


class FakeDb:
    def __init__(self, **tables):
        self.tables = {name: _Table(rows) for name, rows in tables.items()}

    def table(self, name):
        return self.tables[name]


def db(memo_id=None):
    return FakeDb(
        outbound_calls=[{"carrier_call_id": "CA1", "user_id": "rep-1", "memo_id": memo_id}],
        memos=[{"id": "live-memo"}, {"id": "recording-memo"}],
    )


def test_the_first_memo_claims_the_call():
    fake = db()
    assert claim_call_memo(fake, "CA1", "live-memo") == "live-memo"
    assert fake.tables["outbound_calls"].rows[0]["memo_id"] == "live-memo"


def test_the_second_memo_loses_and_is_removed():
    fake = db()
    claim_call_memo(fake, "CA1", "live-memo")
    assert claim_call_memo(fake, "CA1", "recording-memo") == "live-memo"
    assert [m["id"] for m in fake.tables["memos"].rows] == ["live-memo"]
    assert fake.tables["outbound_calls"].rows[0]["memo_id"] == "live-memo"


def test_a_call_is_only_found_for_the_rep_who_placed_it():
    fake = db()
    assert find_user_call(fake, "rep-1", "CA1")["carrier_call_id"] == "CA1"
    assert find_user_call(fake, "rep-2", "CA1") is None
    assert find_user_call(fake, "rep-1", "CA9") is None
