"""Unit tests for aggregate_search_results — the two-level grouping logic."""

from bot.handlers.search import aggregate_search_results
from services.ps_store import GameInfo, RegionPrice

# ── helpers ────────────────────────────────────────────────────────────────────

def _game(
    title: str, platforms: list[str] | None = None, type_: str = "FULL_GAME", ps_id_suffix: str | None = None
) -> GameInfo:
    return GameInfo(title=title, platforms=platforms or ["PS5"], type=type_, cover_url=None, ps_id_suffix=ps_id_suffix)


def _price(ps_id: str | None = None, price: float = 49.99) -> RegionPrice:
    return RegionPrice(price=price, currency="$", base_price=None,
                       discount_text=None, ps_id=ps_id)


# ── Level 1: suffix grouping ───────────────────────────────────────────────────

def test_same_suffix_different_composite_key_merges():
    """Localised titles with the same ps_id suffix collapse into one card."""
    en = _game("FC 25 Standard Edition PS4 & PS5", ps_id_suffix="25STANDARDBUNDLE")
    es = _game("FC 25 Edición Estándar para PS4 y PS5", ps_id_suffix="25STANDARDBUNDLE")
    assert en.composite_key != es.composite_key

    by_key, rep_game, _ = aggregate_search_results(
        ["en-us", "es-mx"],
        [
            [(en, _price("UP0006-PPSA20049_00-25STANDARDBUNDLE"))],
            [(es, _price("EP0006-PPSA20050_00-25STANDARDBUNDLE"))],
        ],
    )

    assert len(by_key) == 1
    key = next(iter(by_key))
    assert "en-us" in by_key[key]
    assert "es-mx" in by_key[key]


def test_suffix_canonical_key_is_first_seen():
    """The region processed first claims the canonical key for a suffix."""
    en = _game("FC 25 Standard Edition PS4 & PS5", ps_id_suffix="25STANDARDBUNDLE")
    es = _game("FC 25 Edición Estándar para PS4 y PS5", ps_id_suffix="25STANDARDBUNDLE")

    by_key, rep_game, _ = aggregate_search_results(
        ["en-us", "es-mx"],
        [
            [(en, _price("UP0006-PPSA20049_00-25STANDARDBUNDLE"))],
            [(es, _price("EP0006-PPSA20050_00-25STANDARDBUNDLE"))],
        ],
    )

    assert en.composite_key in by_key  # first region's key wins


def test_suffix_prefers_ascii_rep_game():
    """Representative GameInfo uses ASCII title even when non-ASCII region is first."""
    localized = _game("Набір FC 25 PS5", ps_id_suffix="25STANDARDBUNDLE")
    english = _game("FC 25 Standard Edition PS5", ps_id_suffix="25STANDARDBUNDLE")

    # en-us is in region_codes so it's moved to front and becomes canonical
    _, rep_game, _ = aggregate_search_results(
        ["ru-ru", "en-us"],
        [
            [(localized, _price("EP0006-PPSA20050_00-25STANDARDBUNDLE"))],
            [(english,   _price("UP0006-PPSA20049_00-25STANDARDBUNDLE"))],
        ],
    )

    assert len(rep_game) == 1
    assert next(iter(rep_game.values())).title == "FC 25 Standard Edition PS5"


def test_us_results_canonical_title_used():
    """en-us rep_game title is used even when en-us is not in user regions."""
    localized = _game("FC 25 Edición Estándar PS5", ps_id_suffix="25STANDARDBUNDLE")
    us_game   = _game("FC 25 Standard Edition PS5", ps_id_suffix="25STANDARDBUNDLE")

    _, rep_game, _ = aggregate_search_results(
        ["es-mx"],
        [[(localized, _price("EP0006-PPSA20050_00-25STANDARDBUNDLE"))]],
        us_results=[(us_game, _price("UP0006-PPSA20049_00-25STANDARDBUNDLE"))],
    )

    assert len(rep_game) == 1
    assert next(iter(rep_game.values())).title == "FC 25 Standard Edition PS5"


def test_us_results_prices_not_shown_to_user():
    """en-us prices are hidden when en-us is not in the user's regions."""
    localized = _game("FC 25 Edición Estándar PS5", ps_id_suffix="25STANDARDBUNDLE")
    us_game   = _game("FC 25 Standard Edition PS5", ps_id_suffix="25STANDARDBUNDLE")

    by_key, _, _ = aggregate_search_results(
        ["es-mx"],
        [[(localized, _price("EP0006-PPSA20050_00-25STANDARDBUNDLE", price=59.99))]],
        us_results=[(us_game, _price("UP0006-PPSA20049_00-25STANDARDBUNDLE", price=69.99))],
    )

    key = next(iter(by_key))
    assert "en-us" not in by_key[key]
    assert "es-mx" in by_key[key]


def test_us_results_canonical_key_claimed_by_us():
    """Suffix canonical key is en-us composite_key when us_results provided."""
    localized = _game("FC 25 Edición Estándar PS5", ps_id_suffix="25STANDARDBUNDLE")
    us_game   = _game("FC 25 Standard Edition PS5", ps_id_suffix="25STANDARDBUNDLE")

    by_key, _, _ = aggregate_search_results(
        ["es-mx"],
        [[(localized, _price("EP0006-PPSA20050_00-25STANDARDBUNDLE"))]],
        us_results=[(us_game, _price("UP0006-PPSA20049_00-25STANDARDBUNDLE"))],
    )

    assert us_game.composite_key in by_key


def test_us_results_none_falls_back_to_ascii_preference():
    """When us_results is None and en-us not in user regions, ASCII preference applies."""
    localized = _game("Набір Lies of P PS5")
    english   = _game("Lies of P PS5")

    _, rep_game, _ = aggregate_search_results(
        ["ru-ru", "en-gb"],
        [
            [(localized, _price("EP1672-PPSA00001_00-0000000000000001"))],
            [(english,   _price("EP1672-PPSA00001_00-0000000000000002"))],
        ],
        us_results=None,
    )

    assert next(iter(rep_game.values())).title == "Lies of P PS5"


def test_us_in_user_regions_prices_shown():
    """When en-us is a user region its prices appear in by_key normally."""
    us_game = _game("FC 25 Standard Edition PS5", ps_id_suffix="25STANDARDBUNDLE")
    es_game = _game("FC 25 Edición Estándar PS5", ps_id_suffix="25STANDARDBUNDLE")

    by_key, _, _ = aggregate_search_results(
        ["en-us", "es-mx"],
        [
            [(us_game, _price("UP0006-PPSA20049_00-25STANDARDBUNDLE", price=69.99))],
            [(es_game, _price("EP0006-PPSA20050_00-25STANDARDBUNDLE", price=59.99))],
        ],
        us_results=None,  # already in region_codes
    )

    key = next(iter(by_key))
    assert "en-us" in by_key[key]
    assert "es-mx" in by_key[key]


def test_multiple_suffixes_stay_separate():
    """Two products with different suffixes produce two cards."""
    standard = _game("FC 25 Standard Edition PS5", ps_id_suffix="25STANDARDBUNDLE")
    ultimate = _game("FC 25 Ultimate Edition PS5", ps_id_suffix="25ULTIMATEBUNDLE")

    by_key, _, _ = aggregate_search_results(
        ["en-us", "en-gb"],
        [
            [(standard, _price("UP0006-PPSA20049_00-25STANDARDBUNDLE"))],
            [(ultimate, _price("UP0006-PPSA20051_00-25ULTIMATEBUNDLE"))],
        ],
    )

    assert len(by_key) == 2


def test_suffix_collects_all_region_prices():
    """All regional prices end up under the canonical key."""
    regions = ["en-us", "es-mx", "fr-fr", "de-de"]
    games = [
        _game("FC 25 Standard Edition PS4 & PS5", ps_id_suffix="25STANDARDBUNDLE"),
        _game("FC 25 Edición Estándar para PS4 y PS5", ps_id_suffix="25STANDARDBUNDLE"),
        _game("FC 25 Édition Standard pour PS4 et PS5", ps_id_suffix="25STANDARDBUNDLE"),
        _game("FC 25 Standard Edition PS4 & PS5", ps_id_suffix="25STANDARDBUNDLE"),
    ]
    prices = [
        _price(f"UP0006-PPSA{i:05d}_00-25STANDARDBUNDLE", 59.99)
        for i in range(4)
    ]

    by_key, _, _ = aggregate_search_results(
        regions,
        [[(g, p)] for g, p in zip(games, prices)],
    )

    assert len(by_key) == 1
    key = next(iter(by_key))
    assert set(by_key[key].keys()) == set(regions)


# ── Level 2: composite_key fallback ───────────────────────────────────────────

def test_no_suffix_groups_by_composite_key():
    """Without suffixes, same composite_key collapses across regions."""
    g1 = _game("Lies of P")
    g2 = _game("Lies of P")
    assert g1.composite_key == g2.composite_key

    by_key, _, _ = aggregate_search_results(
        ["en-us", "en-gb"],
        [
            [(g1, _price("UP1685-PPSA00001_00-4396566144501976"))],
            [(g2, _price("EP1672-PPSA00001_00-9137597337715830"))],
        ],
    )

    assert len(by_key) == 1
    assert "en-us" in next(iter(by_key.values()))
    assert "en-gb" in next(iter(by_key.values()))


def test_no_suffix_different_composite_key_stays_separate():
    """Different editions without suffix produce separate cards."""
    standard = _game("Lies of P", type_="FULL_GAME")
    bundle = _game("Lies of P: Overture Bundle", type_="GAME_BUNDLE")

    by_key, _, _ = aggregate_search_results(
        ["en-us"],
        [
            [(standard, _price(None)), (bundle, _price(None))],
        ],
    )

    assert len(by_key) == 2


def test_no_suffix_ps_id_still_recorded():
    """ps_ids_by_key is populated even without a suffix."""
    g = _game("Lies of P")

    _, _, ps_ids = aggregate_search_results(
        ["en-us"],
        [[(g, _price("UP1685-PPSA00001_00-4396566144501976"))]],
    )

    key = g.composite_key
    assert ps_ids[key]["en-us"] == "UP1685-PPSA00001_00-4396566144501976"


# ── Mixed: suffix + no-suffix in same batch ───────────────────────────────────

def test_suffix_and_no_suffix_games_coexist():
    """FC 25 (has suffix) and Lies of P (no matching suffix) stay independent."""
    fc_en = _game("FC 25 Standard Edition PS5", ps_id_suffix="25STANDARDBUNDLE")
    fc_es = _game("FC 25 Edición Estándar PS5", ps_id_suffix="25STANDARDBUNDLE")
    lop   = _game("Lies of P")

    by_key, _, _ = aggregate_search_results(
        ["en-us", "es-mx", "en-gb"],
        [
            [(fc_en, _price("UP0006-PPSA20049_00-25STANDARDBUNDLE")),
             (lop,   _price("UP1685-PPSA00001_00-4396566144501976"))],
            [(fc_es, _price("EP0006-PPSA20050_00-25STANDARDBUNDLE"))],
            [(lop,   _price("EP1672-PPSA00002_00-9137597337715830"))],
        ],
    )

    # FC 25 → 1 card; Lies of P → 1 card
    assert len(by_key) == 2
    fc_key = fc_en.composite_key
    lop_key = lop.composite_key
    assert set(by_key[fc_key].keys()) == {"en-us", "es-mx"}
    assert set(by_key[lop_key].keys()) == {"en-us", "en-gb"}


# ── Edge cases ─────────────────────────────────────────────────────────────────

def test_empty_results():
    by_key, rep_game, ps_ids = aggregate_search_results(
        ["en-us", "en-gb"], [[], []]
    )
    assert by_key == {}
    assert rep_game == {}
    assert ps_ids == {}


def test_price_without_ps_id_not_added_to_ps_ids():
    g = _game("Some Game")
    _, _, ps_ids = aggregate_search_results(
        ["en-us"],
        [[(g, _price(None))]],
    )
    assert ps_ids == {}


def test_same_region_multiple_games_all_recorded():
    """Multiple games from one region all appear in the output."""
    g1 = _game("Game One", ps_id_suffix="GAME1SUFFIX00")
    g2 = _game("Game Two", ps_id_suffix="GAME2SUFFIX00")

    by_key, rep_game, _ = aggregate_search_results(
        ["en-us"],
        [[(g1, _price("UP0001-X_00-GAME1SUFFIX00")),
          (g2, _price("UP0001-X_00-GAME2SUFFIX00"))]],
    )

    assert len(by_key) == 2
    assert len(rep_game) == 2
