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
