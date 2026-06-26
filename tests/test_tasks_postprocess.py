from unittest.mock import patch

import pandas as pd

from tasks import _process_row


@patch("tasks.parse_description")
def test_process_row_excludes_catalog_without_prices(mock_parse_description):
    mock_parse_description.return_value = (
        [
            {"brand": "Siemens", "article": "3RU1126", "price": 100, "quantity": 1, "condition": "бу"},
            {"brand": "Siemens", "article": "3SB3601", "price": 100, "quantity": 1, "condition": "бу"},
        ],
        None,
    )
    row = pd.Series(
        {
            "Наименование": "Siemens каталог",
            "Цена": 100,
            "Валюта": "RUB",
            "Кол-во в наличии": 1,
            "Раздел": "A",
            "Категория": "B",
            "Описание": "3RU1126 3SB3601",
        }
    )

    parsed_items, had_error = _process_row("job-id", 1, row)

    assert parsed_items == []
    assert had_error is False


@patch("tasks.parse_description")
def test_process_row_merges_condition_markers(mock_parse_description):
    mock_parse_description.return_value = (
        [{"brand": "ABB", "article": "A1", "price": 1000, "quantity": 1, "condition": "бу"}],
        None,
    )
    row = pd.Series(
        {
            "Наименование": "Датчик",
            "Цена": 1000,
            "Валюта": "RUB",
            "Кол-во в наличии": 1,
            "Раздел": "A",
            "Категория": "B",
            "Описание": "После демонтажа, в работе не было",
        }
    )

    parsed_items, had_error = _process_row("job-id", 2, row)

    assert had_error is False
    assert parsed_items[0]["condition"] == "бу, демонтаж, в работе не было"
