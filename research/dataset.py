"""
Research dataset: regions and game titles for the grouping effectiveness study.

Used by run_grouping_research.py to evaluate suffix-based vs composite_key-based
grouping across the full set of PS Store regions.
"""

REGIONS = [
    "en-us", "en-gb", "en-au", "en-ca", "en-in", "en-sg", "en-za",
    "ja-jp", "ko-kr",
    "de-de", "fr-fr", "es-es", "it-it", "nl-nl", "pl-pl", "sv-se",
    "pt-br", "es-mx", "es-ar", "es-cl", "es-co",
    "tr-tr", "ru-ru", "ar-ae",
    "zh-hk", "zh-tw",
    "pt-pt", "fr-be", "nl-be", "fr-ch", "de-ch", "de-at",
]

GAMES = [
    # ── Sports (heavy suffix / regional variant patterns) ─────────────────────
    # FC / sports titles are among the hardest to group: each region has its own
    # localised title and often a distinct product ID, yet the suffix (e.g.
    # 25STANDARDBUNDLE) is shared. Good stress-test for Level-1 grouping.
    "EA Sports FC 25",
    "Madden NFL 25",
    "WWE 2K25",
    "EA Sports College Football 25",
    "NBA 2K25",
    "MLB The Show 25",
    "UFC 5",
    "F1 24",
    "PGA Tour 2K25",
    "NHL 25",
    "MotoGP 24",

    # ── Japanese titles (Cyrillic / Asian locale heavy) ────────────────────────
    # Titles vary heavily across locales (kanji, Cyrillic, Arabic). Key test
    # for suffix grouping vs. composite_key fallback. Also covers cases where
    # a game is unavailable in certain regions.
    "Final Fantasy VII Rebirth",
    "Final Fantasy XVI",
    "Final Fantasy VII Remake",
    "Persona 5 Royal",
    "Persona 3 Reload",
    "Dragon's Dogma 2",
    "Monster Hunter Wilds",
    "Monster Hunter World",
    "Elden Ring",
    "Dark Souls III",
    "Bloodborne",
    "Sekiro Shadows Die Twice",
    "Demon's Souls",
    "Lies of P",
    "Like a Dragon Infinite Wealth",
    "Like a Dragon Ishin",
    "Yakuza Like a Dragon",
    "Tekken 8",
    "Street Fighter 6",
    "Devil May Cry 5",
    "Resident Evil 4",
    "Resident Evil Village",
    "Resident Evil 2",
    "Nioh 2",
    "Tales of Arise",
    "Scarlet Nexus",
    "Astro Bot",

    # ── PlayStation exclusives ─────────────────────────────────────────────────
    # Available in most regions with stable titles — a reliable baseline for
    # composite_key grouping.
    "Stellar Blade",
    "God of War",
    "Spider-Man 2",
    "Spider-Man Miles Morales",
    "Marvel's Spider-Man Remastered",
    "The Last of Us Part I",
    "The Last of Us Part II Remastered",
    "The Last of Us Part II",
    "Horizon Forbidden West",
    "Horizon Zero Dawn",
    "Ghost of Tsushima",
    "Returnal",
    "Rift Apart",
    "Gran Turismo 7",
    "Uncharted 4",
    "Death Stranding",

    # ── Western AAA ───────────────────────────────────────────────────────────
    # Mixed publishers with varying regionalisation strategies. Some titles
    # (CoD, Assassin's Creed) have complex edition structures — verifies that
    # different editions are not incorrectly merged into a single card.
    "Cyberpunk 2077",
    "The Witcher 3",
    "Red Dead Redemption 2",
    "Grand Theft Auto V",
    "Baldur's Gate 3",
    "Hogwarts Legacy",
    "Dead Space",
    "Atomic Heart",
    "Indiana Jones and the Great Circle",
    "Mortal Kombat 1",
    "Mortal Kombat 11",
    "Call of Duty Black Ops 6",
    "Diablo IV",
    "Starfield",
    "Avowed",
    "Assassin's Creed Shadows",
    "Assassin's Creed Mirage",
    "Assassin's Creed Valhalla",

    # ── Recent releases (2024–2025) ───────────────────────────────────────────
    # Latest titles with up-to-date suffix patterns. Some may be absent in
    # certain regions (ar-ae, zh-hk, etc.), producing useful gap data.
    "Black Myth Wukong",
    "Metaphor ReFantazio",
    "Silent Hill 2",
    "Alan Wake 2",
    "Space Marine 2",
    "Like a Dragon Pirate Yakuza in Hawaii",
    "Dragon Age The Veilguard",
    "Helldivers 2",
    "Pragmata",

    # ── Indie / mid-tier ─────────────────────────────────────────────────────
    # Fewer regional variants, but interesting edge cases: Minecraft has
    # per-region product IDs with no shared suffix; Hades II was in early
    # access at the time of writing and is absent from some regions.
    "Minecraft",
    "Hades",
    "Hades II",
    "Hollow Knight",
    "Stardew Valley",
    "Disco Elysium",
    "Grounded",
    "Sifu",
    "Tunic",
    "Cult of the Lamb",

    # ── Older / legacy titles ─────────────────────────────────────────────────
    # PS3–PS4 era classics. Verifies that grouping holds on legacy content:
    # some titles have numeric (non-human-readable) suffixes; others have no
    # shared suffix at all and rely purely on composite_key.
    "The Last of Us",
    "Infamous Second Son",
    "Shadow of the Colossus",
    "Dark Souls Remastered",
    "Nioh",
    "It Takes Two",
    "Mass Effect Legendary Edition",
    "BioShock The Collection",
    "Borderlands 3",
    "Doom Eternal",
    "Wolfenstein II The New Colossus",
]
