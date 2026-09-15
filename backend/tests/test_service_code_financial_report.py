from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import BillingCodeType, Charge, Encounter, Facility, Patient, ReceivableActivity, ServiceCode, User, UserFacilityAccess
from app.security import password_hash


def auth(client,email):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":"report-password"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_service_code_financial_summary_matches_legacy_totals_and_filters():
    with TestClient(app) as client:
        with SessionLocal() as db:
            facility=Facility(name="Financial Summary Facility",legacy_facility_id=961);other=Facility(name="Financial Summary Hidden",legacy_facility_id=962)
            reader=User(email="service-financial@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["acct:rep_a:read"])
            db.add_all([facility,other,reader]);db.flush();db.add(UserFacilityAccess(user_id=reader.id,facility_id=facility.id))
            patient=Patient(legacy_pid=96001,first_name="Service",last_name="Financial",date_of_birth=date(1980,1,1),sex="unknown");fee_type=BillingCodeType(key="FINTEST",legacy_type_id=991,sequence=1,fee=True,procedure=True,active=True)
            db.add_all([patient,fee_type]);db.flush()
            db.add_all([ServiceCode(legacy_code_id=963,code_type_id=991,code="99213",modifier="",description="Visit",financial_reporting=False),ServiceCode(legacy_code_id=964,code_type_id=991,code="99213",modifier="25",description="Visit modifier",financial_reporting=True),ServiceCode(legacy_code_id=965,code_type_id=991,code="93000",modifier="",description="ECG",financial_reporting=False)])
            occurred=datetime(2039,7,10,12,tzinfo=timezone.utc);encounter=Encounter(legacy_encounter_id=966,patient_id=patient.id,occurred_at=occurred,facility_id=facility.id,legacy_facility_id=961);hidden=Encounter(legacy_encounter_id=967,patient_id=patient.id,occurred_at=occurred,facility_id=other.id,legacy_facility_id=962)
            db.add_all([encounter,hidden]);db.flush()
            db.add_all([
                Charge(patient_id=patient.id,encounter_id=encounter.id,code_system="FINTEST",code="99213",description="Visit",units=2,unit_price=Decimal("150.00"),active=True,legacy_payload={"pid":96001,"encounter":966,"provider_id":968}),
                Charge(patient_id=patient.id,encounter_id=encounter.id,code_system="FINTEST",code="93000",description="ECG",units=1,unit_price=Decimal("50.00"),active=True,legacy_payload={"pid":96001,"encounter":966,"provider_id":969}),
                Charge(patient_id=patient.id,encounter_id=hidden.id,code_system="FINTEST",code="HIDDEN",description="Hidden",units=1,unit_price=Decimal("999.00"),active=True,legacy_payload={"pid":96001,"encounter":967,"provider_id":968}),
                ReceivableActivity(patient_id=patient.id,encounter_id=encounter.id,legacy_patient_id=96001,legacy_encounter_id=966,legacy_sequence=1,code="99213",pay_amount=Decimal("100.00"),adjustment_amount=Decimal("20.00"),posted_at=occurred),
                ReceivableActivity(patient_id=patient.id,encounter_id=encounter.id,legacy_patient_id=96001,legacy_encounter_id=966,legacy_sequence=2,code="93000",pay_amount=Decimal("40.00"),adjustment_amount=Decimal("5.00"),posted_at=occurred),
                ReceivableActivity(patient_id=patient.id,encounter_id=hidden.id,legacy_patient_id=96001,legacy_encounter_id=967,legacy_sequence=3,code="HIDDEN",pay_amount=Decimal("1.00"),posted_at=occurred),
            ]);db.commit();facility_uuid=facility.uuid
        headers=auth(client,"service-financial@example.com")
        response=client.post("/api/v1/reports/svc_code_financial_report/runs",headers=headers,json={"date_from":"2039-07-10","date_to":"2039-07-10","facility_uuid":facility_uuid})
        assert response.status_code==201,response.text
        payload=response.json();assert payload["row_count"]==2
        assert payload["totals"]=={"codes":2,"units":3,"amount_billed":"200.00","paid_amount":"140.00","adjustment_amount":"25.00","balance_amount":"35.00"}
        visit=next(row for row in payload["rows"] if row["procedure_code"]=="99213")
        assert visit=={"procedure_code":"99213","units":2,"amount_billed":"150.00","paid_amount":"100.00","adjustment_amount":"20.00","financial_reporting":True,"balance_amount":"30.00"}
        important=client.post("/api/v1/reports/svc_code_financial_report/runs",headers=headers,json={"date_from":"2039-07-10","date_to":"2039-07-10","provider_legacy_id":968,"financial_reporting_only":True})
        assert important.status_code==201 and [row["procedure_code"] for row in important.json()["rows"]]==["99213"]
        export=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers);assert export.status_code==200 and export.text.splitlines()[0]==",".join(payload["columns"])


def test_service_code_financial_report_requires_accounting_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:db.add(User(email="service-financial-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:med:read"]));db.commit()
        assert client.post("/api/v1/reports/svc_code_financial_report/runs",headers=auth(client,"service-financial-denied@example.com"),json={}).status_code==403
