from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import ClinicalRuleLog, Facility, Patient, User, UserFacilityAccess
from app.security import password_hash


def auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response=client.post("/api/v1/auth/token",json={"email":email,"password":password})
    assert response.status_code==200
    return {"Authorization":f"Bearer {response.json()['access_token']}"}


def test_cdr_log_preserves_payload_filters_dates_and_enforces_facility_scope():
    with TestClient(app) as client:
        with SessionLocal() as db:
            patient=Patient(legacy_pid=910001,first_name="Clinical",last_name="Reminder",date_of_birth=date(1980,1,1),sex="unknown")
            north=Facility(legacy_facility_id=910001,name="CDR North")
            south=Facility(legacy_facility_id=910002,name="CDR South")
            reader=User(legacy_user_id=910001,email="cdr-reader@example.com",password_hash=password_hash.hash("cdr-password"),role="viewer",permissions=["patients:med:read"])
            db.add_all([patient,north,south,reader]);db.flush()
            db.add(UserFacilityAccess(user_id=reader.id,facility_id=north.id))
            original='[{"rule":"A1","message":"Check A&B"}]'
            changed='[{"rule":"A1","message":"Updated"}]'
            db.add_all([
                ClinicalRuleLog(legacy_log_id=910001,occurred_at=datetime(2032,4,12,10,0,tzinfo=timezone.utc),patient_id=patient.id,actor_id=reader.id,facility_id=north.id,legacy_patient_id=910001,legacy_user_id=910001,legacy_facility_id=910001,category="clinical_reminder_widget",value=original,new_value=changed),
                ClinicalRuleLog(legacy_log_id=910002,occurred_at=datetime(2032,4,12,11,0,tzinfo=timezone.utc),patient_id=patient.id,facility_id=south.id,legacy_patient_id=910001,legacy_user_id=999999,legacy_facility_id=910002,category="allergy_alert",value="not-json-but-preserved",new_value=None),
                ClinicalRuleLog(legacy_log_id=910003,occurred_at=datetime(2032,4,13,9,0,tzinfo=timezone.utc),legacy_patient_id=999999,legacy_user_id=999999,legacy_facility_id=999999,category="custom_category",value="",new_value=""),
            ]);db.commit()
            north_uuid=north.uuid

        reader_headers=auth_headers(client,"cdr-reader@example.com","cdr-password")
        scoped=client.post("/api/v1/reports/cdr_log/runs",headers=reader_headers,json={"date_from":"2032-04-12","date_to":"2032-04-12"})
        assert scoped.status_code==201
        payload=scoped.json()
        assert payload["row_count"]==1
        assert payload["rows"][0]["value"]==original
        assert payload["rows"][0]["new_value"]==changed
        assert payload["rows"][0]["category_title"]=="Passive Alert"
        assert payload["rows"][0]["patient_pid"]==910001
        assert payload["totals"]=={"logs":1,"passive_alerts":1,"active_alerts":0,"allergy_warnings":0,"changed_evaluations":1}
        exported=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=reader_headers)
        assert exported.status_code==200
        assert exported.text.splitlines()[0]=="log_uuid,date,patient_pid,patient_uuid,user_id,actor,facility_id,facility,category,category_title,value,new_value"

        admin_headers=auth_headers(client,"admin@example.com","change-me-now")
        all_facilities=client.post("/api/v1/reports/cdr_log/runs",headers=admin_headers,json={"date_from":"2032-04-12","date_to":"2032-04-12"})
        assert all_facilities.status_code==201 and all_facilities.json()["row_count"]==2
        assert {row["category_title"] for row in all_facilities.json()["rows"]}=={"Passive Alert","Allergy Warning"}
        selected=client.post("/api/v1/reports/cdr_log/runs",headers=admin_headers,json={"date_from":"2032-04-12","date_to":"2032-04-12","facility_uuid":north_uuid})
        assert selected.status_code==201 and selected.json()["row_count"]==1


def test_cdr_log_requires_clinical_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email="cdr-denied@example.com",password_hash=password_hash.hash("cdr-password"),role="viewer",permissions=["patients:demo:read"]));db.commit()
        headers=auth_headers(client,"cdr-denied@example.com","cdr-password")
        assert client.post("/api/v1/reports/cdr_log/runs",headers=headers,json={}).status_code==403
