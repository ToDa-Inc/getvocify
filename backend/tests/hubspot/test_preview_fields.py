from app.services.hubspot.preview import (
    include_extracted_field,
    preview_field_already_applied,
    replay_written_fields,
)


def test_skips_unchanged_on_first_review():
    assert (
        include_extracted_field(
            new_display="OPEN",
            current_display="OPEN",
            include_unchanged=False,
        )
        is False
    )


def test_keeps_unchanged_after_approve():
    assert (
        include_extracted_field(
            new_display="OPEN",
            current_display="OPEN",
            include_unchanged=True,
        )
        is True
    )


def test_always_keeps_a_real_diff():
    assert (
        include_extracted_field(
            new_display="OPEN",
            current_display="NEW",
            include_unchanged=False,
        )
        is True
    )


def test_empty_extraction_never_shows():
    assert (
        include_extracted_field(
            new_display="",
            current_display="OPEN",
            include_unchanged=True,
        )
        is False
    )


def test_already_applied_only_when_replaying_a_match():
    assert (
        preview_field_already_applied(
            current_display="OPEN",
            new_display="OPEN",
            include_unchanged=True,
        )
        is True
    )
    assert (
        preview_field_already_applied(
            current_display="NEW",
            new_display="OPEN",
            include_unchanged=True,
        )
        is False
    )
    assert (
        preview_field_already_applied(
            current_display="OPEN",
            new_display="OPEN",
            include_unchanged=False,
        )
        is False
    )


def test_approved_memo_replays_written_fields():
    assert replay_written_fields("approved") is True
    assert replay_written_fields("pending_review") is False
    assert replay_written_fields(None) is False
