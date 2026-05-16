from bot.keyboards.inline import game_card_keyboard


def test_game_card_keyboard_subscribe_by_default():
    kb = game_card_keyboard(0)
    button = kb.inline_keyboard[0][0]
    assert button.text == "🔔 Subscribe"
    assert button.callback_data == "subscribe:0"


def test_game_card_keyboard_unsubscribe():
    kb = game_card_keyboard(3, is_subscribed=True)
    button = kb.inline_keyboard[0][0]
    assert button.text == "🔕 Unsubscribe"
    assert button.callback_data == "unsubscribe:3"


def test_game_card_keyboard_index_in_callback():
    kb = game_card_keyboard(7)
    assert kb.inline_keyboard[0][0].callback_data == "subscribe:7"
