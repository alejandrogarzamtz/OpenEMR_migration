from datetime import date, datetime, time, timedelta
from decimal import Decimal
from app.import_legacy import clean, event_datetime, json_value, legacy_consent_decision, parse_legacy_person_name, stable_legacy_row_keys, valid_dob


def test_legacy_value_normalization():
    assert clean("  Ada ") == "Ada"
    assert clean("  ") is None
    assert valid_dob(date(1815, 12, 10)) == date(1815, 12, 10)
    assert valid_dob(date(1, 1, 1)) == date(1900, 1, 1)
    assert json_value(datetime(2026, 9, 3, 12, 30)) == "2026-09-03T12:30:00"
    assert json_value(Decimal("12.30")) == "12.30"
    assert json_value(b"\x01\x02") == "0102"
    assert event_datetime(date(2026, 9, 3), time(9, 30)) == datetime(2026, 9, 3, 9, 30)
    assert event_datetime(date(2026, 9, 3), timedelta(hours=9, minutes=30)) == datetime(2026, 9, 3, 9, 30)
    assert legacy_consent_decision("email", "YES") == "permit"
    assert legacy_consent_decision("sms", "NO") == "deny"
    assert legacy_consent_decision("privacy-notice", "YES") == "acknowledged"
    assert legacy_consent_decision("advance-directive", "NO") == "not-completed"
    assert legacy_consent_decision("message-delegate", "Ada Guardian") == "permit"
    assert legacy_consent_decision("health-information-exchange", "") == "unknown"
    assert parse_legacy_person_name("Ada Byron") == ("Ada", "Byron")
    assert parse_legacy_person_name("Byron, Ada") == ("Ada", "Byron")
    assert parse_legacy_person_name("") == ("Unknown", "Unknown")


def test_legacy_multiset_row_keys_are_stable_and_preserve_duplicates():
    rows=[{"id":2,"description":"Second","amount":Decimal("1.20")},{"id":1,"description":"First","amount":Decimal("2.30")},{"id":1,"description":"First","amount":Decimal("2.30")}]
    forward=stable_legacy_row_keys(rows);reverse=stable_legacy_row_keys(list(reversed(rows)))
    assert [payload for _,payload,_ in forward]==[payload for _,payload,_ in reverse]
    keys=[key for _,_,key in forward]
    assert keys==[key for _,_,key in reverse] and len(set(keys))==3
    assert keys[0].endswith(":1") and keys[1].endswith(":2")
