from aiogram import Router

from bot.handlers import regions, start, subscriptions

router = Router()
router.include_router(start.router)
router.include_router(regions.router)
router.include_router(subscriptions.router)
