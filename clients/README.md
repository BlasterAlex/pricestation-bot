# Clients

Outbound HTTP adapters for third-party APIs. No bot handlers, no DB sessions.
Domain types (`GameInfo`, `RegionPrice`) come from `services/`; this layer only talks to the network and maps responses into those types.

```
handlers / worker  →  services (domain)  →  clients (HTTP)
```

---

## `ps_store.py` — PlayStation Store GraphQL

Client for `web.np.playstation.com` persisted GraphQL queries.

| Function | Role |
|----------|------|
| `search_games(query, region)` | Universal search; filters to paid `GAME_TYPES` |
| `get_game_info(ps_id, region)` | Product upsell + CTAs → one `(GameInfo, RegionPrice)` or `None` |
| `get_concept_default_product_id(concept_id, region)` | Resolves concept page → default product id |
| `list_concept_editions(concept_id, region)` | Paid editions under a concept (for link edition picker) |

Raises `PSStoreAPIError` on transport / unexpected HTTP failures for concept flows. Search / `get_game_info` keep the historical soft-fail style (`[]` / `None`) where that was already the contract.

Prometheus counters/histograms: `ps_api_*` via `bot.metrics`.

Used by search, subscriptions sync, price-check worker, and `services/ps_link_prices.py`.

---

## `ps_regions.py` — Country selector

Fetches the flat country/locale list from `playstation.com` country-selector JSON (`get_ps_regions`). In-memory cache ~6 hours.

Used by region add / settings flows (`bot/handlers/regions.py`).
