from services.ps_store_url import PsStoreLinkKind, parse_ps_store_url


def test_parse_concept_url():
    link = parse_ps_store_url(
        "https://store.playstation.com/en-in/concept/10016651"
    )
    assert link is not None
    assert link.kind is PsStoreLinkKind.CONCEPT
    assert link.locale == "en-in"
    assert link.concept_id == "10016651"
    assert link.ps_id is None


def test_parse_product_url():
    link = parse_ps_store_url(
        "https://store.playstation.com/en-in/product/UP6312-PPSA32718_00-AUGUSTA000000000"
    )
    assert link is not None
    assert link.kind is PsStoreLinkKind.PRODUCT
    assert link.locale == "en-in"
    assert link.ps_id == "UP6312-PPSA32718_00-AUGUSTA000000000"
    assert link.concept_id is None


def test_parse_ignores_query_and_extra_text():
    link = parse_ps_store_url(
        "check this https://store.playstation.com/en-us/concept/10016651?foo=1#bar please"
    )
    assert link is not None
    assert link.concept_id == "10016651"


def test_parse_rejects_non_store_host():
    assert parse_ps_store_url("https://example.com/concept/10016651") is None


def test_parse_rejects_unknown_path():
    assert parse_ps_store_url("https://store.playstation.com/en-us/category/foo") is None
