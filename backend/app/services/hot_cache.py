"""Short-lived in-process caches for lookups every request repeats.

One call's post-call burst (the memo, its hooks, the island's six requests) read the same rep's
membership ~25 times, the company's member list 6 times and the CRM field schemas 13 times in
five seconds (prod logs, 2026-11-16). Each read is a blocking Supabase round trip on the event
loop, so they added up to seconds of a stalled server. The API runs as one process, so a cache
here is shared by every request; each one is cleared by the code that changes what it holds.
"""

from __future__ import annotations

import time
from typing import Any, Hashable, Optional


class TTLCache:
    def __init__(self, ttl_s: float):
        self.ttl_s = ttl_s
        self._rows: dict[Hashable, tuple[float, Any]] = {}

    def get(self, key: Hashable) -> Optional[Any]:
        row = self._rows.get(key)
        if row is None:
            return None
        if row[0] <= time.monotonic():
            self._rows.pop(key, None)
            return None
        return row[1]

    def put(self, key: Hashable, value: Any) -> None:
        self._rows[key] = (time.monotonic() + self.ttl_s, value)

    def forget(self, key: Optional[Hashable] = None) -> None:
        if key is None:
            self._rows.clear()
        else:
            self._rows.pop(key, None)


# A rep's active membership (user_id -> Membership) and a company's member list (company_id ->
# rows). Short, because a change made outside this process (the Supabase dashboard) only shows
# once they expire; every change made here clears them at once (forget_members).
MEMBERSHIPS = TTLCache(15)
MEMBER_LISTS = TTLCache(15)
# A connection's CRM field schema as each provider parses it ((connection_id, object_type) ->
# value). Its stored copy in crm_schemas lives 24 h; a refresh here replaces this one too.
SCHEMAS = TTLCache(600)


def forget_members() -> None:
    """Who belongs to which company changed: the next read goes to the database."""
    MEMBERSHIPS.forget()
    MEMBER_LISTS.forget()


def changes_members(fn):
    """For a function that writes company_members: the member caches are cleared after it runs,
    whatever it returns or raises."""
    import functools
    import inspect

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def run_async(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            finally:
                forget_members()

        return run_async

    @functools.wraps(fn)
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        finally:
            forget_members()

    return run
