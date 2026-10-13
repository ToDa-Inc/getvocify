"""One current score per call, whatever order the rows come back in."""

from app.services.coaching.score_rows import current_score, current_scores


def _row(seq, created, revision="r1", memo="m1"):
    return {"memo_id": memo, "revision_seq": seq, "created_at": created, "input_revision": revision}


def test_the_highest_revision_wins_even_when_written_earlier():
    old, new = _row(1, "2026-09-25T10:00:00+00:00", "a"), _row(2, "2026-09-23T10:00:00+00:00", "b")
    assert current_score([old, new]) is new and current_score([new, old]) is new


def test_same_revision_the_latest_written_wins():
    first, second = _row(3, "2026-09-23T10:00:00+00:00", "a"), _row(3, "2026-09-24T10:00:00+00:00", "b")
    assert current_score([first, second]) is second and current_score([second, first]) is second


def test_a_full_tie_does_not_depend_on_the_order():
    a, b = _row(3, "2026-09-23T10:00:00+00:00", "a"), _row(3, "2026-09-23T10:00:00+00:00", "b")
    assert current_score([a, b]) is b and current_score([b, a]) is b


def test_per_memo_and_empty():
    rows = [_row(1, "x", memo="m1"), _row(2, "x", memo="m1"), _row(1, "x", memo="m2")]
    assert {k: v["revision_seq"] for k, v in current_scores(rows).items()} == {"m1": 2, "m2": 1}
    assert current_score([]) is None and current_scores([]) == {}
