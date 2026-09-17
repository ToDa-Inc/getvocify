from app.services.whatsapp.actions import (
    ACT_APPROVE,
    ACT_KEEP,
    ACT_RETARGET,
    PICK_SKIP_DEAL,
    PRIMARY_BUTTONS,
    copilot_confirm_buttons,
    deal_list_sections,
)


def test_primary_buttons_are_semantic():
    ids = [b["id"] for b in PRIMARY_BUTTONS]
    assert ids == [ACT_APPROVE, ACT_KEEP, ACT_RETARGET]
    assert all(len(b["title"]) <= 25 for b in PRIMARY_BUTTONS)


def test_copilot_confirm_has_no_cambiar_deal():
    ids = [b["id"] for b in copilot_confirm_buttons()]
    assert ids == [ACT_APPROVE, ACT_KEEP]
    assert ACT_RETARGET not in ids


def test_deal_list_includes_reset_and_caps_rows():
    matches = [{"deal_id": str(i), "deal_name": f"Deal {i}"} for i in range(12)]
    sections = deal_list_sections(matches, has_deal=True)
    rows = [r for s in sections for r in s["rows"]]
    assert any(r["id"] == PICK_SKIP_DEAL for r in rows)
    assert sum(len(s["rows"]) for s in sections) <= 10
