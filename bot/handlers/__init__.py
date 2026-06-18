from aiogram import Router

from bot.handlers import currency, regions, search, start, subscriptions

router = Router()
router.include_router(start.router)
router.include_router(currency.router)
router.include_router(regions.router)
router.include_router(search.router)
router.include_router(subscriptions.router)
