from aiogram import Bot

from bot.formatters import format_game_card
from bot.keyboards.inline import price_drop_keyboard
from services.currency import DEFAULT_BASE_CURRENCY
from services.price_history import UserGameSaleHistory, resolve_history_format
from services.ps_store import GameInfo, RegionPrice


async def notify_price_drop(
    bot: Bot,
    telegram_id: int,
    game_id: int,
    game_info: GameInfo,
    prices: dict[str, RegionPrice],
    old_prices: dict[str, float] | None,
    rates: dict[str, float] | None,
    base_currency: str = DEFAULT_BASE_CURRENCY,
    sale_history: UserGameSaleHistory | None = None,
    history_format: str | None = None,
) -> None:
    title = "🔔 Price drop!"
    text = format_game_card(
        game_info,
        prices,
        rates,
        old_prices,
        title=title,
        base_currency=base_currency,
        sale_history=sale_history,
        history_format=resolve_history_format(history_format),
        history_limit=3,
    )
    keyboard = price_drop_keyboard(game_id)
    if game_info.cover_url:
        await bot.send_photo(telegram_id, game_info.cover_url, caption=text, reply_markup=keyboard)
    else:
        await bot.send_message(telegram_id, text, reply_markup=keyboard)
