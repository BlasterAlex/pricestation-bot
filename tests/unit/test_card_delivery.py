from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.card_delivery import CAPTION_LIMIT, caption_length, send_card

COVER = "https://example.com/cover.jpg"


def test_link_target_is_not_counted():
    url = "https://store.playstation.com/en-gb/product/" + ("X" * 500)
    html = f'<a href="{url}">€29.99</a>'
    assert caption_length(html) == caption_length("€29.99")


def test_nested_tags_are_not_counted():
    assert caption_length("<b><s><i>ab</i></s></b>") == 2


def test_named_html_entities_count_as_decoded_characters():
    assert caption_length("&lt;&amp;&gt;&quot;") == 4


def test_numeric_html_entity_counts_as_one_character():
    assert caption_length("&#60;") == 1


def test_emoji_counts_in_utf16_code_units():
    assert caption_length("🔔") == 2
    assert caption_length("🇬🇧") == 4


def test_caption_limit_boundary_uses_utf16_length():
    bells = "🔔" * 512
    assert len(bells) < CAPTION_LIMIT
    assert caption_length(bells) == CAPTION_LIMIT
    assert caption_length(bells + "🔔") == CAPTION_LIMIT + 2


@pytest.mark.asyncio
async def test_send_card_sends_photo_when_visible_text_fits():
    message = AsyncMock()
    keyboard = MagicMock()
    text = '<a href="' + ("u" * 5000) + '">ok</a>'

    await send_card(message, text, keyboard, COVER)

    message.answer_photo.assert_awaited_once_with(
        photo=COVER,
        caption=text,
        reply_markup=keyboard,
    )
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_card_sends_text_when_no_cover():
    message = AsyncMock()
    keyboard = MagicMock()

    await send_card(message, "card", keyboard, None)

    message.answer.assert_awaited_once_with("card", reply_markup=keyboard)
    message.answer_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_card_sends_text_only_when_utf16_length_exceeds_limit():
    message = AsyncMock()
    keyboard = MagicMock()
    text = "🔔" * 513

    await send_card(message, text, keyboard, COVER)

    message.answer.assert_awaited_once_with(text, reply_markup=keyboard)
    message.answer_photo.assert_not_awaited()
