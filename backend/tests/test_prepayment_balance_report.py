from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Patient, ReceivableActivity, ReceivableSession, User
from app.security import password_hash


def auth(client,email):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":"report-password"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_prepayment_balances_match_legacy_arithmetic_filters_and_export():
    with TestClient(app) as client:
        with SessionLocal() as db:
            reader=User(email="prepayment-report@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["acct:rep_a:read"])
            patient=Patient(legacy_pid=95001,first_name="Prepaid",middle_name="M",last_name="Patient",date_of_birth=date(1980,1,1),sex="unknown")
            db.add_all([reader,patient]);db.flush()
            db.add_all([
                ReceivableSession(legacy_session_id=95101,patient_id=patient.id,legacy_patient_id=95001,closed=False,reference="PRE-OPEN",check_date=date(2026,6,1),pay_total=Decimal("100.00"),global_amount=Decimal("25.00"),adjustment_code="pre_payment"),
                ReceivableSession(legacy_session_id=95102,patient_id=patient.id,legacy_patient_id=95001,closed=False,reference="NO-ACTIVITY",check_date=date(2026,6,2),pay_total=Decimal("40.00"),global_amount=Decimal("0.00"),adjustment_code="pre_payment"),
                ReceivableSession(legacy_session_id=95103,patient_id=patient.id,legacy_patient_id=95001,closed=False,reference="RESIDUE",check_date=date(2026,6,3),pay_total=Decimal("20.004"),global_amount=Decimal("0.00"),adjustment_code="pre_payment"),
                ReceivableSession(legacy_session_id=95104,patient_id=patient.id,legacy_patient_id=95001,closed=True,reference="CLOSED",check_date=date(2026,6,4),pay_total=Decimal("80.00"),global_amount=Decimal("80.00"),adjustment_code="pre_payment"),
            ]);db.flush()
            db.add_all([
                ReceivableActivity(legacy_patient_id=95001,legacy_encounter_id=0,legacy_sequence=1,legacy_session_id=95101,pay_amount=Decimal("30.00"),posted_at=datetime(2026,6,1,tzinfo=timezone.utc)),
                ReceivableActivity(legacy_patient_id=95001,legacy_encounter_id=0,legacy_sequence=2,legacy_session_id=95101,pay_amount=Decimal("10.00"),deleted_at=datetime(2026,6,2,tzinfo=timezone.utc),posted_at=datetime(2026,6,1,tzinfo=timezone.utc)),
                ReceivableActivity(legacy_patient_id=95001,legacy_encounter_id=0,legacy_sequence=3,legacy_session_id=95103,pay_amount=Decimal("20.00"),posted_at=datetime(2026,6,3,tzinfo=timezone.utc)),
            ]);db.commit();patient_uuid=patient.uuid
        headers=auth(client,"prepayment-report@example.com")
        response=client.post("/api/v1/reports/prepayment_balance_report/runs",headers=headers,json={"date_from":"2026-06-01","date_to":"2026-06-30","patient_uuid":patient_uuid})
        assert response.status_code==201,response.text
        payload=response.json();assert payload["row_count"]==2
        assert payload["totals"]=={"sessions":2,"received":"140.00","applied":"30.00","in_global":"25.00","unapplied":"110.00"}
        rows={row["reference"]:row for row in payload["rows"]}
        assert rows["PRE-OPEN"]["patient"]=="Patient, Prepaid M" and rows["PRE-OPEN"]["unapplied"]=="70.00"
        assert rows["NO-ACTIVITY"]["applied"]=="0" and rows["NO-ACTIVITY"]["unapplied"]=="40.00"
        parked=client.post("/api/v1/reports/prepayment_balance_report/runs",headers=headers,json={"parked_only":True})
        assert parked.status_code==201 and [row["reference"] for row in parked.json()["rows"]]==["PRE-OPEN"]
        export=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers)
        assert export.status_code==200 and export.text.splitlines()[0]==",".join(payload["columns"])


def test_prepayment_report_requires_accounting_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:db.add(User(email="prepayment-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:med:read"]));db.commit()
        assert client.post("/api/v1/reports/prepayment_balance_report/runs",headers=auth(client,"prepayment-denied@example.com"),json={}).status_code==403
