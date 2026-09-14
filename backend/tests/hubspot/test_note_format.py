from app.services.hubspot.note_format import (
    first_bullet_plaintext,
    format_field_changes_section,
    format_hubspot_note_body,
    format_summary_html,
    record_written_fields,
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


def test_note_body_includes_written_field_changes():
    body = format_hubspot_note_body(
        summary="Hello there",
        transcript="You\nHi",
        field_changes=[
            {"object_type": "contacts", "field": "vocify_fit", "value": "moderate"},
            {
                "object_type": "companies",
                "field": "crm_utilizado",
                "value": "zoho",
                "created": True,
            },
        ],
    )
    assert "Fields updated" in body
    assert "Contact · Fit" in body
    assert "moderate" in body
    assert "Company (new) · Crm Utilizado" in body
    assert "zoho" in body
    assert 'style="color:#067647"' in body
    assert "<s " in body


def test_field_changes_section_shows_previous_value_and_spanish_title():
    html = format_field_changes_section(
        [
            {
                "object_type": "contacts",
                "field": "vocify_sales_motion",
                "label": "Sales motion",
                "previous": "inside_sales",
                "value": "field_sales",
            }
        ],
        spanish=True,
    )
    assert "Campos actualizados" in html
    assert "Contacto · Sales motion" in html
    assert '<s style="color:#b42318">Inside Sales</s>' in html
    assert '<strong style="color:#067647">Field Sales</strong>' in html


def test_record_written_fields_skips_owner_and_empty_values():
    written: list[dict] = []
    record_written_fields(
        written,
        object_type="contacts",
        props={"vocify_fit": "moderate", "hubspot_owner_id": "99", "jobtitle": ""},
        current={"vocify_fit": None},
    )
    assert written == [
        {
            "object_type": "contacts",
            "field": "vocify_fit",
            "value": "moderate",
            "previous": None,
            "created": False,
        }
    ]


def test_note_body_splits_collapsed_transcript_into_turns():
    body = format_hubspot_note_body(
        summary="Hello there",
        transcript=(
            "SPEAKER: S1\n"
            "¿Usted ahora mismo está con Zoho?\n"
            "Sí.\n"
            "B2B outbound."
        ),
    )
    assert body.count("<strong>Comercial:</strong>") >= 1
    assert body.count("<strong>Contacto:</strong>") >= 1
    assert "¿Usted ahora mismo está con Zoho?" in body
    assert "Sí." in body


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
