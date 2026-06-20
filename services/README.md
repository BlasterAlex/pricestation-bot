# Services

Business logic layer. Each module is independent and has no dependency on bot handlers.

---

## `currency.py` — Currency Conversion

### Exchange rates

Rates are fetched from [open.er-api.com](https://open.er-api.com) using USD as the base:

```
GET https://open.er-api.com/v6/latest/USD
→ { "rates": { "EUR": 0.92, "TRY": 34.1, "UAH": 41.5, ... } }
```

`rates[X]` means: 1 USD = X units of currency X. Rates are cached in memory for 1 hour (`_CACHE_TTL = 3600`).

### Conversion formula

`convert(amount, from_ps_currency, to_iso, rates)` converts between any two currencies using USD as an intermediate:

```
result = amount / rates[from_iso] * rates[to_iso]
```

USD itself is always `1.0` and is handled as a special case (not required to be in the rates dict).

If either rate is missing, `convert` returns `None` and no converted value is displayed.

### Display currency

Each user can set a preferred display currency via `/currency` (stored as `users.preferred_currency`, defaults to `USD`). Any ISO 4217 code present in the exchange rate API response is valid — not limited to PS Store native currencies (e.g. `SGD`, `HKD`, `MYR` are all accepted).

Validation happens at command time against the live rates dict.

The display currency is used in three places:
- **Search results** — converted amount shown next to each native price
- **Game card** — same, plus old prices in price-drop arrows
- **Push notifications** — each notification is rendered in the recipient's own currency

The cheapest region is determined by comparing converted values, so bold highlighting always reflects real purchasing power in the user's chosen currency. The converted suffix is omitted when the region's native currency already matches the display currency.

### `PS_CURRENCY_MAP` and `PS_ISO_TO_SYMBOL`

Two lookup tables map between PS Store price symbols and ISO 4217 codes:

- `PS_CURRENCY_MAP` — PS Store symbol → ISO code (e.g. `"TL" → "TRY"`, `"R$" → "BRL"`)
- `PS_ISO_TO_SYMBOL` — ISO code → display symbol (reverse direction, used for formatting)

Currencies absent from `PS_ISO_TO_SYMBOL` (e.g. `SGD`) fall back to the ISO code itself as the display symbol: `SGD 65.00`.
