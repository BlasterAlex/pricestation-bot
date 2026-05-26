"""
Grouping effectiveness research script.

For each game in dataset.GAMES, searches all regions in dataset.REGIONS,
applies two-level grouping (ps_id_suffix → composite_key), and classifies
each resulting group:

  suffix_bridged   2+ regions, 2+ distinct composite_keys
                   → suffix was essential; without it these would be separate cards
  composite_merged 2+ regions, 1 composite_key
                   → composite_key alone was sufficient for cross-region merging
  singleton        exactly 1 region
                   → game found in only one region, no cross-region grouping possible

Output:
  research/results.json   raw data
  research/results.txt    human-readable text table
  research/results.png    percentage breakdown chart (requires matplotlib)

Usage (from project root):
  pip install matplotlib          # once, only needed for the chart
  python research/run_grouping_research.py
"""

import asyncio
import io
import json
import sys
from pathlib import Path

import aiohttp

# Force UTF-8 output on Windows consoles
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Make project root importable
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dataset import GAMES, REGIONS  # noqa: E402

from services.ps_store import GameInfo, RegionPrice, _search_games  # noqa: E402

RESEARCH_DIR  = Path(__file__).parent
RESULTS_DIR   = RESEARCH_DIR / "results"

# ── Types ──────────────────────────────────────────────────────────────────────

SearchResult = list[tuple[GameInfo, RegionPrice]]
ResultsByRegion = dict[str, SearchResult]

# Group type labels
SUFFIX_BRIDGED   = "suffix_bridged"
COMPOSITE_MERGED = "composite_merged"
SINGLETON        = "singleton"

GROUP_TYPES = (SUFFIX_BRIDGED, COMPOSITE_MERGED, SINGLETON)

# ── Search ────────────────────────────────────────────────────────────────────

async def search_all_regions(
    session: aiohttp.ClientSession,
    query: str,
) -> ResultsByRegion:
    """Search all regions concurrently and return a {region: results} dict."""
    tasks = [
        asyncio.create_task(_search_games(session, query, r, page_size=30))
        for r in REGIONS
    ]
    all_results = await asyncio.gather(*tasks)
    return dict(zip(REGIONS, all_results))


# ── Two-level grouping ────────────────────────────────────────────────────────

def analyze_game(results_by_region: ResultsByRegion) -> list[dict]:
    """Apply suffix → composite_key grouping and classify each resulting group.

    Mirrors the logic in aggregate_search_results, but instead of building a
    price map it tracks *how* each group was formed so the result can be
    classified as suffix_bridged, composite_merged, or singleton.

    en-us is processed first (moved to front if present) so composite_keys and
    representative titles match what the app would produce.
    """
    # Process en-us first for canonical keys, same as aggregate_search_results
    ordered_regions = (
        ["en-us"] + [r for r in REGIONS if r != "en-us"]
        if "en-us" in results_by_region
        else list(REGIONS)
    )

    by_key: dict[str, dict[str, tuple[GameInfo, RegionPrice]]] = {}
    suffix_to_key: dict[str, str] = {}

    for region in ordered_regions:
        region_results = results_by_region.get(region, [])
        seen_keys: set[str] = set()

        for game, price in region_results:
            sfx = game.ps_id_suffix
            if sfx and sfx in suffix_to_key:
                key = suffix_to_key[sfx]
            else:
                key = game.composite_key
                if sfx:
                    suffix_to_key[sfx] = key

            if key in seen_keys:
                continue
            seen_keys.add(key)

            by_key.setdefault(key, {})[region] = (game, price)

    groups: list[dict] = []
    for key, region_data in by_key.items():
        composite_keys = {g.composite_key for g, _ in region_data.values()}
        suffixes      = {g.ps_id_suffix   for g, _ in region_data.values()
                         if g.ps_id_suffix}
        region_count  = len(region_data)

        if region_count == 1:
            group_type = SINGLETON
        elif len(composite_keys) > 1:
            group_type = SUFFIX_BRIDGED    # suffix merged entries with different titles
        else:
            group_type = COMPOSITE_MERGED  # composite_key alone was sufficient

        # Pick a representative title: prefer ASCII, prefer en-us
        rep_title = (
            region_data.get("en-us", (None, None))[0] or
            next(
                (g for g, _ in region_data.values() if g.title.isascii()),
                next(iter(region_data.values()))[0],
            )
        ).title

        groups.append({
            "key":            key,
            "type":           group_type,
            "region_count":   region_count,
            "regions":        sorted(region_data.keys()),
            "composite_keys": sorted(composite_keys),
            "suffixes":       sorted(suffixes),
            "title":          rep_title,
        })

    groups.sort(key=lambda g: -g["region_count"])
    return groups


# ── Text report ───────────────────────────────────────────────────────────────

def _counts(groups: list[dict]) -> dict[str, int]:
    return {t: sum(1 for g in groups if g["type"] == t) for t in GROUP_TYPES}


def format_report(all_results: list[dict]) -> str:
    col = 46

    # ── Summary table ─────────────────────────────────────────────────────────
    summary: list[str] = [
        "SUMMARY",
        "-" * 90,
        f"  {'Game':<{col}} {'Groups':>6}  {'Suffix':>6}  {'Composite':>9}  {'Singleton':>9}",
        "  " + "-" * 88,
    ]

    total: dict[str, int] = {t: 0 for t in GROUP_TYPES}
    total_groups = 0

    for res in all_results:
        groups = res["groups"]
        c = _counts(groups)
        n = len(groups)
        total_groups += n
        for t in GROUP_TYPES:
            total[t] += c[t]

        flag = "  <!>" if c[SUFFIX_BRIDGED] else ""
        summary.append(
            f"  {res['query']:<{col}} {n:>6}  "
            f"{c[SUFFIX_BRIDGED]:>6}  "
            f"{c[COMPOSITE_MERGED]:>9}  "
            f"{c[SINGLETON]:>9}"
            f"{flag}"
        )

    if total_groups:
        pct = {t: total[t] / total_groups * 100 for t in GROUP_TYPES}
        summary += [
            "  " + "-" * 88,
            f"  {'TOTAL':<{col}} {total_groups:>6}  "
            f"{total[SUFFIX_BRIDGED]:>6}  "
            f"{total[COMPOSITE_MERGED]:>9}  "
            f"{total[SINGLETON]:>9}",
            f"  {'(% of all groups)':<{col}} {'100%':>6}  "
            f"{pct[SUFFIX_BRIDGED]:>5.1f}%  "
            f"{pct[COMPOSITE_MERGED]:>8.1f}%  "
            f"{pct[SINGLETON]:>8.1f}%",
        ]

    return "\n".join(summary)


# ── Chart ─────────────────────────────────────────────────────────────────────

def save_chart(all_results: list[dict], path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — skipping chart (pip install matplotlib)")
        return

    COLORS = {
        SUFFIX_BRIDGED:   "#2ecc71",   # green  — suffix did the work
        COMPOSITE_MERGED: "#3498db",   # blue   — composite_key was enough
        SINGLETON:        "#e67e22",   # orange — no cross-region grouping
    }
    LABELS = {
        SUFFIX_BRIDGED:   "Suffix-bridged",
        COMPOSITE_MERGED: "Composite-merged",
        SINGLETON:        "Singleton (1 region)",
    }

    total_all = {
        t: sum(_counts(r["groups"])[t] for r in all_results)
        for t in GROUP_TYPES
    }
    total_n = sum(total_all.values()) or 1

    pie_vals   = [total_all[t] for t in GROUP_TYPES]
    pie_colors = [COLORS[t]   for t in GROUP_TYPES]
    pie_labels = [
        f"{LABELS[t]}\n{total_all[t]}  ({total_all[t] / total_n * 100:.1f}%)"
        for t in GROUP_TYPES
    ]

    fig, ax = plt.subplots(figsize=(7, 7))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")

    wedges, _ = ax.pie(
        pie_vals,
        colors=pie_colors,
        startangle=90,
        wedgeprops={"linewidth": 1.5, "edgecolor": "#1a1a2e"},
    )
    ax.legend(
        wedges, pie_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.22),
        fontsize=10,
        labelcolor="white",
        framealpha=0,
    )
    ax.set_title(
        "PS Store grouping effectiveness: suffix vs composite_key",
        color="white", fontsize=11, pad=14,
    )

    plt.savefig(path, dpi=120, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"Searching {len(GAMES)} games across {len(REGIONS)} regions...\n")

    connector = aiohttp.TCPConnector(limit=64)
    async with aiohttp.ClientSession(connector=connector) as session:
        all_results: list[dict] = []
        for i, query in enumerate(GAMES, 1):
            print(f"[{i:3d}/{len(GAMES)}] {query} ...", flush=True)
            results_by_region = await search_all_regions(session, query)
            groups = analyze_game(results_by_region)
            all_results.append({"query": query, "groups": groups})
            await asyncio.sleep(0.3)

    print("\nDone. Saving results...\n")

    RESULTS_DIR.mkdir(exist_ok=True)

    # JSON
    json_path = RESULTS_DIR / "results.json"
    json_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Saved: {json_path}")

    # Text report
    report = format_report(all_results)
    txt_path = RESULTS_DIR / "results.txt"
    txt_path.write_text(report, encoding="utf-8")
    print(f"  Saved: {txt_path}")

    # Chart
    png_path = RESULTS_DIR / "results.png"
    save_chart(all_results, png_path)
    print(f"  Saved: {png_path}")

    print()
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
