# Grouping Research

Study of two-level PS Store search result grouping effectiveness.

**Problem:** the same game returns different search results in different regions - different product IDs, different localized titles, sometimes even different platform labels. 

**Solution:** the grouping strategy must collapse all regional variants into a single card without false-positive merges.

---

## Level 1 - `ps_id_suffix` (primary key)

PS Store product IDs follow the pattern `{PREFIX}-{CONCEPT_ID}-{SUFFIX}`:

```
UP0006-PPSA20049_00-25STANDARDBUNDLE   ← US edition
EP0006-PPSA20050_00-25STANDARDBUNDLE   ← EU edition
```

The **suffix** (`25STANDARDBUNDLE`) is the trailing segment after the last `-`.
It encodes the specific product (edition + content) and is **identical across all regional prefixes** (`UP`, `EP`, `JP`, `KP`) for the same product.
This makes it a reliable cross-region identity key even when titles differ completely:

| Region  | Title                         | ps_id_suffix        |
|---------|-------------------------------|---------------------|
| `en-us` | FC 25 Standard Edition PS5    | `25STANDARDBUNDLE`  |
| `es-mx` | FC 25 Edición Estándar PS5    | `25STANDARDBUNDLE`  |
| `de-de` | FC 25 Standardedition PS5     | `25STANDARDBUNDLE`  |

Extraction: `ps_id.rsplit("-", 1)[-1]` - takes everything after the last hyphen.

**Fails when:** some regions assign a unique suffix per market (certain JP/KR exclusives, or bundles that differ by content per region). These fall through to Level 2.

---

## Level 2 - `composite_key` (fallback)

Built from three normalized fields:

```
composite_key = normalize_title(title) + "_" + type.lower() + "_" + "_".join(sorted(platforms))
```

**`normalize_title`** pipeline:
1. Lowercase the title.
2. Strip punctuation: `™ ® © : ( ) . , ' " ! ? - /`
3. Collapse and remove all whitespace.
4. Strip non-ASCII characters (Cyrillic, Japanese, Korean, etc.).
5. If the ASCII result is shorter than 3 characters (fully non-ASCII title), fall back to keeping
   the non-ASCII characters instead.

Examples:

| Input title                          | composite_key                            |
|--------------------------------------|------------------------------------------|
| `God of War: Ragnarök™`              | `godofwarragnarok_full_game_ps5`         |
| `FINAL FANTASY XVI`                  | `finalfantasyxvi_full_game_ps5`          |
| `Набір FINAL FANTASY VII REMAKE ...` | `finalfantasyviiremake..._full_game_ps5` |
| `バルダーズ・ゲート3`                         | `バルダーズゲート3_full_game_ps5` *(fallback)*   |

Works well for games with consistent English titles across regions. Fails when:
- The same game has genuinely different edition names in different regions (handled by suffix).
- A title is fully non-ASCII in one region and ASCII in another (produces different keys).

---

## Grouping Priority

Regions are processed in order, always starting with `en-us` (canonical source for titles).
For each game result:

```
game.ps_id_suffix is not None
  AND this suffix was already seen in an earlier result?
    ├─ yes → Level 1: merge into that suffix's group
    └─ no  → Level 2: use composite_key as the group key
                 └─ if suffix is not None → register it
                      (next region with the same suffix will hit Level 1)
```

The first region to produce a suffix **claims** its `composite_key` as the canonical group key.
All subsequent regions with the same suffix are merged into that group regardless of their own
`composite_key` (i.e. regardless of how different their localized title is).

Within a group, **`en-us` unconditionally wins the representative `GameInfo`** (title, cover).
When `en-us` has no result for a game, the ASCII title is preferred over non-ASCII.

## Contents

| File                       | Description                                              |
|----------------------------|----------------------------------------------------------|
| `dataset.py`               | Regions list and ~100 game titles with category comments |
| `run_grouping_research.py` | Script: searches all regions, analyses groupings         |
| `requirements.txt`         | Script dependencies (`aiohttp`, `matplotlib`)            |
| `results/results.json`     | Raw script output (overwritten on each run)              |
| `results/results.txt`      | Human-readable summary report                            |
| `results/results.png`      | Pie chart: group type distribution                       |

## Usage

```bash
# install research dependencies (once)
pip install -r research/requirements.txt

python research/run_grouping_research.py
```

Results are written to `research/results/`.

## Regions

32 regions covering North America, Europe, Latin America, Asia-Pacific, and the Middle East.

## What We're Measuring

- How many groups each game produces under suffix grouping vs. composite_key only
- Which games correctly collapse into one card across all regions, and which don't
- Where grouping breaks down - spurious duplicates or incorrect merges

## Chart

![Group type distribution](results/results.png)

## Results Format

### `results.txt` - summary table

| Column      | Description                                                                                                   |
|-------------|---------------------------------------------------------------------------------------------------------------|
| `Groups`    | Total number of distinct groups produced for this game                                                        |
| `Suffix`    | Groups formed via `ps_id_suffix` - suffix was essential to merge localised variants                           |
| `Composite` | Groups formed via `composite_key` alone - title/type/platforms matched across regions without a shared suffix |
| `Singleton` | Groups with exactly one region - game found in only one market, no cross-region merge possible                |
| `<!>`       | Flag: at least one suffix-bridged group exists (suffix grouping was needed)                                   |

### `results.json` - raw data

Full per-game detail: all groups with `type`, `region_count`, `regions`, `suffixes`, `composite_keys`, and representative `title`.

### Group types

| Type               | Condition                                | Meaning                                                                       |
|--------------------|------------------------------------------|-------------------------------------------------------------------------------|
| `SUFFIX_BRIDGED`   | 2+ regions, 2+ distinct `composite_key`s | Localised titles differ - suffix was the only way to merge them into one card |
| `COMPOSITE_MERGED` | 2+ regions, 1 `composite_key`            | Title is consistent across regions - composite key alone was sufficient       |
| `SINGLETON`        | exactly 1 region                         | Region-exclusive edition, bundle, or false-positive search result             |
