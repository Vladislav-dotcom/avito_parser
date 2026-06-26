from services.price_service import sanitize_multi_item_prices, should_exclude_catalog_row


def test_sanitize_multi_item_prices_clears_fake_row_price():
    items = [
        {"article": "A", "price": 100},
        {"article": "B", "price": 100},
    ]
    result = sanitize_multi_item_prices(items, 100)
    assert result[0]["price"] is None
    assert result[1]["price"] is None


def test_sanitize_multi_item_prices_keeps_distinct_prices():
    items = [
        {"article": "A", "price": 1000},
        {"article": "B", "price": 2000},
    ]
    result = sanitize_multi_item_prices(items, 1000)
    assert result[0]["price"] == 1000
    assert result[1]["price"] == 2000


def test_sanitize_multi_item_prices_single_item_unchanged():
    items = [{"article": "3RV1021-1AA15", "price": 5000}]
    result = sanitize_multi_item_prices(items, 5000)
    assert result[0]["price"] == 5000


def test_sanitize_multi_item_prices_partial_prices_unchanged():
    items = [
        {"article": "A", "price": 100},
        {"article": "B", "price": None},
    ]
    result = sanitize_multi_item_prices(items, 100)
    assert result[0]["price"] == 100
    assert result[1]["price"] is None


def test_should_exclude_catalog_row_multi_without_prices():
    items = [
        {"article": "A", "price": None},
        {"article": "B", "price": None},
    ]
    assert should_exclude_catalog_row(items) is True


def test_should_exclude_catalog_row_single_item():
    items = [{"article": "3RV1021-1AA15", "price": None}]
    assert should_exclude_catalog_row(items) is False


def test_should_exclude_catalog_row_multi_with_one_price():
    items = [
        {"article": "A", "price": 1000},
        {"article": "B", "price": None},
    ]
    assert should_exclude_catalog_row(items) is False


def test_catalog_flow_sanitize_then_exclude():
    items = [{"article": f"ART-{index}", "price": 100} for index in range(5)]
    sanitized = sanitize_multi_item_prices(items, 100)
    assert should_exclude_catalog_row(sanitized) is True
