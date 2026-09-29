"""Small in-memory Supabase for tool tests. Supports the query shapes the Ask tools use."""

from __future__ import annotations


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, tables, name):
        self._tables = tables
        self._name = name
        self._eq = []
        self._in = []
        self._gte = []
        self._or = None
        self._delete = False
        self._update = None
        self._desc = False
        self._order = None
        self._limit = None
        self._range = None

    def select(self, *_a, **_k):
        return self

    def delete(self):
        self._delete = True
        return self

    def update(self, payload):
        self._update = payload
        return self

    def eq(self, column, value):
        self._eq.append((column, value))
        return self

    def in_(self, column, values):
        self._in.append((column, {str(v) for v in values}))
        return self

    def gte(self, column, value):
        self._gte.append((column, str(value)))
        return self

    def or_(self, expression):
        self._or = [part.split(".", 2) for part in expression.split(",")]
        return self

    def order(self, column, desc=False):
        self._order, self._desc = column, desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        if self._delete:
            keep = [
                r for r in self._tables.get(self._name, [])
                if not all(r.get(c) == v for c, v in self._eq)
            ]
            self._tables[self._name] = keep
            return _Result([])
        if self._update is not None:
            hit = [r for r in self._tables.get(self._name, []) if all(r.get(c) == v for c, v in self._eq)]
            for row in hit:
                row.update(self._update)
            return _Result([dict(r) for r in hit])
        rows = [dict(r) for r in self._tables.get(self._name, [])]
        for column, value in self._eq:
            rows = [r for r in rows if r.get(column) == value]
        for column, allowed in self._in:
            rows = [r for r in rows if str(r.get(column)) in allowed]
        for column, floor in self._gte:
            rows = [r for r in rows if str(r.get(column) or "") >= floor]
        if self._or:
            def keep(row):
                for column, op, value in self._or:
                    if op == "eq" and str(row.get(column)) == value:
                        return True
                    if op == "is" and value == "null" and row.get(column) is None:
                        return True
                return False

            rows = [r for r in rows if keep(r)]
        if self._order:
            rows.sort(key=lambda r: str(r.get(self._order) or ""), reverse=self._desc)
        if self._range is not None:
            rows = rows[self._range[0] : self._range[1] + 1]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(rows)


class FakeSupabase:
    def __init__(self, **tables):
        self.tables = tables

    def table(self, name):
        return _Query(self.tables, name)


class FakeCompanyService:
    def __init__(self, member_ids):
        self.member_ids = member_ids

    def list_members(self, company_id):
        return [
            {"user_id": uid, "status": "active", "full_name": f"Rep {uid}", "email": f"{uid}@x.test"}
            for uid in self.member_ids
        ]


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class FakeHubSpotClient:
    """Evaluates the search filters the analytics tools send, over in-memory records.

    Records are plain dicts of HubSpot properties, keyed by object type ("calls", "deals", ...).
    `total` is exact, like the real Search API; `results` honour `limit`, `after` and `sorts`.
    `schema` maps object type -> property definitions, as /crm/v3/properties/{type} returns them.
    """

    def __init__(self, calls=(), deals=(), owners=(), fail_with=None, records=None, schema=None, pipelines=None, dispositions=None):
        self.records = {"calls": list(calls), "deals": list(deals), **{k: list(v) for k, v in (records or {}).items()}}
        self.owners = list(owners)
        self.schema = schema or {}
        self.pipelines = pipelines or []
        self.dispositions = dispositions
        self.requests: list[tuple[str, dict]] = []
        self.fail_with = fail_with

    @staticmethod
    def _match(props, flt):
        name, op, value = flt["propertyName"], flt["operator"], flt.get("value")
        have = props.get(name)
        if op == "HAS_PROPERTY":
            return have not in (None, "")
        if op == "NOT_HAS_PROPERTY":
            return have in (None, "")
        if op in ("IN", "NOT_IN"):
            inside = str(have).lower() in {str(v).lower() for v in flt.get("values") or []}
            return inside if op == "IN" else not inside
        if have in (None, ""):
            return False
        a, b = _num(have), _num(value)
        if op in ("GTE", "GT", "LT", "LTE") and a is not None and b is not None:
            return {"GTE": a >= b, "GT": a > b, "LT": a < b, "LTE": a <= b}[op]
        if op == "EQ":
            return str(have).lower() == str(value).lower()
        if op == "NEQ":
            return str(have).lower() != str(value).lower()
        if op == "CONTAINS_TOKEN":
            return str(value).lower() in str(have).lower()
        return False

    async def post(self, endpoint, data=None):
        self.requests.append((endpoint, data or {}))
        if self.fail_with:
            raise self.fail_with
        object_type = endpoint.split("/objects/")[1].split("/")[0]
        groups = (data or {}).get("filterGroups") or [{"filters": []}]
        matched = [
            r for r in self.records.get(object_type, [])
            if any(all(self._match(r, f) for f in g["filters"]) for g in groups)
        ]
        for sort in reversed((data or {}).get("sorts") or []):
            key = sort["propertyName"]
            matched.sort(key=lambda r: (_num(r.get(key)) is None, _num(r.get(key)) or 0), reverse=sort.get("direction") == "DESCENDING")
        limit = int((data or {}).get("limit") or 10)
        start = int((data or {}).get("after") or 0)
        page = matched[start : start + limit]
        body = {"total": len(matched), "results": [{"id": str(r.get("id", i)), "properties": r} for i, r in enumerate(page, start)]}
        if start + limit < len(matched):
            body["paging"] = {"next": {"after": str(start + limit)}}
        return body

    async def get(self, endpoint, params=None):
        self.requests.append((endpoint, params or {}))
        if self.fail_with:
            raise self.fail_with
        if endpoint == "/crm/v3/owners":
            return {"results": self.owners}
        if endpoint.startswith("/crm/v3/properties/"):
            return {"results": self.schema.get(endpoint.rsplit("/", 1)[1], [])}
        if endpoint == "/crm/v3/pipelines/deals":
            return {"results": self.pipelines}
        if endpoint == "/calling/v1/dispositions":
            if self.dispositions is None:
                raise RuntimeError("404")
            return self.dispositions
        return None
