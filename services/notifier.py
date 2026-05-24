from aiogram import Bot

from bot.formatters import format_game_card
from bot.keyboards.inline import unsubscribe_keyboard
from services.ps_store import GameInfo, RegionPrice


async def notify_price_drop(
    bot: Bot,
    telegram_id: int,
    game_id: int,
    game_info: GameInfo,
    prices: dict[str, RegionPrice],
    old_prices: dict[str, float] | None,
    rates: dict[str, float] | None,
) -> None:
    title = "🔔 Price drop!"
    text = format_game_card(game_info, prices, rates, old_prices, title=title)
    keyboard = unsubscribe_keyboard(game_id)
    if game_info.cover_url:
        await bot.send_photo(telegram_id, game_info.cover_url, caption=text, reply_markup=keyboard)
    else:
        await bot.send_message(telegram_id, text, reply_markup=keyboard)
