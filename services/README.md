# Services

Business logic layer. Each module is independent and has no dependency on bot handlers.

---

## `currency.py` — Currency Conversion

Rates from [open.er-api.com](https://open.er-api.com) (USD base), cached in memory for 1 hour. `convert()` crosses through USD; if either rate is missing, returns `None` and no converted suffix is shown.

**Display:** `users.preferred_currency` (default `USD`); any ISO code present in the live rates dict is valid. Cheapest region is chosen by converted amounts; suffix omitted when the region's native currency already matches.

**PS Store symbols:** `PS_CURRENCY_MAP` (symbol → ISO), `PS_ISO_TO_SYMBOL` (ISO → display symbol); ISO codes absent from the map fall back to the code itself (e.g. `SGD 65.00`).

Used by search and game cards, push notify, `/settings` (validation and suggestions).

---

## `price_history.py` — Sale History

Overview: [`docs/features/price-history.md`](../docs/features/price-history.md). Schema: [`db/models/README.md`](../db/models/README.md#price_history).

Shared rows — one sale per `(game, region)`. **Writes:** worker on price drop; `subscription.py` seeds an active promo on subscribe or new region. **Skips:** unchanged price, increase, duplicate poll at same price.

**Reads:** from user's `subscriptions.created_at`, tracked regions only. Promos hidden until `discount_end`; permanent drops visible immediately. Display date: `discount_end` for promos, `recorded_at` otherwise (`recorded_at` = insert time, not promo start).

**Limits:** 3 per region (push), 10 (detail card); extra rows stay in DB. History date mode from `users.history_display_format`.

Used by `subscription.py`, `worker/tasks/price_check`, subscription handlers, `notify`, settings. Card text: `bot/formatters.py`.
