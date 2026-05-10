import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from scheduler.tasks.price_check import check_prices

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_prices, "interval", hours=settings.SCHEDULER_INTERVAL_HOURS)
    scheduler.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
