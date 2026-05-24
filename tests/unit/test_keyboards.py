from bot.keyboards.inline import subscribe_keyboard, subscriptions_list_keyboard, unsubscribe_keyboard
from services.ps_store import GameInfo


def _game(title: str = "Test Game", type_: str = "FULL_GAME") -> GameInfo:
    return GameInfo(title=title, platforms=["PS5"], type=type_, cover_url=None)


def test_subscribe_keyboard():
    kb = subscribe_keyboard(7)
    button = kb.inline_keyboard[0][0]
    assert button.text == "🔔 Subscribe"
    assert button.callback_data == "subscribe:7"


def test_unsubscribe_keyboard():
    kb = unsubscribe_keyboard(42)
    button = kb.inline_keyboard[0][0]
    assert button.text == "🔕 Unsubscribe"
    assert button.callback_data == "unsubscribe:42"


# ── subscriptions_list_keyboard ───────────────────────────────────────────────

def test_subscriptions_list_keyboard_game_buttons():
    games = [_game(f"Game {i}") for i in range(3)]
    kb = subscriptions_list_keyboard(games, page=0, total_pages=1)
    rows = kb.inline_keyboard
    assert len(rows) == 3
    for i, row in enumerate(rows):
        assert row[0].callback_data == f"game_select:{i}"
        assert f"Game {i}" in row[0].text


def test_subscriptions_list_keyboard_game_button_emoji():
    kb = subscriptions_list_keyboard([_game(type_="PREMIUM_EDITION")], page=0, total_pages=1)
    assert kb.inline_keyboard[0][0].text.startswith("💎")


def test_subscriptions_list_keyboard_no_nav_when_single_page():
    kb = subscriptions_list_keyboard([_game()], page=0, total_pages=1)
    all_callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert not any("subs_page" in c for c in all_callbacks)


def test_subscriptions_list_keyboard_nav_first_page():
    kb = subscriptions_list_keyboard([_game()], page=0, total_pages=3)
    nav_callbacks = [btn.callback_data for btn in kb.inline_keyboard[-1]]
    assert "subs_page:1" in nav_callbacks
    assert "subs_page:-1" not in nav_callbacks
    assert not any(c == "subs_page:0" for c in nav_callbacks)


def test_subscriptions_list_keyboard_nav_last_page():
    kb = subscriptions_list_keyboard([_game()], page=2, total_pages=3)
    nav_callbacks = [btn.callback_data for btn in kb.inline_keyboard[-1]]
    assert "subs_page:1" in nav_callbacks
    assert "subs_page:3" not in nav_callbacks


def test_subscriptions_list_keyboard_nav_middle_page():
    kb = subscriptions_list_keyboard([_game()], page=1, total_pages=3)
    nav_callbacks = [btn.callback_data for btn in kb.inline_keyboard[-1]]
    assert "subs_page:0" in nav_callbacks
    assert "subs_page:2" in nav_callbacks


def test_subscriptions_list_keyboard_page_indicator():
    kb = subscriptions_list_keyboard([_game()], page=1, total_pages=5)
    nav = kb.inline_keyboard[-1]
    indicator = next(btn for btn in nav if "/" in btn.text)
    assert indicator.text == "2 / 5"
    assert indicator.callback_data == "noop"
