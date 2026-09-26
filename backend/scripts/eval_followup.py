"""Run the follow-up prompt against evals/F02/cases.json with the configured model.

Usage (from backend/): .venv/bin/python -u scripts/eval_followup.py
A model error is retried once, then counted as a failed case. Exit code 1 when any case fails.
Each run is saved to evals/F02/runs/ with its time, model and the sha256 of cases.json.
Every check is a regex or a length. The one approximation: "Spanish from Spain" means no
LATAM_MARKERS, which catches the usual slips, not every variety.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services.followup import PROMPT_PATH, compose  # noqa: E402
from app.services.followup_logic import PROMPT_VERSION, build_messages, c04_facts  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "evals" / "F02" / "cases.json"
RUNS = CASES.parent / "runs"
REP_TIMEZONE = "Europe/Madrid"
ATTEMPTS = 2
RETRY_DELAY_S = 10.0
MIN_WORDS, MAX_WORDS = 60, 120
MAX_SUBJECT = 60
FLAGS = re.IGNORECASE | re.MULTILINE
GENERIC_SUBJECT = re.compile(r"^\W*(seguimiento|follow[- ]?up)\W*$", FLAGS)
LINKS = re.compile(r"https?://|www\.", FLAGS)
FILLER = re.compile(
    r"espero que (estés|esté|te encuentres|se encuentre|os encontréis|todo vaya)|como hablamos antes"
    r"|quedo a (tu|su|vuestra) (entera |total )?disposición|no dudes? en|quedo atent[oa]|quedo a la espera"
    r"|para cualquier (duda|consulta|cosa)|espero (tus|sus|vuestras) noticias"
    r"|hope (this email finds you|you('re| are)( doing)? well)|don'?t hesitate|feel free to reach out"
    r"|looking forward to hearing from you|let me know if you have any questions|just following up",
    FLAGS,
)
LATAM_MARKERS = re.compile(r"\b(ahorita|platic\w*|celular(es)?|computadora|chévere|checar|carro)\b", FLAGS)
OTHER_LANGUAGE = {
    "es": re.compile(r"\b(the|and|you|your|with|we)\b", FLAGS),
    "en": re.compile(r"\b(el|los|las|que|para|con|gracias|nosotros)\b", FLAGS),
}
FORMALITY = {
    "tu": (re.compile(r"\b(te|tu|tú|tus|contigo|ti)\b", FLAGS), re.compile(r"\busted(es)?\b", FLAGS)),
    "usted": (re.compile(r"\b(usted|le|les|su|sus)\b", FLAGS), re.compile(r"\b(te|tu|tú|tus|contigo)\b", FLAGS)),
}
EXPECT_KEYS = {"formality", "must_match", "must_not_match"}


def messages_for(case: dict) -> list[dict]:
    given = case["input"]
    facts = c04_facts(given["intelligence"], REP_TIMEZONE) if "intelligence" in given else None
    return build_messages(
        system_prompt=PROMPT_PATH.read_text(encoding="utf-8"),
        transcript=given["transcript"],
        summary=given["summary"],
        next_steps=list(given.get("next_steps") or []),
        contact_name=given.get("contact_name"),
        rep_name=given["rep_name"],
        voice_samples=list(given.get("voice_samples") or []),
        facts=facts,
    )


def _signature(body: str, rep_name: str) -> list[str]:
    first, *rest = rep_name.split()
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    last = re.sub(r"[\W_]+$", "", lines[-1]) if lines else ""
    failures = []
    if not last.casefold().endswith(first.casefold()):
        failures.append(f"signature: last line {last!r} does not end with {first!r}")
    surname = " ".join(rest)
    if surname and surname.casefold() in body.casefold():
        failures.append(f"signature: surname {surname!r} appears")
    return failures


def check(case: dict, draft: dict) -> list[str]:
    body, subject = draft["body"], draft["subject"]
    language, expect = case["language"], case["expect"]
    failures = []
    words = len(re.findall(r"\w+", body))
    if not MIN_WORDS <= words <= MAX_WORDS:
        failures.append(f"words: {words}, expected {MIN_WORDS}-{MAX_WORDS}")
    if len(subject) >= MAX_SUBJECT or GENERIC_SUBJECT.match(subject):
        failures.append(f"subject: {subject!r}")
    if not str(draft.get("language") or "").lower().startswith(language):
        failures.append(f"language: expected {language!r}, got {draft.get('language')!r}")
    for name, pattern in (("other language", OTHER_LANGUAGE[language]), ("link", LINKS), ("filler", FILLER)):
        found = pattern.search(body)
        if found:
            failures.append(f"{name}: {found.group(0)!r}")
    if language == "es" and LATAM_MARKERS.search(body):
        failures.append(f"not Spain Spanish: {LATAM_MARKERS.search(body).group(0)!r}")
    failures += _signature(body, case["input"]["rep_name"])
    if expect.get("formality"):
        required, forbidden = FORMALITY[expect["formality"]]
        if not required.search(body):
            failures.append(f"formality: no {expect['formality']} marker")
        if forbidden.search(body):
            failures.append(f"formality: {forbidden.search(body).group(0)!r} in a {expect['formality']} email")
    text = f"{subject}\n{body}"
    failures += [f"must_match: {p!r}" for p in expect.get("must_match") or [] if not re.search(p, text, FLAGS)]
    for pattern in expect.get("must_not_match") or []:
        found = re.search(pattern, text, FLAGS)
        if found:
            failures.append(f"must_not_match {pattern!r}: {found.group(0)!r}")
    return failures


async def run_case(llm, messages: list[dict], *, delay: float = RETRY_DELAY_S) -> tuple[dict | None, list[str]]:
    errors = []
    for attempt in range(ATTEMPTS):
        if attempt:
            await asyncio.sleep(delay)
        try:
            return await compose(llm, messages), errors
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}"[:200])
    return None, errors


def run_record(lines: list[dict], summary: dict, *, now: datetime, cases_bytes: bytes) -> tuple[str, dict]:
    model = str(summary.get("model") or "unknown")
    name = f"{now:%Y%m%dT%H%M%SZ}-{re.sub(r'[^A-Za-z0-9.-]+', '_', model)}.json"
    return name, {
        "timestamp": now.isoformat(), "prompt": summary.get("prompt"), "model": model,
        "cases_sha256": hashlib.sha256(cases_bytes).hexdigest(), "summary": summary, "results": lines,
    }


async def main() -> int:
    from app.services.llm import LLMClient

    cases_bytes = CASES.read_bytes()
    cases = json.loads(cases_bytes.decode("utf-8"))
    lines = []
    llm = LLMClient()
    failed = errored = retried = 0
    for case in cases:
        draft, errors = await run_case(llm, messages_for(case))
        if draft is None:
            failures = ["model error on every attempt" if errors else "empty or malformed draft"]
        else:
            failures = check(case, draft)
        failed += bool(failures)
        errored += draft is None and bool(errors)
        retried += bool(errors) and draft is not None
        line = {"id": case["id"], "pass": not failures, "failures": failures, "errors": errors}
        if failures and draft is not None:
            line["draft"] = draft
        lines.append(line)
        print(json.dumps(line, ensure_ascii=False))
    summary = {
        "prompt": PROMPT_VERSION, "model": settings.FOLLOWUP_MODEL, "cases": len(cases),
        "failed": failed, "model_errors": errored, "passed_after_retry": retried,
    }
    print(json.dumps(summary))
    name, record = run_record(lines, summary, now=datetime.now(timezone.utc).replace(microsecond=0),
                              cases_bytes=cases_bytes)
    RUNS.mkdir(exist_ok=True)
    (RUNS / name).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
