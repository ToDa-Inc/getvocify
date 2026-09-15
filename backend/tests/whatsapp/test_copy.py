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


def test_briefing_text_shows_dated_task_from_schedule():
    preview = ApprovalPreview(
        memo_id=uuid4(),
        transcript_summary="summary",
        selected_contact=ContactMatch(
            contact_id="1",
            name="Ana López",
            company_name="Neurtek",
        ),
        skip_deal=True,
    )
    text = briefing_text(
        preview,
        next_steps=["Llamar a Aritzel"],
        next_step_schedules=["2026-09-20"],
    )
    assert "Llamar a Aritzel" in text
    assert "Sun 20" in text


def test_briefing_text_shows_dated_task_from_proposed_update():
    preview = ApprovalPreview(
        memo_id=uuid4(),
        transcript_summary="summary",
        selected_contact=ContactMatch(
            contact_id="1",
            name="Ana López",
            company_name="Neurtek",
        ),
        skip_deal=True,
        proposed_updates=[
            ProposedUpdate(
                field_name="next_step_task_1",
                field_label="Tarea",
                new_value="Enviar propuesta",
                due_date="2026-09-18",
                extraction_confidence=0.9,
            ),
        ],
    )
    text = briefing_text(preview, next_steps=["Enviar propuesta"])
    assert "Enviar propuesta" in text
    assert "Fri 18" in text
