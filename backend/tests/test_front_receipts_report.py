from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Encounter, Facility, FrontOfficePayment, Patient, User, UserFacilityAccess
from app.security import password_hash


def auth(client,email):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":"report-password"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_front_receipts_groups_lines_filters_scope_and_totals_by_method():
    with TestClient(app) as client:
        with SessionLocal() as db:
            north=Facility(name="Receipts North",legacy_facility_id=821);south=Facility(name="Receipts South",legacy_facility_id=822)
            reader=User(email="receipts@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["acct:rep_a:read"])
            db.add_all([north,south,reader]);db.flush();db.add(UserFacilityAccess(user_id=reader.id,facility_id=north.id))
            patient=Patient(legacy_pid=92001,first_name="Front",middle_name="Office",last_name="Receipt",date_of_birth=date(1980,1,1),sex="unknown",legacy_payload={"pubpid":"RCPT-1"});remote=Patient(legacy_pid=92002,first_name="Remote",last_name="Receipt",date_of_birth=date(1981,1,1),sex="unknown")
            db.add_all([patient,remote]);db.flush();when=datetime(2036,3,4,10,11,12,tzinfo=timezone.utc)
            encounter=Encounter(legacy_encounter_id=923,patient_id=patient.id,occurred_at=when,facility_id=north.id,legacy_facility_id=821,legacy_provider_id=824);remote_encounter=Encounter(legacy_encounter_id=925,patient_id=remote.id,occurred_at=when,facility_id=south.id,legacy_facility_id=822,legacy_provider_id=826)
            db.add_all([encounter,remote_encounter]);db.flush()
            db.add_all([
                FrontOfficePayment(legacy_payment_id=927,patient_id=patient.id,encounter_id=encounter.id,legacy_patient_id=92001,legacy_encounter_id=923,received_at=when,actor_name="cashier",method="cash",source="copay",current_amount=Decimal("20.00"),previous_amount=Decimal("0"),posted_current_amount=Decimal("20"),posted_previous_amount=Decimal("0")),
                FrontOfficePayment(legacy_payment_id=928,patient_id=patient.id,encounter_id=encounter.id,legacy_patient_id=92001,legacy_encounter_id=923,received_at=when,actor_name="cashier",method="cash",source="invoice",current_amount=Decimal("5.00"),previous_amount=Decimal("30.00"),posted_current_amount=Decimal("5"),posted_previous_amount=Decimal("30")),
                FrontOfficePayment(legacy_payment_id=929,patient_id=remote.id,encounter_id=remote_encounter.id,legacy_patient_id=92002,legacy_encounter_id=925,received_at=when,method="card",source="remote",current_amount=Decimal("999"),previous_amount=Decimal("0"),posted_current_amount=Decimal("999"),posted_previous_amount=Decimal("0")),
            ]);db.commit();north_uuid=north.uuid
        headers=auth(client,"receipts@example.com")
        response=client.post("/api/v1/reports/front_receipts_report/runs",headers=headers,json={"date_from":"2036-03-04","date_to":"2036-03-04","facility_uuid":north_uuid,"provider_legacy_id":824})
        assert response.status_code==201,response.text
        payload=response.json();assert payload["row_count"]==1
        row=payload["rows"][0];assert row["receipt_key"]=="92001.20360304101112" and row["patient"]=="Receipt, Front Office"
        assert row["current_amount"]=="25.00" and row["previous_amount"]=="30.00" and row["total"]=="55.00" and row["payment_line_count"]==2
        assert row["method"]=="cash" and row["source"]=="invoice"
        assert payload["totals"]["total"]=="55.00" and payload["totals"]["by_method"]==[{"method":"cash","current_amount":"25.00","previous_amount":"30.00","total":"55.00","receipts":1}]
        export=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers);assert export.status_code==200 and "receipt_key" in export.text.splitlines()[0]


def test_front_receipts_requires_accounting_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:db.add(User(email="receipts-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:med:read"]));db.commit()
        assert client.post("/api/v1/reports/front_receipts_report/runs",headers=auth(client,"receipts-denied@example.com"),json={}).status_code==403
