from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from services.user import get_or_create_user

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    await get_or_create_user(session, message.from_user.id, message.from_user.username)
    await session.commit()
    await message.answer(
        "Hi! I'm PriceStation — I track prices in the PS Store.\n\n"
        "Use /add_region to choose the regions you want to follow."
    )
