"""The channel filter finds rows that never had interaction_kind stamped, exactly as
interaction_kind_for classifies them, so no migration or backfill is needed."""

from __future__ import annotations

import itertools

import pytest

from app.services.captures import INTERACTION_KINDS, interaction_kind_filter, interaction_kind_for
from tests.postgrest_or import matches

SOURCES = [None, "", "vocify_call", "hubspot_call", "whatsapp", "web", "recall", "gmail"]
SOURCE_TYPES = [None, "", "voice_memo", "meeting_transcript", "recall_bot", "vocify_call"]
KINDS = sorted(INTERACTION_KINDS)


def _row(source, source_type, stored=None):
    return {"source": source, "source_type": source_type, "interaction_kind": stored}


@pytest.mark.parametrize("source,source_type", list(itertools.product(SOURCES, SOURCE_TYPES)))
def test_an_unstamped_row_is_selected_by_exactly_its_derived_kind(source, source_type):
    row = _row(source, source_type)
    derived = interaction_kind_for(source, source_type, None)
    selected = [kind for kind in KINDS if matches(interaction_kind_filter(kind), row)]
    assert selected == [derived]


@pytest.mark.parametrize("source", SOURCES)
def test_a_stored_kind_wins_over_the_origin(source):
    for stored in KINDS:
        row = _row(source, "meeting_transcript", stored)
        assert [k for k in KINDS if matches(interaction_kind_filter(k), row)] == [stored]


def test_the_known_origins():
    assert matches(interaction_kind_filter("call"), _row("vocify_call", None))
    assert matches(interaction_kind_filter("call"), _row("hubspot_call", "meeting_transcript"))
    assert matches(interaction_kind_filter("visit"), _row("whatsapp", None))
    assert matches(interaction_kind_filter("meeting"), _row("web", "meeting_transcript"))
    assert matches(interaction_kind_filter("meeting"), _row("recall", "recall_bot"))
    assert matches(interaction_kind_filter("call"), _row("web", "voice_memo"))
    assert not matches(interaction_kind_filter("voice_note"), _row("web", "voice_memo"))
