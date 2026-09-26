"""evals/F02 stays runnable: every case feeds the real prompt input and only uses checks the runner knows."""

import asyncio
import importlib.util
import json
import os
import re
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-followup-32b+")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-followup-32b+")

BACKEND = Path(__file__).resolve().parents[1]
CASES = BACKEND / "evals" / "F02" / "cases.json"
INPUT_KEYS = {"rep_name", "contact_name", "summary", "next_steps", "voice_samples", "transcript", "intelligence"}


def _runner():
    spec = importlib.util.spec_from_file_location("eval_followup", BACKEND / "scripts" / "eval_followup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cases() -> list[dict]:
    return json.loads(CASES.read_text(encoding="utf-8"))


def test_every_case_is_well_formed_and_builds_the_real_prompt_input():
    runner, cases = _runner(), _cases()
    assert 10 <= len(cases) <= 14
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["language"] for case in cases} == {"es", "en"}
    for case in cases:
        given, expect = case["input"], case["expect"]
        assert set(case) == {"id", "language", "input", "expect"}, case["id"]
        assert set(given) <= INPUT_KEYS and given["transcript"].strip() and len(given["rep_name"].split()) >= 2, case["id"]
        assert set(expect) <= runner.EXPECT_KEYS, case["id"]
        assert expect.get("formality") in (None, *runner.FORMALITY), case["id"]
        for pattern in expect.get("must_match", []) + expect.get("must_not_match", []):
            re.compile(pattern, runner.FLAGS)
        context = json.loads(runner.messages_for(case)[1]["content"])
        assert ("commitments" in context) == ("intelligence" in given), case["id"]
        if (context.get("meeting") or {}).get("day"):
            assert expect.get("must_match"), f"{case['id']}: a meeting case must check its day and time"


def test_cases_cover_the_brief():
    cases = _cases()
    ids = " ".join(case["id"] for case in cases)
    for topic in ("meeting", "vague", "price", "name", "usted", "tu_", "pain"):
        assert topic in ids, topic
    assert sum(case["language"] == "en" for case in cases) in (1, 2)


DRAFT = {
    "subject": "Demo del jueves y caso de logística",
    "language": "es",
    "body": (
        "Hola Marina,\n\n"
        "Gracias por contarme cómo se os quedan leads sin llamar cada semana. Te confirmo la demo el jueves "
        "1 de octubre a las 11:00, donde verás cómo lo resolvió otra empresa de transporte con un reparto claro "
        "de a quién le toca cada lead.\n\n"
        "Antes, el miércoles, te mando el caso de éxito de logística para que llegues con contexto y puedas "
        "preparar las preguntas que quieras hacer.\n\n"
        "Un saludo,\nLucía"
    ),
}
CASE = {"id": "c", "language": "es", "input": {"rep_name": "Lucía Pérez"}, "expect": {"formality": "tu"}}


def test_a_clean_draft_passes_every_global_check():
    assert _runner().check(CASE, DRAFT) == []


def test_each_global_check_fails_on_its_own():
    check = _runner().check
    bad = {
        "words": {**DRAFT, "body": "Hola Marina,\n\nTe mando el caso.\n\nLucía"},
        "subject": {**DRAFT, "subject": "Seguimiento"},
        "language": {**DRAFT, "language": "en"},
        "filler": {**DRAFT, "body": DRAFT["body"].replace("Un saludo,", "Quedo a tu disposición.\n\nUn saludo,")},
        "link": {**DRAFT, "body": DRAFT["body"].replace("logística para", "logística (https://x.io) para")},
        "signature": {**DRAFT, "body": DRAFT["body"].replace("\nLucía", "\nLucía Pérez")},
        "formality": {**DRAFT, "body": DRAFT["body"].replace("Te confirmo", "Le confirmo a usted")},
        "Spain": {**DRAFT, "body": DRAFT["body"].replace("te mando", "ahorita te mando")},
        "other language": {**DRAFT, "body": DRAFT["body"].replace("Gracias por", "Thank you and gracias por")},
    }
    for name, draft in bad.items():
        failures = check(CASE, draft)
        assert any(name in failure for failure in failures), (name, failures)


def test_case_regexes_are_checked_on_subject_and_body():
    check = _runner().check
    case = {**CASE, "expect": {"must_match": ["\\bviernes\\b"], "must_not_match": ["\\bjueves\\b"]}}
    failures = check(case, DRAFT)
    assert any("must_match" in failure for failure in failures)
    assert any("must_not_match" in failure for failure in failures)


def test_a_model_error_is_retried_once_then_reported_not_raised():
    runner = _runner()
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "{}"}]

    class Flaky:
        def __init__(self, fails):
            self.fails = fails

        async def chat_json(self, *_args, **_kwargs):
            if self.fails:
                self.fails -= 1
                raise ValueError("Empty model response")
            return {"subject": "Caso", "body": "Hola", "language": "es"}

    draft, errors = asyncio.run(runner.run_case(Flaky(1), messages, delay=0))
    assert draft["subject"] == "Caso"
    assert errors == ["ValueError: Empty model response"]
    draft, errors = asyncio.run(runner.run_case(Flaky(5), messages, delay=0))
    assert draft is None
    assert len(errors) == 2
