from aiogram import Router

from bot.handlers import start, subscriptions

router = Router()
router.include_router(start.router)
router.include_router(subscriptions.router)
