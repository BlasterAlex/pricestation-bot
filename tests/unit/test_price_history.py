from datetime import datetime, timedelta, timezone

import pytest

from db.models.price_history import PriceHistory
from services.price_history import (
    DEFAULT_HISTORY_FORMAT,
    HISTORY_FORMAT_DATE,
    format_sale_when,
    is_active_sale,
    is_past_sale,
    resolve_history_format,
    sale_display_at,
)
from services.ps_store import RegionPrice

NOW = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("days_ago", "expected"),
    [
        (0, "today"),
        (1, "1 day ago"),
        (24, "24 days ago"),
        (59, "59 days ago"),
    ],
)
def test_format_sale_when_duration_days(days_ago, expected):
    recorded = NOW - timedelta(days=days_ago)
    assert format_sale_when(recorded, "duration", now=NOW) == expected


def test_format_sale_when_duration_months_only():
    recorded = NOW - timedelta(days=60)
    assert format_sale_when(recorded, "duration", now=NOW) == "2 months ago"


def test_format_sale_when_duration_months_and_days():
    recorded = NOW - timedelta(days=86)
    assert format_sale_when(recorded, "duration", now=NOW) == "2 months 26 days ago"


def test_format_sale_when_date():
    recorded = datetime(2026, 3, 12, tzinfo=timezone.utc)
    assert format_sale_when(recorded, "date", now=NOW) == "12 Mar 2026"


def test_is_active_sale():
    on_sale = RegionPrice(ps_id="x", price=29.99, currency="$", base_price=59.99, discount_text="-50%")
    full_price = RegionPrice(ps_id="x", price=59.99, currency="$", base_price=59.99, discount_text=None)
    no_base = RegionPrice(ps_id="x", price=29.99, currency="$", base_price=None, discount_text=None)
    assert is_active_sale(on_sale) is True
    assert is_active_sale(full_price) is False
    assert is_active_sale(no_base) is False


def test_is_past_sale():
    now = NOW
    future = now + timedelta(days=1)
    past = now - timedelta(days=1)
    active_promo = PriceHistory(game_id=1, region_id=1, price=10, discount_end=future)
    ended_promo = PriceHistory(game_id=1, region_id=1, price=10, discount_end=past)
    permanent = PriceHistory(game_id=1, region_id=1, price=10)
    assert is_past_sale(active_promo, now=now) is False
    assert is_past_sale(ended_promo, now=now) is True
    assert is_past_sale(permanent, now=now) is True


def test_sale_display_at():
    recorded = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ended = datetime(2026, 3, 1, tzinfo=timezone.utc)
    promo = PriceHistory(game_id=1, region_id=1, price=10, recorded_at=recorded, discount_end=ended)
    permanent = PriceHistory(game_id=1, region_id=1, price=10, recorded_at=recorded)
    assert sale_display_at(promo) == ended
    assert sale_display_at(permanent) == recorded


def test_resolve_history_format_null_returns_default():
    assert resolve_history_format(None) == DEFAULT_HISTORY_FORMAT


def test_resolve_history_format_returns_stored_value():
    assert resolve_history_format(HISTORY_FORMAT_DATE) == HISTORY_FORMAT_DATE
    assert resolve_history_format("duration") == "duration"
