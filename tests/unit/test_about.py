from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.handlers.about import ISSUES_URL, cmd_about


async def test_about_links_to_github_issues():
    message = SimpleNamespace(answer=AsyncMock())

    await cmd_about(message)

    text = message.answer.await_args.args[0]
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert ISSUES_URL in text
    assert "GitHub Issues" in text
    assert markup.inline_keyboard[0][0].url == ISSUES_URL
    assert markup.inline_keyboard[0][0].text == "Open Issues"
