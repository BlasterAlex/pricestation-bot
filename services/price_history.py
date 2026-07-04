from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PriceHistory, Region, Subscription, UserRegion
from services.ps_store import RegionPrice

HISTORY_FORMAT_DURATION = "duration"
HISTORY_FORMAT_DATE = "date"
DEFAULT_HISTORY_FORMAT = HISTORY_FORMAT_DURATION

LIMIT_PUSH = 3
LIMIT_CARD = 10


@dataclass
class RegionSaleHistory:
    region_code: str
    currency: str
    sales: list[tuple[float, datetime]] = field(default_factory=list)


@dataclass
class UserGameSaleHistory:
    tracking_since: datetime
    regions: list[RegionSaleHistory] = field(default_factory=list)
    total_sales: int = 0
    has_more: bool = False


def resolve_history_format(value: str | None) -> str:
    if value == HISTORY_FORMAT_DATE:
        return HISTORY_FORMAT_DATE
    return HISTORY_FORMAT_DURATION


def is_active_sale(rp: RegionPrice) -> bool:
    return (
        rp.price is not None
        and rp.base_price is not None
        and rp.price < rp.base_price
    )


def sale_display_at(entry: PriceHistory) -> datetime:
    """When to show a sale in Past sales — promo end date, or detection time for permanent drops."""
    return entry.discount_end or entry.recorded_at


def is_past_sale(entry: PriceHistory, *, now: datetime | None = None) -> bool:
    """Promos with a future end date stay hidden until the sale ends."""
    if entry.discount_end is None:
        return True
    ref = now or datetime.now(timezone.utc)
    end = entry.discount_end
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return end <= ref


async def record_active_sales_on_subscribe(
    session: AsyncSession,
    game_id: int,
    prices: dict[str, RegionPrice],
    regions_by_code: dict[str, Region],
) -> None:
    """Seed price_history with the current sale when tracking starts during an active discount."""
    for code, rp in prices.items():
        if not is_active_sale(rp):
            continue
        region = regions_by_code.get(code)
        if region is None:
            continue
        session.add(PriceHistory(
            game_id=game_id,
            region_id=region.id,
            price=rp.price,
            discount_end=rp.discount_end,
        ))


def _format_calendar_date(dt: datetime) -> str:
    return dt.strftime("%d %b %Y")


def format_sale_when(recorded_at: datetime, mode: str, *, now: datetime | None = None) -> str:
    if mode == HISTORY_FORMAT_DATE:
        return _format_calendar_date(recorded_at)

    reference = now or datetime.now(timezone.utc)
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    days = (reference.date() - recorded_at.date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day ago"
    if days < 60:
        return f"{days} days ago"

    months = days // 30
    rem = days % 30
    month_label = f"{months} month" if months == 1 else f"{months} months"
    if rem == 0:
        return f"{month_label} ago"
    day_label = "1 day" if rem == 1 else f"{rem} days"
    return f"{month_label} {day_label} ago"


async def get_user_game_sale_history(
    session: AsyncSession,
    user_id: int,
    game_id: int,
    *,
    limit_per_region: int,
) -> UserGameSaleHistory | None:
    sub = await session.scalar(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.game_id == game_id)
    )
    if sub is None:
        return None

    user_region_ids = {
        row[0]
        for row in (
            await session.execute(select(UserRegion.region_id).where(UserRegion.user_id == user_id))
        ).all()
    }
    if not user_region_ids:
        return UserGameSaleHistory(tracking_since=sub.created_at, regions=[], total_sales=0)

    now = datetime.now(timezone.utc)
    rows = (
        await session.execute(
            select(PriceHistory, Region)
            .join(Region, Region.id == PriceHistory.region_id)
            .where(
                PriceHistory.game_id == game_id,
                PriceHistory.region_id.in_(user_region_ids),
                PriceHistory.recorded_at >= sub.created_at,
                or_(PriceHistory.discount_end.is_(None), PriceHistory.discount_end <= now),
            )
            .order_by(PriceHistory.recorded_at.desc())
        )
    ).all()
    rows.sort(key=lambda row: sale_display_at(row[0]), reverse=True)

    total = len(rows)
    by_region: dict[str, RegionSaleHistory] = {}
    has_more = False
    for entry, region in rows:
        bucket = by_region.get(region.code)
        if bucket is None:
            bucket = RegionSaleHistory(region_code=region.code, currency=region.currency or "")
            by_region[region.code] = bucket
        if len(bucket.sales) >= limit_per_region:
            has_more = True
            continue
        bucket.sales.append((float(entry.price), sale_display_at(entry)))

    return UserGameSaleHistory(
        tracking_since=sub.created_at,
        regions=list(by_region.values()),
        total_sales=total,
        has_more=has_more,
    )
