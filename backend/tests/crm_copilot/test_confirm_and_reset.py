from app.services.crm_copilot.loop import _confirm_text, _is_hollow_preview
from app.services.crm_copilot.route import is_reset_command


def test_reset_phrases():
    assert is_reset_command("reset")
    assert is_reset_command("/reset")
    assert is_reset_command("nueva conversación")
    assert is_reset_command("Nueva sesion")
    assert is_reset_command("olvida esto")
    assert is_reset_command("empezar de cero")
    assert is_reset_command("start over")
    assert not is_reset_command("qué pasó con Marc")
    assert not is_reset_command("Actualizar")


def test_confirm_text_is_human_not_json():
    text = _confirm_text(
        "create_note",
        {"contact_id": "8648", "body": "Ya hemos integrado Pipedrive (no Payper)."},
        {},
    )
    assert "create_note" not in text
    assert "{" not in text
    assert "Pipedrive" in text
    assert "Actualizar or No actualizar" not in text


def test_confirm_text_uses_preview_without_button_echo():
    text = _confirm_text("apply_write", {}, {"last_preview_text": "Cargo → CEO"})
    assert text == "Cargo → CEO"
    assert "Actualizar or No actualizar" not in text


def test_solo_contacto_card_is_hollow():
    assert _is_hollow_preview("Contacto\nSolo contacto")
    assert _is_hollow_preview("Contacto\nSolo contacto\n\nActualizar or No actualizar.")
    assert not _is_hollow_preview("Cargo → CEO")
    assert not _is_hollow_preview("Nota: Les encaja la solución")


def test_a_note_confirmation_names_the_contact_it_is_for():
    from app.services.crm_copilot.loop import _confirm_text

    copilot = {"last_contact_id": "c1", "last_contact_name": "Marina López"}
    assert _confirm_text("create_note", {"body": "Enviar la propuesta", "contact_id": "c1"}, copilot) == "Nota para Marina López: Enviar la propuesta"
    assert _confirm_text("create_task", {"subject": "Llamar", "contact_id": "c1"}, copilot) == "Tarea para Marina López: Llamar"


def test_the_name_is_not_used_for_a_different_contact():
    from app.services.crm_copilot.loop import _confirm_text

    copilot = {"last_contact_id": "c1", "last_contact_name": "Marina López"}
    assert _confirm_text("create_note", {"body": "x", "contact_id": "c2"}, copilot) == "Nota: x"


def test_a_single_search_hit_remembers_the_name_for_later_confirmations():
    from app.services.crm_copilot.loop import _touch_session

    copilot: dict = {}
    _touch_session(copilot, {"contacts": [{"id": "c1", "name": "Marina López", "url": "u"}]})
    assert copilot["last_contact_id"] == "c1" and copilot["last_contact_name"] == "Marina López"
