from app.api.crm_pipedrive import _fields_to_properties
from app.services.pipedrive.schema import (
    PipedriveSchemaService,
    curated_spec_from_field,
    expand_schema_fields,
    field_key,
    field_label,
    flatten_record,
    is_custom_field_code,
)


def test_v2_field_code_maps():
    raw = {"field_code": "title", "field_name": "Title", "field_type": "varchar", "is_writable": True}
    assert field_key(raw) == "title"
    assert field_label(raw) == "Title"
    props = _fields_to_properties([raw])
    assert props[0].name == "title"
    assert props[0].label == "Title"
    assert props[0].readOnlyValue is False


def test_v1_key_still_maps():
    raw = {"key": "value", "name": "Value", "field_type": "monetary", "edit_flag": True}
    assert field_key(raw) == "value"
    props = _fields_to_properties([raw])
    assert props[0].name == "value"
    assert props[0].label == "Value"


def test_v2_without_key_is_not_dropped():
    assert _fields_to_properties([{"field_code": "stage_id", "field_name": "Stage"}])[0].name == "stage_id"
    assert _fields_to_properties([{"field_name": "Nope"}]) == []


def test_value_subfield_currency_from_live_shape():
    raw = [
        {
            "field_code": "value",
            "field_name": "Value",
            "field_type": "monetary",
            "is_writable": True,
            "subfields": [
                {"field_code": "currency", "field_name": "Currency of Value", "field_type": "varchar"},
            ],
        }
    ]
    expanded = expand_schema_fields(raw)
    props = _fields_to_properties(expanded)
    names = [p.name for p in props]
    assert names == ["value", "currency"]
    assert props[1].label == "Currency of Value"


def test_live_enum_options_id_label():
    raw = {
        "field_code": "5f65fa0c38e46e47a59a4721d5b51f21d89fb679",
        "field_name": "CRM",
        "field_type": "enum",
        "is_writable": True,
        "is_custom_field": True,
        "options": [{"id": 39, "label": "Hubspot"}, {"id": 41, "label": "Pipedrive"}],
    }
    prop = _fields_to_properties([raw])[0]
    assert prop.name == "5f65fa0c38e46e47a59a4721d5b51f21d89fb679"
    assert [(o.value, o.label) for o in prop.options] == [("39", "Hubspot"), ("41", "Pipedrive")]


def test_curated_spec_normalizes_enum_and_number():
    enum_field = {
        "field_code": "abc1234567890123456789012345678901234567890",
        "field_name": "Funcionalitats",
        "field_type": "set",
        "options": [{"id": 1338, "label": "Menjador"}],
    }
    spec = curated_spec_from_field(enum_field, "deals")
    assert spec["type"] == "enumeration"
    assert spec["object_type"] == "deals"
    assert spec["options"][0]["value"] == "1338"

    number_field = {"field_code": "preu", "field_name": "Preu per alumne", "field_type": "double"}
    assert curated_spec_from_field(number_field, "deals")["type"] == "number"


def test_flatten_record_unwraps_custom_fields():
    flat = flatten_record({"title": "Acme", "custom_fields": {"hash1234567890123456789012345678901234567890": 35}})
    assert flat["title"] == "Acme"
    assert flat["hash1234567890123456789012345678901234567890"] == 35


def test_split_write_uses_official_hash_rule():
    svc = PipedriveSchemaService(None)
    payload = svc.split_write_payload(
        {
            "title": "Acme",
            "currency": "EUR",
            "mrr": 10,
            "5f65fa0c38e46e47a59a4721d5b51f21d89fb679": 41,
        }
    )
    assert payload["title"] == "Acme"
    assert payload["currency"] == "EUR"
    assert payload["mrr"] == 10
    assert payload["custom_fields"] == {"5f65fa0c38e46e47a59a4721d5b51f21d89fb679": 41}
    assert is_custom_field_code("5f65fa0c38e46e47a59a4721d5b51f21d89fb679")
    assert not is_custom_field_code("title")
