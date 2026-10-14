"""No new Supabase query runs straight on the event loop from an `async def` route.

supabase-py is synchronous: `.execute()` inside an `async def` handler holds the one event loop every
request shares until Supabase answers. On 2026-10-14 such calls froze production for up to 186 s and a
call's memo was lost. Linters cannot see it (ruff's ASYNC rules pass on that exact code), so this counts
them. The counts below are what is left; they may only go down.

To fix one: make the handler a plain `def` when it awaits nothing (FastAPI runs it in its threadpool),
or wrap the query in `await run_in_threadpool(...)`. When a count drops, lower it here.
"""

import ast
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "app" / "api"
ROUTE_METHODS = {"get", "post", "put", "patch", "delete"}

ALLOWED = {
    "admin.py": 20,
    "auth.py": 8,
    "calendar.py": 1,
    "company.py": 1,
    "crm.py": 18,
    "crm_pipedrive.py": 8,
    "crm_salesforce.py": 8,
    "followup.py": 8,
    "hubspot_recordings.py": 1,
    "memos.py": 22,
    "playbook_rules.py": 1,
    "playbooks.py": 1,
    "reports.py": 4,
    "stripe_webhooks.py": 1,
    "today.py": 7,
    "webhooks.py": 5,
}


def _is_route(fn: ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(d, ast.Call) and getattr(d.func, "attr", "") in ROUTE_METHODS for d in fn.decorator_list
    )


def _executes_on_the_loop(fn: ast.AsyncFunctionDef) -> list[int]:
    """`.execute()` lines in the handler's own body (not in nested functions or lambdas run elsewhere)."""
    lines, stack = [], list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and not node.args
        ):
            lines.append(node.lineno)
        stack.extend(ast.iter_child_nodes(node))
    return sorted(lines)


def _found() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(API.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and _is_route(node):
                for line in _executes_on_the_loop(node):
                    found.setdefault(path.relative_to(API).as_posix(), []).append(f"{node.name}:{line}")
    return found


def test_no_new_supabase_query_on_the_event_loop():
    over = {
        name: sites
        for name, sites in _found().items()
        if len(sites) > ALLOWED.get(name, 0)
    }
    assert not over, (
        "New synchronous Supabase queries inside `async def` routes (they block every request): "
        f"{over}. Make the handler `def`, or use `await run_in_threadpool(...)`."
    )
