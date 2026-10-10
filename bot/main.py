import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiogram.utils.backoff import BackoffConfig
from prometheus_client import start_http_server

from bot.handlers import router
from bot.middlewares.db import DbSessionMiddleware
from config import settings, setup_logging
from db.session import AsyncSessionFactory

setup_logging()

_POLLING_BACKOFF = BackoffConfig(min_delay=5.0, max_delay=30.0, factor=1.5, jitter=0.1)

_BOT_COMMANDS = [
    BotCommand(command="start", description="Welcome message"),
    BotCommand(command="settings", description="Display currency, regions, and preferences"),
    BotCommand(command="search", description="Find a game and subscribe to price drops"),
    BotCommand(command="subscriptions", description="Manage your subscriptions"),
]


async def main() -> None:
    start_http_server(8000)
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await bot.set_my_commands(_BOT_COMMANDS)
    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware(AsyncSessionFactory))
    dp.include_router(router)
    await dp.start_polling(bot, backoff_config=_POLLING_BACKOFF)


if __name__ == "__main__":
    asyncio.run(main())
