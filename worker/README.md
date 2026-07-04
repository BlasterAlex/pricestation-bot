# Worker Jobs

The `worker` service runs two background jobs on a cron schedule via [APScheduler](https://apscheduler.readthedocs.io/).

---

## Jobs

### `check_prices` - Price Check

**Schedule:** `PRICE_CHECK_CRON` (default: `0 */4 * * *` - every 4 hours at :00)

Iterates over all `game_regions` that have at least one subscriber and fetches the current price from the PS Store GraphQL API.

For each `GameRegion`:
1. Calls `get_game_info(ps_id, region_code)` against the PS Store API.
2. Compares the new price with `current_price` stored in the DB.
3. If the price dropped:
   - Saves `old_price = current_price`, updates `current_price`.
   - Inserts a row into `price_drops` (`ON CONFLICT DO NOTHING` - one pending drop per game at a time).
   - Inserts a row into `price_history` (including `discount_end` when the API provides it) — see [`services/README.md`](../services/README.md#price_historypy--sale-history).
4. Updates `base_price`, `discount_text`, `discount_end`, `last_checked`, and game metadata.

---

### `send_notifications` - Notification Dispatch

**Schedule:** `NOTIFY_CRON` (default: `10 */4 * * *` - every 4 hours at :10)

Picks up pending `price_drops` and sends Telegram notifications to subscribers.

For each pending `PriceDrop`:
1. Reads current prices from `game_regions` for the game.
2. For each subscriber, filters to regions the user tracks.
3. Calls `notify_price_drop` (sends a photo or text message via aiogram). Each notification is personalised: prices are converted to the user's `preferred_currency` (defaults to `USD`), the cheapest region is highlighted in bold based on those converted values, old prices (shown with a ↓ arrow) are converted to the same currency, and a past sales block is included when ended-sale history exists — see [`docs/features/price-history.md`](../docs/features/price-history.md).
4. Marks `price_drop.notified_at` regardless of per-user failures, to prevent duplicate notifications.

---

## Aggregation Window

PS Store sales often roll out to different regions across multiple check cycles. Without protection, a single sale would trigger two separate notifications - one when the first regions drop, another when the remaining regions catch up.

```
00:00  uk-ua drops → PriceDrop #1 created
00:10  notify job: PriceDrop #1 is 10 min old → withheld (< 9h)
04:10  notify job: 4h10m old → withheld
08:00  en-us drops → ON CONFLICT DO NOTHING (PriceDrop #1 still pending)
       game_regions.current_price for en-us updated ✓
09:10  notify job: 9h10m old → SENT - all regions included in one message ✓
```

The key insight: `PriceDrop` is just a trigger - it doesn't store prices. The notification job reads live prices from `game_regions` at send time, so by the time the drop is released, all regional prices are already up to date.

**Setting:** `NOTIFY_AGGREGATION_HOURS` (default: `9`). Should be greater than the gap between the first and last regional price update for a typical sale - usually one or two check cycles.

---

## Configuration Reference

| Variable                   | Default        | Effect                                  |
|----------------------------|----------------|-----------------------------------------|
| `PRICE_CHECK_CRON`         | `0 */4 * * *`  | How often prices are fetched            |
| `NOTIFY_CRON`              | `10 */4 * * *` | How often pending drops are dispatched  |
| `NOTIFY_AGGREGATION_HOURS` | `9`            | Minimum age of a drop before it is sent |

---

## Price Drop Flow (end-to-end)

```
PS Store API
    │
    │  get_game_info(ps_id, region)
    ▼
check_prices job
    │
    ├─ price unchanged → update last_checked, done
    │
    └─ price dropped
           │
           ├─ update game_region (current_price, old_price, ...)
           └─ INSERT INTO price_drops ON CONFLICT DO NOTHING
                          │
                          │  (pending, withheld for NOTIFY_AGGREGATION_HOURS)
                          ▼
               send_notifications job
                          │
                          ├─ read all game_regions for the game
                          ├─ for each subscriber → send Telegram message
                          └─ set price_drop.notified_at
```
