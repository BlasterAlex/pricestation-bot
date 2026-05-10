from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    await message.answer(
        "Привет! Я PriceStation — слежу за ценами в PS Store.\n\n"
        "Используй /subscribe чтобы подписаться на игру."
    )
