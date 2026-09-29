"""The Ask eval stays honest: its cases point at real tools and real ground truth."""

import json
import re
from pathlib import Path

from app.services.crm_copilot.intel_tools import INTEL_TOOL_NAMES
from evals.ask import fixtures

CASES = json.loads((Path(__file__).resolve().parents[2] / "evals" / "ask" / "cases.json").read_text())
KNOWN = INTEL_TOOL_NAMES | {"search_contacts", "get_contact", "create_note", "create_task", "inspect_record"}


def test_case_ids_are_unique_and_there_are_enough_of_them():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)) and len(ids) >= 30


def test_every_expected_number_has_ground_truth_computed_from_the_data():
    for case in CASES:
        for key in case.get("numbers", []):
            assert key in fixtures.TRUTH, (case["id"], key)


def test_every_named_tool_exists_and_every_regex_compiles():
    for case in CASES:
        for key in ("expect_tools_any", "forbid_tools", "expect_none_of"):
            assert set(case.get(key, [])) <= KNOWN, (case["id"], key)
        for pattern in [*case.get("must", []), *case.get("must_not", []), *[p for group in case.get("must_any", []) for p in group]]:
            re.compile(pattern)


def test_both_personas_are_covered():
    assert {c["persona"] for c in CASES} == {"ae", "mgr"}
    assert sum(1 for c in CASES if c["persona"] == "mgr") >= 12


def test_the_ground_truth_is_what_the_fixtures_contain():
    t = fixtures.TRUTH
    assert t["team_calls_aug"] == 150 and t["team_connected_aug"] == 36 and t["team_rate_aug"] == 24.0
    assert t["ana_rate_aug"] == 25.0 and t["lost_aug"] == 26 and t["won_aug"] == 8
