from __future__ import annotations

from typing import Any, Optional


def _normalize_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_price(value: Any) -> bool:
    return _normalize_price(value) is not None


def sanitize_multi_item_prices(items: list[dict[str, Any]], row_price: Any) -> list[dict[str, Any]]:
    if len(items) <= 1:
        return items

    normalized_row_price = _normalize_price(row_price)
    if normalized_row_price is None:
        return items

    item_prices = [_normalize_price(item.get("price")) for item in items]
    non_null_prices = [price for price in item_prices if price is not None]
    if not non_null_prices:
        return items

    if len(non_null_prices) != len(items):
        return items

    if len(set(non_null_prices)) != 1:
        return items

    if non_null_prices[0] != normalized_row_price:
        return items

    sanitized_items: list[dict[str, Any]] = []
    for item in items:
        sanitized_item = dict(item)
        sanitized_item["price"] = None
        sanitized_items.append(sanitized_item)
    return sanitized_items


def should_exclude_catalog_row(items: list[dict[str, Any]]) -> bool:
    if len(items) <= 1:
        return False
    return not any(_has_price(item.get("price")) for item in items)
