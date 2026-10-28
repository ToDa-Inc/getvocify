"""The current live brain (evals.copilot.live_brain_run), with every call read as of its own day (see history.py).
Always on production's path: Together direct with reasoning none, OpenRouter only as its backup.

    cd backend && PATH=$HOME/.railway/bin:$PATH python -m evals.strategic.run_current --no-judge --only 816ba4f7 --json a.json
"""

import json
import sys

from evals.copilot import live_brain_run
from evals.strategic.history import install


def main() -> int:
    # Production's COPILOT_* first: the app reads its settings once, at its first import, and without the direct
    # provider it would silently go to OpenRouter alone.
    live_brain_run.load_production_provider()
    sys.path.insert(0, str(live_brain_run.HERE.parents[1]))
    from app.api import copilot as copilot_api
    from app.services.copilot.suggest import live_direct

    direct = live_direct()
    if not direct or "together" not in direct[0]:
        sys.exit("the direct provider (Together) is not configured in this process: refusing to run")
    install(copilot_api, [json.loads(p.read_text(encoding="utf-8")) for p in live_brain_run.CALLS.glob("*.local.json")])
    return live_brain_run.main()


if __name__ == "__main__":
    sys.exit(main())
