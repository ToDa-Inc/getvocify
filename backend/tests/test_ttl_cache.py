from app.services.ttl_cache import TtlCache


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_a_value_is_returned_until_it_expires():
    clock = Clock()
    cache: TtlCache[str] = TtlCache(10, clock=clock)
    cache.put("a", "x")
    clock.now += 9
    assert cache.get("a") == "x"
    clock.now += 2
    assert cache.get("a") is None


def test_an_unknown_key_is_none_and_clear_forgets_everything():
    cache: TtlCache[str] = TtlCache(10)
    assert cache.get("a") is None
    cache.put("a", "x")
    cache.clear()
    assert cache.get("a") is None


def test_storing_again_restarts_the_clock():
    clock = Clock()
    cache: TtlCache[str] = TtlCache(10, clock=clock)
    cache.put("a", "x")
    clock.now += 8
    cache.put("a", "y")
    clock.now += 8
    assert cache.get("a") == "y"
