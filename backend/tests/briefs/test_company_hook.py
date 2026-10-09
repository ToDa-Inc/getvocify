"""Lista 4 T3 (E9): the «gancho de empresa» line - another contact of the same company."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-for-company-hook-32b")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-company-hook-32b")

import pytest

from app.services.briefs.company_hook import company_hook_line, normalize_company_name

TZ = "Europe/Madrid"


def _memo(memo_id="memo-m", *, contact_id="77", user_id="user-a", company="Factorial", name="Manuel García",
          summary="Le interesó el módulo de fichaje. Pidió precios.", created_at="2026-09-12T08:00:00Z", intelligence=None):
    extraction = {"companyName": company, "contactName": name, "summary": summary}
    if intelligence is not None:
        extraction["intelligence"] = intelligence
    return {
        "id": memo_id,
        "user_id": user_id,
        "hubspot_contact_id": contact_id,
        "created_at": created_at,
        "capture_started_at": created_at,
        "extraction": extraction,
    }


def _hook(memos, **kwargs):
    base = {"company_name": "Factorial", "colleague_memos": memos, "current_contact_id": "42", "tz_name": TZ, "viewer_id": "user-a"}
    base.update(kwargs)
    return company_hook_line(**base)


def test_colleague_memo_of_the_same_company_becomes_the_hook_line():
    assert _hook([_memo()]) == {
        "type": "company",
        "text": "En Factorial ya hablaste con Manuel García el 12 sep: Le interesó el módulo de fichaje.",
        "source_ref": "memo-m",
        "observed_at": "2026-09-12T08:00:00Z",
    }


def test_the_most_recent_colleague_memo_wins():
    old = _memo("memo-old", created_at="2026-09-01T08:00:00Z", name="Ana")
    new = _memo("memo-new", created_at="2026-09-20T08:00:00Z", name="Manuel García")
    line = _hook([old, new])
    assert line["source_ref"] == "memo-new"
    assert "Manuel García el 20 sep" in line["text"]


def test_the_contact_being_called_is_never_its_own_hook():
    assert _hook([_memo(contact_id="42")]) is None
    line = _hook([_memo("memo-same", contact_id="42", created_at="2026-09-25T08:00:00Z"), _memo("memo-other")])
    assert line["source_ref"] == "memo-other"


def test_memo_without_a_crm_contact_is_not_a_colleague():
    assert _hook([_memo(contact_id=None)]) is None


def test_other_companies_do_not_match():
    assert _hook([_memo(company="Holded")]) is None
    assert _hook([_memo(company="")]) is None
    assert _hook([_memo()], company_name="") is None
    assert _hook([_memo()], company_name=None) is None


@pytest.mark.parametrize(
    ("crm", "memo"),
    [
        ("Factorial", "FACTORIAL S.L."),
        ("Factorial HR, S.L.U.", "factorial hr"),
        ("Acme Inc.", "ACME"),
        ("Acme Ltd", "acme, inc"),
        ("Müller GmbH", "Muller"),
        ("Telefónica S.A.", "Telefonica"),
        ("  Factorial  ", "Factorial SL"),
    ],
)
def test_company_names_match_after_normalizing(crm, memo):
    assert normalize_company_name(crm) == normalize_company_name(memo)
    assert _hook([_memo(company=memo)], company_name=crm) is not None


def test_a_name_that_is_only_a_legal_suffix_does_not_normalize_to_nothing():
    assert normalize_company_name("S.L.") == "sl"
    assert normalize_company_name(None) == ""


def test_the_display_name_is_the_crm_name_as_written():
    line = _hook([_memo(company="FACTORIAL S.L.")], company_name="Factorial")
    assert line["text"].startswith("En Factorial ya hablaste")


def test_no_usable_summary_is_no_line():
    assert _hook([_memo(summary="")]) is None
    assert _hook([_memo(summary="# Resumen\n\n")]) is None


def test_a_memo_without_summary_is_skipped_for_an_older_one_with_it():
    empty = _memo("memo-empty", summary="", created_at="2026-09-20T08:00:00Z")
    usable = _memo("memo-usable", created_at="2026-09-10T08:00:00Z")
    assert _hook([empty, usable])["source_ref"] == "memo-usable"


def test_pain_quote_stands_in_for_a_missing_summary():
    intelligence = {
        "pain_confirmed": True,
        "evidence": [{"id": "ev-1", "quote": "Perdemos dos horas al día cuadrando turnos"}],
    }
    line = _hook([_memo(summary="", intelligence=intelligence)])
    assert line["text"] == "En Factorial ya hablaste con Manuel García el 12 sep: «Perdemos dos horas al día cuadrando turnos»"


def test_long_summary_is_trimmed_to_a_short_sentence():
    long = "Revisaron " + "muchos detalles del proceso de onboarding " * 6 + "y cerraron."
    line = _hook([_memo(summary=long)])
    tail = line["text"].split(": ", 1)[1]
    assert len(tail) <= 141
    assert tail.endswith("…")
    assert tail.startswith("Revisaron muchos detalles")


def test_colleague_memo_by_another_author_says_se_hablo():
    line = _hook([_memo(user_id="user-b")])
    assert line["text"] == "En Factorial ya se habló con Manuel García el 12 sep: Le interesó el módulo de fichaje."


def test_colleague_without_a_name_is_otra_persona():
    line = _hook([_memo(name="")])
    assert line["text"].startswith("En Factorial ya hablaste con otra persona el 12 sep:")


def test_memo_without_a_date_is_skipped():
    assert _hook([_memo(created_at=None)]) is None
