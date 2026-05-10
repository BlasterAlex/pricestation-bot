from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, session: AsyncSession) -> None:
    await message.answer("Введите название игры для поиска:")


@router.message(Command("my"))
async def cmd_my_subscriptions(message: Message, session: AsyncSession) -> None:
    await message.answer("Ваши подписки:")
