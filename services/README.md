# Services

Domain / business-logic layer. No Telegram handlers. Prefer calling `clients/` for outbound HTTP rather than embedding it here.

External PlayStation HTTP lives in [`clients/`](../clients/README.md).

---

## `currency.py` — Currency conversion

Rates from [open.er-api.com](https://open.er-api.com) (USD base), cached ~1 hour. `convert()` crosses through USD; missing rates → `None` (no converted suffix).

**Display:** `users.preferred_currency` (default `USD`). Cheapest region uses converted amounts; suffix omitted when the region’s native currency already matches.

**PS Store symbols:** `PS_CURRENCY_MAP` / `PS_ISO_TO_SYMBOL`.

Used by search and game cards, push notify, `/settings`.

---

## `ps_store.py` — Store domain models & ID helpers

| Piece | Role |
|-------|------|
| `GameInfo`, `RegionPrice` | Shared product/price DTOs (+ `to_dict` / `from_dict`) |
| `ps_id_build_id` | Build ID for save-compatibility grouping |
| `ps_id_suffix` | Product suffix for cross-region card merge |
| `preferred_ps_prefix` / `remap_ps_id_prefix` / `best_ps_id` | Regional UP/EP/JP/KP id selection |
| `is_effectively_ascii` | Title preference helper |

Overview: [`docs/features/cross-region-saves.md`](../docs/features/cross-region-saves.md).  
HTTP/GQL: [`clients/ps_store.py`](../clients/ps_store.py).

---

## `ps_store_url.py` — Store URL parsing

`parse_ps_store_url` → `PsStoreLink` (`PsStoreLinkKind` + locale / ids). Pure string parse; no network.

Overview: [`docs/features/ps-store-links.md`](../docs/features/ps-store-links.md).

---

## `ps_link_prices.py` — Multi-region prices from a seed product

`prices_for_tracked_regions(game, seed_ps_id, seed_locale, region_codes)`: remap prefix → `get_game_info`, else title search matched by suffix / `composite_key`. Concurrent per region; failed regions omitted.

Used by the PS Store link handler.

---

## `subscription.py` — Subscribe / list / region sync

Create and remove subscriptions, paginated “my games”, and `sync_subscriptions_for_new_region` when the user adds a storefront.

Uses `clients.ps_store` for live prices and `price_history` to seed active promos on subscribe.

---

## `price_history.py` — Sale history

Overview: [`docs/features/price-history.md`](../docs/features/price-history.md). Schema: [`db/models/README.md`](../db/models/README.md#price_history).

One shared row per `(game, region)` sale. Worker writes on drops; subscribe / new-region sync can seed an active promo. Display rules and limits for push vs detail card live here.

---

## `price.py` — Price-check helpers

`is_price_dropped`, `get_game_regions_to_check`, `get_pending_drops` for the worker notify pipeline.

---

## `region.py` — Tracked regions

`get_or_create_region`, `get_user_regions`, `add_user_region`, `remove_user_region`.

Country catalog for the add-region UI comes from [`clients/ps_regions.py`](../clients/ps_regions.py).

---

## `user.py` — Bot users

`get_or_create_user` (Telegram id → DB user). Callers must `session.commit()` after create.

---

## `notifier.py` — Outbound Telegram notifications

`notify_price_drop` — formats and sends a price-drop message (used by the worker).
