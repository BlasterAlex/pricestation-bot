from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

_PS_STORE_RE = re.compile(
    r"https?://store\.playstation\.com/"
    r"(?P<locale>[a-z]{2}-[a-z]{2})/"
    r"(?:concept/(?P<concept_id>\d+)|product/(?P<ps_id>[A-Z]{2}[^\s?#/]+))",
    re.IGNORECASE,
)


class PsStoreLinkKind(StrEnum):
    CONCEPT = "concept"
    PRODUCT = "product"


@dataclass(frozen=True)
class PsStoreLink:
    kind: PsStoreLinkKind
    locale: str
    concept_id: str | None = None
    ps_id: str | None = None


def parse_ps_store_url(text: str) -> PsStoreLink | None:
    if not text:
        return None
    m = _PS_STORE_RE.search(text)
    if not m:
        return None
    locale = m.group("locale").lower()
    if m.group("concept_id"):
        return PsStoreLink(
            kind=PsStoreLinkKind.CONCEPT,
            locale=locale,
            concept_id=m.group("concept_id"),
        )
    return PsStoreLink(kind=PsStoreLinkKind.PRODUCT, locale=locale, ps_id=m.group("ps_id"))
