import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers import router
from bot.middlewares.db import DbSessionMiddleware
from config import settings
from db.session import AsyncSessionFactory

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware(AsyncSessionFactory))
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
