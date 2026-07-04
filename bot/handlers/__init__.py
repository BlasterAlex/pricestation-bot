from aiogram import Router

from bot.handlers import regions, search, settings, start, subscriptions

router = Router()
router.include_router(start.router)
router.include_router(settings.router)
router.include_router(regions.router)
router.include_router(search.router)
router.include_router(subscriptions.router)
