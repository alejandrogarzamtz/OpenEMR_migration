from datetime import date, datetime
from decimal import Decimal
from app.import_legacy import clean, json_value, valid_dob


def test_legacy_value_normalization():
    assert clean("  Ada ") == "Ada"
    assert clean("  ") is None
    assert valid_dob(date(1815, 12, 10)) == date(1815, 12, 10)
    assert valid_dob(date(1, 1, 1)) == date(1900, 1, 1)
    assert json_value(datetime(2026, 9, 3, 12, 30)) == "2026-09-03T12:30:00"
    assert json_value(Decimal("12.30")) == "12.30"
    assert json_value(b"\x01\x02") == "0102"
