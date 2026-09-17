from app.services.crm_copilot.tools import WRITE_TOOLS, confirmation_required


def test_writes_require_confirmation():
    assert confirmation_required("apply_write")
    assert confirmation_required("create_note")
    assert confirmation_required("create_task")
    assert confirmation_required("create_contact")
    assert confirmation_required("create_deal")
    assert not confirmation_required("search_contacts")
    assert not confirmation_required("get_contact")
    assert not confirmation_required("offer_user_choices")
    assert WRITE_TOOLS == {
        "apply_write",
        "create_note",
        "create_task",
        "create_contact",
        "create_deal",
    }
