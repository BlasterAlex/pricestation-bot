import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from prometheus_client import start_http_server

from config import settings, setup_logging
from worker.tasks.price_check import check_prices

setup_logging()


async def main() -> None:
    start_http_server(8000)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_prices, CronTrigger.from_crontab(settings.PRICE_CHECK_CRON))
    scheduler.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
