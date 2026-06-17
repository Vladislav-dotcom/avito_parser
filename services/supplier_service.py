from __future__ import annotations

from services.db_service import get_supplier_by_id, insert_supplier, list_suppliers


class SupplierValidationError(ValueError):
    pass


def _normalize_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise SupplierValidationError("Укажите имя поставщика.")
    return normalized


def get_all_suppliers() -> list[dict]:
    return list_suppliers()


def get_supplier(supplier_id: str) -> dict | None:
    return get_supplier_by_id(supplier_id)


def create_supplier(name: str) -> dict:
    normalized_name = _normalize_name(name)
    try:
        return insert_supplier(normalized_name)
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        if "unique" in message:
            raise SupplierValidationError("Поставщик с таким именем уже существует.") from exc
        raise
