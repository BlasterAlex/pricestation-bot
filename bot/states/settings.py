from aiogram.fsm.state import State, StatesGroup


class SettingsForm(StatesGroup):
    waiting_for_currency = State()
