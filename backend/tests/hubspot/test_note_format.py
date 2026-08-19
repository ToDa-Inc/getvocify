from app.services.hubspot.note_format import (
    first_bullet_plaintext,
    format_hubspot_note_body,
    format_summary_html,
)

FRANCK = """# Contexto
- Llamada en frío a Franck de NEURTEK para presentar Vocify
- No recordaba haber tenido contacto previo

# Perfil
- No gestiona un equipo comercial interno
  - Las ventas van por distribuidores externos
- Usan Microsoft Dynamics; los distribuidores también

# Decisión
- Franck no es el interlocutor adecuado
- Redirige a **Aritzel Expuru**, director de NEURTEK

# Próximos Pasos
- Contactar a Aritzel Expuru en NEURTEK
"""


def test_format_summary_html_uses_headings_not_hash_marks():
    html = format_summary_html(FRANCK)
    assert "<h3>Contexto</h3>" in html
    assert "<ul>" in html
    assert "# Contexto" not in html
    assert "<strong>Aritzel Expuru</strong>" in html
    assert "Próximos" not in html
    assert "Contactar a Aritzel" not in html


def test_hubspot_note_body_contains_structured_summary():
    body = format_hubspot_note_body(summary=FRANCK, transcript="You\nHola")
    assert "<h3>Contexto</h3>" in body
    assert "<p><strong>Resumen</strong></p>" not in body
    assert "<p><strong>Summary</strong></p>" not in body


def test_first_bullet_plaintext_for_deal_description():
    assert first_bullet_plaintext(FRANCK) == (
        "Llamada en frío a Franck de NEURTEK para presentar Vocify"
    )


def test_format_summary_html_strips_asterisk_bullet_markers():
    html = format_summary_html(
        "# Contexto\n* Cold call to Franck\n  * Nested point\n+ Another item\n"
    )
    assert "<li>Cold call to Franck" in html
    assert "<li>Nested point" in html
    assert "<li>Another item" in html
    assert "* Cold call" not in html
    assert "* Nested" not in html
    assert "+ Another" not in html
