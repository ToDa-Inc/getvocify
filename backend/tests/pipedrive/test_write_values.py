"""Values as the live Pipedrive v2 API takes them (checked 2026-11-09 on a sandbox): option ids as numbers, multi-option
fields as lists, and a person's other emails and phones kept when Vocify adds one."""

import asyncio

from app.services.pipedrive.schema import PipedriveSchemaService, merged_contact_list, option_ids

SINGLE = {"field_code": "a" * 40, "field_type": "enum", "options": [{"id": 39, "label": "Alpha"}, {"id": 40, "label": "Beta"}]}
MULTI = {"field_code": "b" * 40, "field_type": "set", "options": [{"id": 42, "label": "Alpha"}, {"id": 43, "label": "Beta"}, {"id": 44, "label": "Gamma"}]}


class Schema(PipedriveSchemaService):
    def __init__(self):
        super().__init__(client=None)

    async def list_fields(self, object_type, *, use_cache=True):
        return [SINGLE, MULTI, {"field_code": "value", "field_type": "monetary"}]


def coerce(fields):
    return asyncio.run(Schema().coerce_for_write("deals", fields))


def test_single_option_is_the_option_id_as_a_number():
    assert coerce({"a" * 40: "40"}) == {"a" * 40: 40}
    assert coerce({"a" * 40: "beta"}) == {"a" * 40: 40}
    assert coerce({"a" * 40: 39}) == {"a" * 40: 39}


def test_multi_option_is_a_list_of_ids_whatever_shape_it_came_in():
    assert coerce({"b" * 40: "42"}) == {"b" * 40: [42]}
    assert coerce({"b" * 40: "42, Gamma"}) == {"b" * 40: [42, 44]}
    assert coerce({"b" * 40: ["Alpha", "43"]}) == {"b" * 40: [42, 43]}


def test_a_value_that_is_no_option_is_dropped_and_others_still_go():
    assert coerce({"a" * 40: "Zeta", "value": 1200}) == {"value": 1200}


def test_option_ids_ignores_unknown_parts():
    assert option_ids(MULTI, "Alpha, nope, 44") == [42, 44]


def test_new_email_is_primary_and_the_existing_ones_are_kept():
    existing = [{"value": "first@example.com", "primary": True, "label": "work"}, {"value": "second@example.com", "primary": False, "label": "home"}]
    merged = merged_contact_list(existing, [{"value": "new@example.com", "primary": True, "label": "work"}])
    assert [(e["value"], e["primary"]) for e in merged] == [("new@example.com", True), ("first@example.com", False), ("second@example.com", False)]


def test_a_phone_already_there_is_not_added_twice():
    merged = merged_contact_list([{"value": "+34 600 000 001", "primary": True}], [{"value": "+34600000001", "primary": True}])
    assert len(merged) == 1 and merged[0]["primary"] is True


def test_text_option_ids_stay_text():
    origin = {"field_code": "origin", "field_type": "enum", "options": [{"id": "ManuallyCreated", "label": "Manually created"}, {"id": "API", "label": "API"}]}
    assert option_ids(origin, "api") == ["API"]
    assert option_ids(origin, "Manually created") == ["ManuallyCreated"]
