from app.models.approval import ApprovalPreview, ContactMatch, ProposedUpdate
from app.services.whatsapp.copy import briefing_text, button_body
from uuid import uuid4


def test_copy_hides_unchanged_email_and_empty_fields():
    preview = ApprovalPreview(
        memo_id=uuid4(),
        transcript_summary="summary",
        selected_contact=ContactMatch(
            contact_id="1",
            name="Ana López",
            company_name="Neurtek",
        ),
        selected_deal=None,
        skip_deal=True,
        proposed_updates=[
            ProposedUpdate(
                object_type="contacts",
                field_name="email",
                field_label="Email",
                new_value="a@b.com",
                current_value="a@b.com",
                extraction_confidence=0.9,
            ),
            ProposedUpdate(
                object_type="contacts",
                field_name="jobtitle",
                field_label="Cargo",
                new_value="Directora",
                current_value="",
                extraction_confidence=0.9,
            ),
        ],
    )
    text = briefing_text(preview, next_steps=["Llamar a Aritzel"])
    assert "Ana López" in text
    assert "Cargo" in text
    assert "a@b.com" not in text
    assert "Llamar a Aritzel" in text
    body = button_body(preview)
    assert len(body) <= 280
    assert "deal" not in body.lower() or "solo" in body.lower()
