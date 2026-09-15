from pathlib import Path


def test_full_reset_conversations_check_includes_retarget_states():
    sql = (Path(__file__).resolve().parents[2] / "full_reset.sql").read_text()
    marker = "CREATE TABLE conversations"
    start = sql.index(marker)
    chunk = sql[start : start + 1200]
    assert "waiting_retarget" in chunk
    assert "waiting_typed_search" in chunk
