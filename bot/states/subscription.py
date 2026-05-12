from aiogram.fsm.state import State, StatesGroup


class SubscriptionForm(StatesGroup):
    waiting_for_game = State()
    waiting_for_region = State()
    waiting_for_target_price = State()


class RegionForm(StatesGroup):
    waiting_for_search = State()


class SearchForm(StatesGroup):
    waiting_for_query = State()
    showing_results = State()
