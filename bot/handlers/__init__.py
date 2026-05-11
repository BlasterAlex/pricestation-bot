from aiogram import Router

from bot.handlers import game_card, regions, search, start, subscriptions

router = Router()
router.include_router(start.router)
router.include_router(regions.router)
router.include_router(search.router)
router.include_router(game_card.router)
router.include_router(subscriptions.router)
