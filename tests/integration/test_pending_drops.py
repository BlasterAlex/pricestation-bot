from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Game, PriceDrop
from services.price import get_pending_drops

AGGREGATION_HOURS = 8


@pytest.fixture(autouse=True)
def patch_aggregation(mocker):
    mocker.patch("services.price.settings.NOTIFY_AGGREGATION_HOURS", AGGREGATION_HOURS)


def _make_drop(game: Game, *, hours_ago: float, notified: bool = False) -> PriceDrop:
    return PriceDrop(
        game_id=game.id,
        created_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        notified_at=datetime.now(timezone.utc) if notified else None,
    )


@pytest_asyncio.fixture
async def game2(session: AsyncSession):
    g = Game(title="Another Game", composite_key="anothergame_full_game_ps5", ps_id_suffix="ANOTHERGAME00")
    session.add(g)
    await session.flush()
    return g


# ── cutoff filtering ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_old_drop_is_returned(session: AsyncSession, game):
    session.add(_make_drop(game, hours_ago=AGGREGATION_HOURS + 1))
    await session.flush()

    drops = await get_pending_drops(session)

    assert len(drops) == 1
    assert drops[0].game_id == game.id


@pytest.mark.asyncio
async def test_fresh_drop_is_withheld(session: AsyncSession, game):
    session.add(_make_drop(game, hours_ago=AGGREGATION_HOURS - 1))
    await session.flush()

    drops = await get_pending_drops(session)

    assert drops == []


@pytest.mark.asyncio
async def test_notified_drop_excluded_regardless_of_age(session: AsyncSession, game):
    session.add(_make_drop(game, hours_ago=AGGREGATION_HOURS + 1, notified=True))
    await session.flush()

    drops = await get_pending_drops(session)

    assert drops == []


@pytest.mark.asyncio
async def test_no_drops_returns_empty(session: AsyncSession):
    drops = await get_pending_drops(session)

    assert drops == []


@pytest.mark.asyncio
async def test_only_old_pending_drops_returned_in_mix(session: AsyncSession, game, game2):
    session.add(_make_drop(game, hours_ago=AGGREGATION_HOURS + 1))   # old → returned
    session.add(_make_drop(game2, hours_ago=AGGREGATION_HOURS - 1))  # fresh → withheld
    await session.flush()

    drops = await get_pending_drops(session)

    assert len(drops) == 1
    assert drops[0].game_id == game.id
