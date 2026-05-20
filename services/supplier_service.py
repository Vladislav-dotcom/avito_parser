from __future__ import annotations

import re

from services.db_service import get_supplier_by_id, insert_supplier, list_suppliers

_LETTER_PATTERN = re.compile(r"^[\wА-Яа-яЁё]$", re.UNICODE)


class SupplierValidationError(ValueError):
    pass


def _normalize_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise SupplierValidationError("Укажите имя поставщика.")
    return normalized


def _normalize_letter(letter: str) -> str:
    normalized = letter.strip()
    if not _LETTER_PATTERN.fullmatch(normalized):
        raise SupplierValidationError("Буква поставщика должна быть одним символом.")
    return normalized


def get_all_suppliers() -> list[dict]:
    return list_suppliers()


def get_supplier(supplier_id: str) -> dict | None:
    return get_supplier_by_id(supplier_id)


def create_supplier(name: str, letter: str) -> dict:
    normalized_name = _normalize_name(name)
    normalized_letter = _normalize_letter(letter)
    try:
        return insert_supplier(normalized_name, normalized_letter)
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        if "unique" in message:
            if "letter" in message:
                raise SupplierValidationError("Буква уже используется другим поставщиком.") from exc
            raise SupplierValidationError("Поставщик с таким именем уже существует.") from exc
        raise
