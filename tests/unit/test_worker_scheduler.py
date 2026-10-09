from unittest.mock import Mock

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from worker.main import register_jobs
from worker.tasks.notify import send_notifications
from worker.tasks.price_check import check_prices


def test_paused_job_uses_configured_misfire_grace(monkeypatch):
    monkeypatch.setattr("worker.main.settings.MISFIRE_GRACE_SECONDS", 90)
    scheduler = AsyncIOScheduler()
    register_jobs(scheduler, Mock())

    jobs = {job.func: job for job in scheduler.get_jobs()}
    assert set(jobs) == {check_prices, send_notifications}
    for job in jobs.values():
        assert job.misfire_grace_time == 90
        assert job.coalesce is True
