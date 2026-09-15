from app.services.preview_targets import resolve_preview_deal_selection


def test_skip_deal_wins_over_existing_deal_id():
    selected, create_new = resolve_preview_deal_selection(
        deal_id="123",
        create_new_deal=False,
        has_selected_contact=True,
        has_contact_candidates=False,
        skip_deal=True,
    )
    assert selected is None
    assert create_new is False


def test_omit_deal_with_contact_still_skips():
    selected, create_new = resolve_preview_deal_selection(
        deal_id=None,
        create_new_deal=False,
        has_selected_contact=True,
        has_contact_candidates=False,
        skip_deal=False,
    )
    assert selected is None
    assert create_new is False
