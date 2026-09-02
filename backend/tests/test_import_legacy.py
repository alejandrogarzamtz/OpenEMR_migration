from datetime import date
from app.import_legacy import clean, valid_dob


def test_legacy_value_normalization():
    assert clean("  Ada ") == "Ada"
    assert clean("  ") is None
    assert valid_dob(date(1815, 12, 10)) == date(1815, 12, 10)
    assert valid_dob(date(1, 1, 1)) == date(1900, 1, 1)
