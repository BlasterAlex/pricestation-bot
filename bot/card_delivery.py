import re

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

CAPTION_LIMIT = 1024

# Telegram HTML tags. Longer names are safe next to short ones because of the word boundary.
_TAG = re.compile(
    r"</?(?:blockquote|strong|strike|tg-spoiler|tg-emoji|code|pre|span|del|ins|em|a|b|i|u|s)\b[^<>]*>",
    re.IGNORECASE,
)
_ENTITY = re.compile(r"&(?:(lt|gt|amp|quot)|#(\d+)|#x([0-9a-fA-F]+));", re.IGNORECASE)
_NAMED = {"lt": "<", "gt": ">", "amp": "&", "quot": '"'}


def _entity_repl(match: re.Match[str]) -> str:
    named, decimal, hexa = match.group(1), match.group(2), match.group(3)
    if named:
        return _NAMED[named.lower()]
    code = int(decimal) if decimal is not None else int(hexa, 16)
    if code > 0x10FFFF:
        return match.group(0)
    return chr(code)


def caption_length(html: str) -> int:
    """Length Telegram uses for a caption: visible text after HTML parsing, in UTF-16 code units."""
    visible = _ENTITY.sub(_entity_repl, _TAG.sub("", html))
    return len(visible.encode("utf-16-le")) // 2


async def send_card(
    chat,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    cover_url: str | None,
) -> None:
    if cover_url and caption_length(text) <= CAPTION_LIMIT:
        await chat.answer_photo(photo=cover_url, caption=text, reply_markup=reply_markup)
        return
    await chat.answer(text, reply_markup=reply_markup)


class BotChat:
    """Bot.send_* with the same shape as Message.answer / answer_photo."""

    def __init__(self, bot: Bot, chat_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def answer(self, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        await self._bot.send_message(self._chat_id, text, reply_markup=reply_markup)

    async def answer_photo(
        self,
        *,
        photo: str,
        caption: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        await self._bot.send_photo(self._chat_id, photo, caption=caption, reply_markup=reply_markup)
