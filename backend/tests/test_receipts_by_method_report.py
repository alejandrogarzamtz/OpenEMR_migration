from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Charge, ClinicalForm, Coverage, Encounter, Facility, Patient, Payer, ReceivableActivity, User, UserFacilityAccess
from app.security import password_hash


def auth(client,email):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":"report-password"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_receipts_by_method_combines_copays_activity_dates_payers_and_summaries():
    with TestClient(app) as client:
        with SessionLocal() as db:
            facility=Facility(name="Receipt Method Facility",legacy_facility_id=831);reader=User(email="receipt-method@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["acct:rep_a:read"])
            db.add_all([facility,reader]);db.flush();db.add(UserFacilityAccess(user_id=reader.id,facility_id=facility.id))
            patient=Patient(legacy_pid=93001,first_name="Payment",last_name="Method",date_of_birth=date(1980,1,1),sex="unknown");payer=Payer(legacy_payer_id=832,name="Method Health",active=True);db.add_all([patient,payer]);db.flush()
            coverage=Coverage(legacy_insurance_id=833,patient_id=patient.id,payer_id=payer.id,priority="primary",policy_number="METHOD-POL",subscriber_name="Payment Method",starts_on=date(2037,1,1))
            service=datetime(2037,4,5,9,tzinfo=timezone.utc);encounter=Encounter(legacy_encounter_id=834,patient_id=patient.id,occurred_at=service,facility_id=facility.id,legacy_facility_id=831,legacy_provider_id=835,legacy_payload={"invoice_refno":"METHOD-INV"});db.add_all([coverage,encounter]);db.flush()
            db.add_all([
                ClinicalForm(legacy_form_key="forms:836",patient_id=patient.id,encounter_id=encounter.id,form_type="newpatient",source_formdir="newpatient",title="Encounter",content={},status="final",authored_at=service),
                Charge(patient_id=patient.id,encounter_id=encounter.id,code_system="COPAY",code="COPAY",description="Office copay",units=1,unit_price=Decimal("20.00"),active=True,billed=True),
                Charge(patient_id=patient.id,encounter_id=encounter.id,code_system="CPT4",code="99213",description="Visit",units=1,unit_price=Decimal("100.00"),active=True,billed=True,legacy_payload={"provider_id":835}),
                ReceivableActivity(patient_id=patient.id,encounter_id=encounter.id,legacy_patient_id=93001,legacy_encounter_id=834,legacy_sequence=1,legacy_session_id=837,payer_type=1,payer_id=payer.id,legacy_payer_id=832,account_code="",code_system="CPT4",code="99213",pay_amount=Decimal("50.00"),adjustment_amount=Decimal("5.00"),posted_at=datetime(2037,4,8,tzinfo=timezone.utc),deposit_date=date(2037,4,10),payment_method="CC",payment_method_label="Credit Card",payment_reference="CHECK-837",memo="EOB payment"),
            ]);db.commit();facility_uuid=facility.uuid
        headers=auth(client,"receipt-method@example.com")
        response=client.post("/api/v1/reports/receipts_by_method_report/runs",headers=headers,json={"date_from":"2037-04-01","date_to":"2037-04-30","facility_uuid":facility_uuid,"provider_legacy_id":835,"receipt_report_by":"payment_method","include_details":True})
        assert response.status_code==201,response.text
        payload=response.json();assert payload["row_count"]==2
        rows={row["method"]:row for row in payload["rows"]};assert rows["Co-Pay"]["payments"]=="-20.00" and rows["Credit Card"]["payments"]=="50.00" and rows["Credit Card"]["adjustments"]=="5.00"
        assert rows["Credit Card"]["date"]=="2037-04-10" and rows["Credit Card"]["policy_number"]=="METHOD-POL"
        assert payload["totals"]["payments"]=="30.00" and payload["totals"]["adjustments"]=="5.00"
        summary=client.post("/api/v1/reports/receipts_by_method_report/runs",headers=headers,json={"date_from":"2037-04-01","date_to":"2037-04-30","receipt_report_by":"payer","include_details":False})
        assert summary.status_code==201 and {row["method"] for row in summary.json()["rows"]}=={"Patient","Method Health"}
        filtered=client.post("/api/v1/reports/receipts_by_method_report/runs",headers=headers,json={"date_from":"2037-04-01","date_to":"2037-04-30","procedure_code":"CPT4:99213","receipt_report_by":"check_number","use_invoice_date":True})
        assert filtered.status_code==201 and filtered.json()["row_count"]==1 and filtered.json()["rows"][0]["method"]=="CHECK-837" and filtered.json()["rows"][0]["date"]=="2037-04-05"
        export=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers);assert export.status_code==200 and "policy_number" in export.text.splitlines()[0]


def test_receipts_by_method_requires_accounting_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:db.add(User(email="receipt-method-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:med:read"]));db.commit()
        assert client.post("/api/v1/reports/receipts_by_method_report/runs",headers=auth(client,"receipt-method-denied@example.com"),json={}).status_code==403
