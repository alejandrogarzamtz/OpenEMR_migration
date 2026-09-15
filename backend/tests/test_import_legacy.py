from datetime import date, datetime, time, timedelta
from decimal import Decimal
from sqlalchemy import select
from app.db import SessionLocal
from app.import_legacy import clean, event_datetime, import_clinical_rule_log, import_social_history, json_value, legacy_consent_decision, parse_legacy_person_name, questionnaire_items, stable_legacy_row_keys, valid_dob
from app.models import ClinicalRuleLog, SocialHistory


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


def test_legacy_fhir_questionnaire_items_become_portal_fields():
    payload={"item":[{"linkId":"group","type":"group","item":[{"linkId":"q1","text":"How are you?","type":"choice","answerOption":[{"valueString":"Well"},{"valueString":"Unwell"}]}]},{"linkId":"q2","text":"Days","type":"integer","maxValue":30}]}
    assert questionnaire_items(payload)==[{"id":"q1","text":"How are you?","type":"choice","options":["Well","Unwell"]},{"id":"q2","text":"Days","type":"integer","min":0,"max":30}]


def test_cdr_import_is_lossless_for_unresolved_references_and_idempotent():
    row={"id":920001,"date":None,"pid":929991,"uid":929992,"facility_id":929993,"category":"custom","value":"invalid { json","new_value":"","extra":"preserved"}
    with SessionLocal() as db:
        assert import_clinical_rule_log(row,db)=="inserted"
        db.flush()
        assert import_clinical_rule_log(row,db)=="existing"
        item=db.query(ClinicalRuleLog).filter_by(legacy_log_id=920001).one()
        assert item.occurred_at is None and item.patient_id is None and item.actor_id is None and item.facility_id is None
        assert item.legacy_patient_id==929991 and item.legacy_user_id==929992 and item.legacy_facility_id==929993
        assert item.value=="invalid { json" and item.new_value==""
        assert item.legacy_payload==row
        db.rollback()


def test_social_history_import_retains_all_source_fields_and_unresolved_patient():
    row={"id":940001,"pid":949999,"date":None,"coffee":"2 cups","tobacco":"|never|","alcohol":"","sleep_patterns":None,"exercise_patterns":"daily","seatbelt_use":"yes","counseling":None,"hazardous_activities":"none","recreational_drugs":"|neverrecreational_drugs|","additional_history":"source narrative","custom_field":"not discarded"}
    with SessionLocal() as db:
        assert import_social_history(row,db)=="inserted";db.flush()
        assert import_social_history(row,db)=="existing"
        item=db.scalar(select(SocialHistory).where(SocialHistory.legacy_history_id==940001))
        assert item and item.patient_id is None and item.legacy_patient_id==949999 and item.recorded_at is None
        assert item.tobacco=="|never|" and item.alcohol=="" and item.additional_history=="source narrative"
        assert item.legacy_payload==row
        db.rollback()
