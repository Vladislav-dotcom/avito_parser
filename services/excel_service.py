from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

EXPECTED_COLUMNS = [
    "Наименование",
    "Цена",
    "Валюта",
    "Кол-во в наличии",
    "Раздел",
    "Категория",
    "Описание",
]

PARSED_COLUMNS = ["Бренд", "Артикул", "Цена", "Кол-во", "Состояние", "Описание"]
_FIELD_MAP = {
    "Бренд": "brand",
    "Артикул": "article",
    "Цена": "price",
    "Кол-во": "quantity",
    "Состояние": "condition",
    "Описание": "generated_description",
}

EXPORT_COLUMN_RENAMES = {
    "Наименование": "название",
    "Бренд": "производитель",
    "Артикул": "артикул",
}


def _has_article(value: object) -> bool:
    if value is None:
        return False
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def read_excel(path: Path) -> pd.DataFrame:
    return pd.read_excel(path)


def validate_columns(dataframe: pd.DataFrame) -> None:
    missing_columns = [column for column in EXPECTED_COLUMNS if column not in dataframe.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"В файле отсутствуют обязательные столбцы: {missing}")


def build_result_dataframe(dataframe: pd.DataFrame, parsed_rows: Iterable[list[dict]]) -> pd.DataFrame:
    source_df = dataframe.copy()
    rows = list(parsed_rows)
    if len(rows) != len(source_df):
        raise ValueError("Количество результатов AI не совпадает с количеством строк в файле.")

    exploded_rows: list[dict] = []
    for source_row, parsed_items in zip(source_df.to_dict(orient="records"), rows):
        if not parsed_items:
            continue

        for parsed_item in parsed_items:
            if not _has_article(parsed_item.get("article")):
                continue
            out_row = dict(source_row)
            for display_name in PARSED_COLUMNS:
                source_key = _FIELD_MAP[display_name]
                out_row[display_name] = parsed_item.get(source_key)
            exploded_rows.append(out_row)

    return pd.DataFrame(exploded_rows)


def format_export_for_1c(dataframe: pd.DataFrame) -> pd.DataFrame:
    return dataframe.rename(columns=EXPORT_COLUMN_RENAMES)


def write_excel(dataframe: pd.DataFrame, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_excel(target_path, index=False)
