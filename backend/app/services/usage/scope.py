"""Who a paid call is for. Set once at an entry point; every vendor call below it inherits it."""

from __future__ import annotations

import functools
import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Iterator, Optional


@dataclass(frozen=True)
class UsageScope:
    """Who a paid call is for: which step (`purpose`) of which interaction (`memo_id`)."""

    purpose: str = "unknown"
    user_id: Optional[str] = None
    company_id: Optional[str] = None
    memo_id: Optional[str] = None
    capture_id: Optional[str] = None


_SCOPE: ContextVar[Optional[UsageScope]] = ContextVar("usage_scope", default=None)


def current_scope() -> UsageScope:
    return _SCOPE.get() or UsageScope()


@contextmanager
def usage_scope(
    purpose: Optional[str] = None,
    *,
    user_id: Optional[str] = None,
    company_id: Optional[str] = None,
    memo_id: Optional[str] = None,
    capture_id: Optional[str] = None,
) -> Iterator[UsageScope]:
    """Nest freely: inner values override, anything left out is inherited."""
    parent = _SCOPE.get()
    base = parent or UsageScope()
    changes = {
        k: str(v)
        for k, v in (
            ("purpose", purpose),
            ("user_id", user_id),
            ("company_id", company_id),
            ("memo_id", memo_id),
            ("capture_id", capture_id),
        )
        if v
    }
    scope = replace(base, **changes)
    token = _SCOPE.set(scope)
    try:
        yield scope
    finally:
        _SCOPE.reset(token)


def scoped(purpose: str):
    """Decorator form of `usage_scope` for async entry points: takes memo_id / user_id / company_id
    from the call's arguments when the function has parameters of those names."""

    def wrap(fn):
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        async def inner(*args, **kwargs):
            bound = sig.bind_partial(*args, **kwargs).arguments
            ids = {k: bound.get(k) for k in ("user_id", "company_id", "memo_id")}
            with usage_scope(purpose, **ids):
                return await fn(*args, **kwargs)

        return inner

    return wrap
