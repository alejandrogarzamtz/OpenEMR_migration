from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Charge, Coverage, Encounter, Facility, Patient, Payer, ReceivableActivity, User, UserFacilityAccess
from app.security import password_hash


def auth(client,email):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":"report-password"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_collections_responsibility_aging_totals_scope_and_csv():
    with TestClient(app) as client:
        with SessionLocal() as db:
            north=Facility(name="Collections North",legacy_facility_id=811);south=Facility(name="Collections South",legacy_facility_id=812)
            reader=User(email="collections@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["acct:rep_a:read"])
            db.add_all([north,south,reader]);db.flush();db.add(UserFacilityAccess(user_id=reader.id,facility_id=north.id))
            patient=Patient(legacy_pid=91001,first_name="Aging",last_name="Patient",date_of_birth=date(1980,1,1),sex="unknown",phone="555-0100",city="Monterrey",legacy_payload={"pubpid":"COLL-1","billing_note":"IN COLLECTIONS"})
            remote=Patient(legacy_pid=91002,first_name="Remote",last_name="Patient",date_of_birth=date(1981,1,1),sex="unknown")
            payer=Payer(legacy_payer_id=911,name="Example Health",active=True);db.add_all([patient,remote,payer]);db.flush()
            coverage=Coverage(legacy_insurance_id=912,patient_id=patient.id,payer_id=payer.id,priority="primary",policy_number="POL-1",group_number="GRP-1",subscriber_name="Aging Patient",starts_on=date(2035,1,1))
            when=datetime(2035,1,15,9,tzinfo=timezone.utc)
            encounter=Encounter(legacy_encounter_id=913,patient_id=patient.id,occurred_at=when,facility_id=north.id,legacy_facility_id=811,provider_name="Doctor Report",legacy_payload={"last_level_closed":0,"stmt_count":0,"invoice_refno":"INV-913","in_collection":1})
            remote_encounter=Encounter(legacy_encounter_id=914,patient_id=remote.id,occurred_at=when,facility_id=south.id,legacy_facility_id=812,legacy_payload={"last_level_closed":0,"stmt_count":1})
            db.add_all([coverage,encounter,remote_encounter]);db.flush()
            db.add_all([
                Charge(patient_id=patient.id,encounter_id=encounter.id,code_system="CPT4",code="99213",description="Visit",units=1,unit_price=Decimal("125.00"),active=True,billed=True,billed_at=when),
                ReceivableActivity(patient_id=patient.id,encounter_id=encounter.id,legacy_patient_id=91001,legacy_encounter_id=913,legacy_sequence=1,legacy_session_id=915,payer_type=1,payer_id=payer.id,legacy_payer_id=911,account_code="",code_system="CPT4",code="99213",pay_amount=Decimal("40.00"),adjustment_amount=Decimal("10.00"),posted_at=datetime(2035,2,1,tzinfo=timezone.utc),deposit_date=date(2035,2,2),payment_method="check",payment_reference="EOB-915"),
                Charge(patient_id=remote.id,encounter_id=remote_encounter.id,code_system="CPT4",code="99213",description="Remote",units=1,unit_price=Decimal("999.00"),active=True,billed=True),
            ]);db.commit();north_uuid=north.uuid
        headers=auth(client,"collections@example.com")
        response=client.post("/api/v1/reports/collections_report/runs",headers=headers,json={"date_from":"2035-01-01","date_to":"2035-01-31","facility_uuid":north_uuid,"collection_category":"Due Ins","age_by":"last_activity","age_columns":3,"age_increment_days":30,"as_of_date":"2035-04-15"})
        assert response.status_code==201,response.text
        payload=response.json();assert payload["row_count"]==1
        row=payload["rows"][0]
        assert row["insurance"]=="Example Health" and row["invoice"]=="INV-913"
        assert row["charges"]=="125.00" and row["adjustments"]=="-10.00" and row["paid"]=="40.00" and row["balance"]=="75.00"
        assert row["age_60_plus"]=="75.00" and row["aging_days"]==72 and row["in_collections"] is True
        assert payload["totals"]["balance"]=="75.00" and payload["totals"]["invoices"]==1
        exported=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers)
        assert exported.status_code==200 and "policy_number" in exported.text.splitlines()[0] and "INV-913" in exported.text
        summary=client.post("/api/v1/reports/collections_report/runs",headers=headers,json={"date_from":"2035-01-01","date_to":"2035-01-31","collection_category":"Ins Summary","as_of_date":"2035-04-15"})
        assert summary.status_code==201 and summary.json()["rows"][0]["insurance"]=="Example Health"


def test_collections_report_requires_accounting_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email="collections-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:med:read"]));db.commit()
        assert client.post("/api/v1/reports/collections_report/runs",headers=auth(client,"collections-denied@example.com"),json={}).status_code==403
