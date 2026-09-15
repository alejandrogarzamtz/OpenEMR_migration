from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.config import settings
from app.main import app
from app.models import Appointment, BillingCodeType, Charge, Encounter, Facility, Patient, ReceivableActivity, ServiceCode, User, UserFacilityAccess
from app.security import password_hash


def headers_for(client,email,password):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":password}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_appointment_encounter_reconciliation_billing_errors_copays_and_scope():
    with TestClient(app) as client:
        with SessionLocal() as db:
            north=Facility(name="Reconciliation North",legacy_facility_id=701);south=Facility(name="Reconciliation South",legacy_facility_id=702)
            reader=User(email="reconciliation@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["acct:rep_a:read"])
            db.add_all([north,south,reader]);db.flush();db.add(UserFacilityAccess(user_id=reader.id,facility_id=north.id))
            matched=Patient(first_name="Matched",last_name="Patient",date_of_birth=datetime(1980,1,1).date(),sex="unknown",legacy_payload={"pubpid":"MRN-M"})
            missing_visit=Patient(first_name="Missing",last_name="Visit",date_of_birth=datetime(1981,1,1).date(),sex="unknown",legacy_payload={"pubpid":"MRN-A"})
            missing_appt=Patient(first_name="Missing",last_name="Appointment",date_of_birth=datetime(1982,1,1).date(),sex="unknown",legacy_payload={"pubpid":"MRN-E"})
            remote=Patient(first_name="Remote",last_name="Patient",date_of_birth=datetime(1983,1,1).date(),sex="unknown")
            db.add_all([matched,missing_visit,missing_appt,remote]);db.flush();when=datetime(2035,5,6,9,0,tzinfo=timezone.utc)
            appointment=Appointment(patient_id=matched.id,facility_id=north.id,provider_name="Doctor One",starts_at=when,ends_at=when.replace(minute=30),status="fulfilled")
            orphan_appointment=Appointment(patient_id=missing_visit.id,facility_id=north.id,provider_name="Doctor One",starts_at=when.replace(hour=10),ends_at=when.replace(hour=10,minute=30),status="scheduled")
            remote_appointment=Appointment(patient_id=remote.id,facility_id=south.id,provider_name="Remote Doctor",starts_at=when,ends_at=when.replace(minute=30),status="scheduled")
            db.add_all([appointment,orphan_appointment,remote_appointment]);db.flush()
            encounter=Encounter(patient_id=matched.id,appointment_id=appointment.id,occurred_at=when,facility_id=north.id,provider_name="Doctor One",status="closed")
            orphan_encounter=Encounter(patient_id=missing_appt.id,occurred_at=when.replace(hour=11),facility_id=north.id,provider_name="Doctor Two",status="closed")
            db.add_all([encounter,orphan_encounter]);db.flush()
            db.add_all([
                BillingCodeType(key="CPT4",legacy_type_id=1,fee=True,justification_type="ICD10",diagnosis=False,procedure=True,active=True),
                BillingCodeType(key="ICD10",legacy_type_id=102,fee=False,diagnosis=True,procedure=False,active=True),
                Charge(patient_id=matched.id,encounter_id=encounter.id,code_system="CPT4",code="99213",description="Visit",units=1,unit_price=Decimal("100.00"),authorized=False,billed=False),
                Charge(patient_id=matched.id,encounter_id=encounter.id,code_system="ICD10",code="Z00.00",description="Diagnosis",units=1,unit_price=Decimal("5.00"),authorized=True,billed=True),
                Charge(patient_id=matched.id,encounter_id=encounter.id,code_system="CPT4",code="99401",description="Counseling",units=1,unit_price=Decimal("0.00"),authorized=True,billed=True,justification="Z00.00"),
                Charge(patient_id=matched.id,encounter_id=encounter.id,code_system="CPT4",code="99999",description="Inactive source row",units=1,unit_price=Decimal("1000.00"),authorized=True,billed=True,justification="Z00.00",active=False),
                ServiceCode(code_type_id=1,code="99401",modifier="",description="Counseling",related_codes="IPPF:2522201",active=True),
                ReceivableActivity(patient_id=matched.id,encounter_id=encounter.id,legacy_patient_id=9001,legacy_encounter_id=8001,legacy_sequence=1,payer_type=0,account_code="PCP",pay_amount=Decimal("20.00"),adjustment_amount=0,posted_at=when),
            ]);db.commit();north_uuid=north.uuid
        headers=headers_for(client,"reconciliation@example.com","report-password")
        response=client.post("/api/v1/reports/appt_encounter_report/runs",headers=headers,json={"date_from":"2035-05-06","date_to":"2035-05-06"})
        assert response.status_code==201,response.text
        payload=response.json();assert payload["row_count"]==3
        rows={row["patient"]:row for row in payload["rows"]}
        assert rows["Matched Patient"]["charges"]=="100.00" and rows["Matched Patient"]["copays"]=="20.00"
        assert rows["Matched Patient"]["errors"]=="Needs Auth; Needs Justify; Fee is not allowed; Missing Fee; Not billed"
        assert rows["Missing Visit"]["errors"]=="No visit" and rows["Missing Visit"]["encounter_uuid"] is None
        assert rows["Missing Appointment"]["appointment_uuid"] is None
        assert payload["totals"]["encounters"]==2 and payload["totals"]["charges"]=="100.00" and payload["totals"]["copays"]=="20.00" and payload["totals"]["errors"]==2
        assert {item["provider"] for item in payload["totals"]["providers"]}=={"Doctor One","Doctor Two","Unknown"}
        summary=client.post("/api/v1/reports/appt_encounter_report/runs",headers=headers,json={"date_from":"2035-05-06","date_to":"2035-05-06","facility_uuid":north_uuid,"include_details":False})
        assert summary.status_code==201 and summary.json()["columns"]==["provider","encounters","charges","copays"]
        exported=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers)
        assert exported.status_code==200 and exported.text.splitlines()[0].endswith("charges,copays,billed,errors")
        settings.simplified_demographics=True;settings.ippf_specific=True
        try:
            configured=client.post("/api/v1/reports/appt_encounter_report/runs",headers=headers,json={"date_from":"2035-05-06","date_to":"2035-05-06"})
            configured_errors=next(row["errors"] for row in configured.json()["rows"] if row["patient"]=="Matched Patient")
            assert "Needs Auth" not in configured_errors and "Missing Fee" not in configured_errors and "GCAC visit form is missing" in configured_errors
        finally:settings.simplified_demographics=False;settings.ippf_specific=False


def test_appointment_encounter_report_requires_financial_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email="reconciliation-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:appt:read"]));db.commit()
        headers=headers_for(client,"reconciliation-denied@example.com","report-password")
        assert client.post("/api/v1/reports/appt_encounter_report/runs",headers=headers,json={}).status_code==403
