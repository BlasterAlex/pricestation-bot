import asyncio

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from prometheus_client import start_http_server

from config import settings, setup_logging
from worker.tasks.notify import send_notifications
from worker.tasks.price_check import check_prices

setup_logging()


async def main() -> None:
    start_http_server(8000)
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_prices, CronTrigger.from_crontab(settings.PRICE_CHECK_CRON))
    scheduler.add_job(send_notifications, CronTrigger.from_crontab(settings.NOTIFY_CRON), args=[bot])
    scheduler.start()
    try:
        await asyncio.Event().wait()
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
