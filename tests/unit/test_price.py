from services.price import is_price_dropped


def test_price_dropped():
    assert is_price_dropped(1000.0, 800.0) is True


def test_price_not_dropped():
    assert is_price_dropped(800.0, 1000.0) is False


def test_price_unchanged():
    assert is_price_dropped(1000.0, 1000.0) is False
