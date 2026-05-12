import pandas as pd
import pytest

from services.excel_service import EXPECTED_COLUMNS, build_result_dataframe, validate_columns


def test_validate_columns_success():
    dataframe = pd.DataFrame(columns=EXPECTED_COLUMNS)
    validate_columns(dataframe)


def test_validate_columns_raises_for_missing_column():
    dataframe = pd.DataFrame(columns=EXPECTED_COLUMNS[:-1])
    with pytest.raises(ValueError):
        validate_columns(dataframe)


def test_build_result_dataframe_adds_columns():
    dataframe = pd.DataFrame(
        [
            {
                "Наименование": "Позиция",
                "Цена": 1000,
                "Валюта": "RUB",
                "Кол-во в наличии": 2,
                "Раздел": "A",
                "Категория": "B",
                "Описание": "test",
            }
        ]
    )
    parsed_rows = [[
        {
            "brand": "ABB",
            "article": "A-123",
            "price": 1000,
            "quantity": 2,
            "condition": "новое",
            "generated_description": "Краткое AI описание",
        }
    ]]
    result = build_result_dataframe(dataframe, parsed_rows)
    assert result["Бренд"].iloc[0] == "ABB"
    assert result["Артикул"].iloc[0] == "A-123"
    assert result["Состояние"].iloc[0] == "новое"
    assert result["Описание"].iloc[0] == "Краткое AI описание"


def test_build_result_dataframe_explodes_rows_for_multi_positions():
    dataframe = pd.DataFrame(
        [
            {
                "Наименование": "Позиция",
                "Цена": 1000,
                "Валюта": "RUB",
                "Кол-во в наличии": 2,
                "Раздел": "A",
                "Категория": "B",
                "Описание": "test",
            }
        ]
    )
    parsed_rows = [[
        {
            "brand": "ABB",
            "article": "A-123",
            "price": 1000,
            "quantity": 2,
            "condition": "новое",
            "generated_description": "Описание 1",
        },
        {
            "brand": "IFM",
            "article": "B-777",
            "price": 8000,
            "quantity": 1,
            "condition": "бу",
            "generated_description": "Описание 2",
        },
    ]]

    result = build_result_dataframe(dataframe, parsed_rows)
    assert len(result.index) == 2
    assert result["Артикул"].tolist() == ["A-123", "B-777"]
    assert result["Описание"].tolist() == ["Описание 1", "Описание 2"]


def test_build_result_dataframe_skips_rows_without_article():
    dataframe = pd.DataFrame(
        [
            {
                "Наименование": "Позиция 1",
                "Цена": 1000,
                "Валюта": "RUB",
                "Кол-во в наличии": 2,
                "Раздел": "A",
                "Категория": "B",
                "Описание": "test 1",
            },
            {
                "Наименование": "Позиция 2",
                "Цена": 2000,
                "Валюта": "RUB",
                "Кол-во в наличии": 1,
                "Раздел": "A",
                "Категория": "B",
                "Описание": "test 2",
            },
        ]
    )
    parsed_rows = [
        [{"brand": "ABB", "article": None, "price": 1000, "quantity": 2, "condition": "новое"}],
        [{
            "brand": "IFM",
            "article": "B-777",
            "price": 2000,
            "quantity": 1,
            "condition": "бу",
            "generated_description": "Описание IFM",
        }],
    ]

    result = build_result_dataframe(dataframe, parsed_rows)
    assert len(result.index) == 1
    assert result["Наименование"].tolist() == ["Позиция 2"]
    assert result["Артикул"].tolist() == ["B-777"]
    assert result["Описание"].tolist() == ["Описание IFM"]
