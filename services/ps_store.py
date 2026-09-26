import re
from dataclasses import dataclass, field
from datetime import datetime

_TRADEMARK_RE = re.compile(r"[™®©]")


def is_effectively_ascii(title: str) -> bool:
    """Return True if the title is ASCII after stripping trademark/copyright symbols."""
    return _TRADEMARK_RE.sub("", title).isascii()


@dataclass
class RegionPrice:
    price: float | None
    currency: str | None
    base_price: float | None
    discount_text: str | None
    ps_id: str | None = None
    discount_end: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "price": self.price,
            "currency": self.currency,
            "base_price": self.base_price,
            "discount_text": self.discount_text,
            "ps_id": self.ps_id,
            "discount_end": self.discount_end,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RegionPrice":
        return cls(**d)


@dataclass
class GameInfo:
    title: str
    platforms: list[str]
    type: str | None
    cover_url: str | None
    ps_id_suffix: str | None = None
    composite_key: str = field(init=False)

    def __post_init__(self) -> None:
        norm = GameInfo.normalize_title(self.title)
        type_part = (self.type or "").lower()
        plat_part = "_".join(sorted(p.lower() for p in self.platforms or []))
        self.composite_key = f"{norm}_{type_part}_{plat_part}"

    @staticmethod
    def normalize_title(title: str) -> str:
        """Strip punctuation, collapse whitespace, lowercase."""
        title = re.sub(r"[™®©:().,'\"!?\-/]", "", title.lower())
        full_norm = re.sub(r"\s+", "", title)
        ascii_norm = re.sub(r"[^\x00-\x7f]", "", full_norm)
        return ascii_norm if len(ascii_norm) >= 3 else full_norm

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "platforms": self.platforms,
            "type": self.type,
            "cover_url": self.cover_url,
            "ps_id_suffix": self.ps_id_suffix,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameInfo":
        return cls(**d)


def ps_id_build_id(ps_id: str | None) -> str | None:
    """Return the Build ID (concept segment) from a PS Store product ID."""
    if not ps_id or "-" not in ps_id or "_" not in ps_id:
        return None
    middle = ps_id.split("-", 1)[1]
    build_id = middle.split("_", 1)[0]
    return build_id or None


def ps_id_suffix(ps_id: str | None) -> str | None:
    """Return the trailing product-code segment of a PS Store product ID."""
    if not ps_id or "-" not in ps_id:
        return None
    return ps_id.rsplit("-", 1)[-1] or None


_COUNTRY_TO_PS_PREFIX: dict[str, str] = {
    "us": "UP",
    "ca": "UP",
    "mx": "UP",
    "br": "UP",
    "ar": "UP",
    "cl": "UP",
    "co": "UP",
    "jp": "JP",
    "kr": "KP",
}


def preferred_ps_prefix(region_code: str) -> str:
    country = region_code.split("-")[-1].lower()
    return _COUNTRY_TO_PS_PREFIX.get(country, "EP")


def remap_ps_id_prefix(ps_id: str, prefix: str) -> str:
    """Swap the leading two-letter regional prefix (UP/EP/JP/KP/…)."""
    if "-" not in ps_id or len(prefix) != 2:
        return ps_id
    rest = ps_id.split("-", 1)[1]
    head, _, _ = ps_id.partition("-")
    digits = head[2:] if len(head) > 2 else ""
    return f"{prefix}{digits}-{rest}" if digits else f"{prefix}-{rest}"


def best_ps_id(region_code: str, ps_ids: dict[str, str]) -> str | None:
    """Pick the ps_id most likely to work for region_code based on product ID prefix."""
    preferred = preferred_ps_prefix(region_code)
    return next((pid for pid in ps_ids.values() if pid.startswith(preferred)), None)
