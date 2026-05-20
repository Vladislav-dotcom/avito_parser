import pytest

from config import Config
from services.db_service import init_db, list_suppliers
from services.supplier_service import (
    SupplierValidationError,
    create_supplier,
    get_all_suppliers,
)


def test_default_suppliers_seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "suppliers.db")
    init_db()

    suppliers = get_all_suppliers()
    assert len(suppliers) == 5
    names = {item["name"] for item in suppliers}
    assert names == {"Еремеев", "Неботов", "Усмамбаев", "Сергей", "plc:Store"}


def test_create_supplier_success(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "suppliers.db")
    init_db()

    supplier = create_supplier("Новый", "Я")
    assert supplier["name"] == "Новый"
    assert supplier["letter"] == "Я"
    assert len(list_suppliers()) == 6


def test_create_supplier_duplicate_letter(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "suppliers.db")
    init_db()

    with pytest.raises(SupplierValidationError, match="Буква уже используется"):
        create_supplier("Другой", "Е")


def test_create_supplier_invalid_letter(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "suppliers.db")
    init_db()

    with pytest.raises(SupplierValidationError, match="одним символом"):
        create_supplier("Тест", "AB")
