from aiogram import Bot


async def send_price_drop(
    bot: Bot,
    telegram_id: int,
    game_title: str,
    old_price: float,
    new_price: float,
    currency: str,
) -> None:
    diff = old_price - new_price
    pct = round(diff / old_price * 100)
    text = (
        f"Снижение цены на <b>{game_title}</b>\n"
        f"{old_price} {currency} → <b>{new_price} {currency}</b> (-{pct}%)"
    )
    await bot.send_message(telegram_id, text)
