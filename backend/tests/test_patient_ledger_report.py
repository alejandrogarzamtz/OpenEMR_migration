from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import BillingCodeType, Charge, Encounter, Facility, Patient, Payer, ReceivableActivity, ReceivableSession, User, UserFacilityAccess
from app.security import password_hash


def headers_for(client,email,password):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":password}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_patient_ledger_reconciles_charges_activities_unapplied_credit_and_scope():
    with TestClient(app) as client:
        with SessionLocal() as db:
            north=Facility(name="Ledger North",legacy_facility_id=4101);south=Facility(name="Ledger South",legacy_facility_id=4102)
            reader=User(email="ledger@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["acct:rep:read"])
            patient=Patient(legacy_pid=4201,first_name="Ledger",last_name="Patient",date_of_birth=date(1985,1,2),sex="unknown")
            payer=Payer(legacy_payer_id=4301,name="Ledger Health")
            db.add_all([north,south,reader,patient,payer]);db.flush();db.add(UserFacilityAccess(user_id=reader.id,facility_id=north.id));db.add_all([BillingCodeType(key="LEDGER_CPT",legacy_type_id=9401,procedure=True),BillingCodeType(key="LEDGER_DX",legacy_type_id=9402,diagnosis=True)]);db.flush()
            when=datetime(2040,3,4,9,0,tzinfo=timezone.utc);encounter=Encounter(legacy_encounter_id=4401,patient_id=patient.id,occurred_at=when,facility_id=north.id,legacy_facility_id=4101,legacy_provider_id=7,provider_name="Ledger Doctor",chief_complaint="Follow-up")
            remote=Encounter(legacy_encounter_id=4402,patient_id=patient.id,occurred_at=when,facility_id=south.id,legacy_facility_id=4102)
            db.add_all([encounter,remote]);db.flush()
            db.add_all([
                Charge(patient_id=patient.id,encounter_id=encounter.id,code_system="LEDGER_CPT",code="99213",description="Office visit",units=2,unit_price=Decimal("120.00"),billed_at=when,active=True,legacy_payload={"provider_id":7,"payer_id":4301}),
                Charge(patient_id=patient.id,encounter_id=encounter.id,code_system="LEDGER_DX",code="Z00.00",description="Diagnosis",units=1,unit_price=Decimal("5.00"),billed_at=when,active=True,legacy_payload={"provider_id":7}),
                Charge(patient_id=patient.id,encounter_id=encounter.id,code_system="LEDGER_CPT",code="99999",description="Inactive",units=1,unit_price=Decimal("900.00"),billed_at=when,active=False,legacy_payload={"provider_id":7}),
                Charge(patient_id=patient.id,encounter_id=remote.id,code_system="LEDGER_CPT",code="99214",description="Remote",units=1,unit_price=Decimal("80.00"),billed_at=when,active=True,legacy_payload={"provider_id":7}),
                ReceivableActivity(patient_id=patient.id,encounter_id=encounter.id,legacy_patient_id=4201,legacy_encounter_id=4401,legacy_sequence=1,legacy_session_id=4501,payer_type=1,payer_id=payer.id,account_code="PAY",code_system="LEDGER_CPT",code="99213",pay_amount=Decimal("30.00"),adjustment_amount=Decimal("10.00"),posted_at=when,payment_reference="CHK-1",payment_method_label="Check",memo="contractual"),
                ReceivableActivity(patient_id=patient.id,encounter_id=encounter.id,legacy_patient_id=4201,legacy_encounter_id=4401,legacy_sequence=2,payer_type=0,account_code="PAY",pay_amount=Decimal("50.00"),adjustment_amount=0,posted_at=when,deleted_at=when),
                ReceivableSession(legacy_session_id=4501,patient_id=patient.id,legacy_patient_id=4201,payer_id=payer.id,legacy_payer_id=4301,reference="CHK-1",pay_total=Decimal("100.00"),payment_type="insurance",payment_method="check",payment_method_label="Check",created_at=when,post_to_date=when.date()),
                ReceivableSession(legacy_session_id=4502,patient_id=patient.id,legacy_patient_id=4201,pay_total=Decimal("25.00"),created_at=when),
            ]);db.commit();patient_uuid=patient.uuid;north_uuid=north.uuid
        headers=headers_for(client,"ledger@example.com","report-password")
        assert client.post("/api/v1/reports/pat_ledger/runs",headers=headers,json={}).status_code==422
        response=client.post("/api/v1/reports/pat_ledger/runs",headers=headers,json={"date_from":"2040-03-04","date_to":"2040-03-04","patient_uuid":patient_uuid,"facility_uuid":north_uuid,"provider_legacy_id":7})
        assert response.status_code==201,response.text
        payload=response.json();assert payload["row_count"]==3
        assert payload["totals"]=={"lines":3,"encounters":1,"units":2,"charges":"120.00","payments":"100.00","adjustments":"10.00","balance":"10.00"}
        rows={row["line_type"]:row for row in payload["rows"]};assert rows["charge"]["payer"]=="Insurance" and rows["charge"]["charge"]=="120.00"
        assert rows["payment"]["payment"]=="30.00" and rows["payment"]["adjustment"]=="10.00" and rows["payment"]["encounter_balance"]=="80.00"
        assert rows["unapplied_credit"]["payment"]=="100.00" and rows["unapplied_credit"]["unapplied_applied"]=="30.00" and rows["unapplied_credit"]["balance_effect"]=="-70.00"
        exported=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers);assert exported.status_code==200 and "unapplied_applied" in exported.text.splitlines()[0]


def test_patient_ledger_requires_accounting_report_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email="ledger-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["acct:rep_a:read"]));db.commit()
        headers=headers_for(client,"ledger-denied@example.com","report-password")
        assert client.post("/api/v1/reports/pat_ledger/runs",headers=headers,json={}).status_code==403
