from app.services.telephony.emergency import is_emergency_destination


def test_blocks_eu_and_us_emergency():
    assert is_emergency_destination("+34112")
    assert is_emergency_destination("+1911")
    assert is_emergency_destination("112")
    assert is_emergency_destination("911")
    assert is_emergency_destination("061")
    assert is_emergency_destination("016")


def test_allows_spanish_mobile():
    assert not is_emergency_destination("+34600111222")
