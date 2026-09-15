from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Patient, PaymentProcessingAudit, User
from app.security import password_hash


def auth(client,email):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":"report-password"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_payment_processing_filters_derives_safe_details_and_preserves_reversals():
    with TestClient(app) as client:
        with SessionLocal() as db:
            reader=User(email="gateway-report@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["acct:rep_a:read"]);patient=Patient(legacy_pid=94001,first_name="Gateway",last_name="Patient",date_of_birth=date(1980,1,1),sex="unknown")
            db.add_all([reader,patient]);db.flush();when=datetime(2038,5,6,12,tzinfo=timezone.utc)
            db.add_all([
                PaymentProcessingAudit(legacy_uuid_hex="01"*16,service="sphere",patient_id=patient.id,legacy_patient_id=94001,success=True,action_name="Sale",amount_text="125.50",amount=Decimal("125.50"),ticket="TICKET-1",transaction_id="TRANS-1",occurred_at=when,reverted=True,revert_action_name="credit",revert_transaction_id="TRANS-2",reverted_at=when,audit_ciphertext='{"get":{"front":"clinic-retail"},"post":{"status_name":"approved"}}',audit_payload={"get":{"front":"clinic-retail"},"post":{"status_name":"approved"}},payload_readable=True),
                PaymentProcessingAudit(legacy_uuid_hex="02"*16,service="sphere",patient_id=patient.id,legacy_patient_id=94001,success=False,action_name="void",amount_text="not-numeric",amount=None,ticket="TICKET-2",transaction_id="TRANS-3",occurred_at=when.replace(hour=13),map_legacy_uuid_hex="01"*16,map_transaction_id="TRANS-1",audit_ciphertext="encrypted-source-value",payload_readable=False),
            ]);db.commit();patient_uuid=patient.uuid
        headers=auth(client,"gateway-report@example.com")
        response=client.post("/api/v1/reports/payment_processing_report/runs",headers=headers,json={"occurred_from":"2038-05-06T00:00:00Z","occurred_to":"2038-05-07T00:00:00Z","patient_uuid":patient_uuid,"payment_service":"sphere"})
        assert response.status_code==201,response.text
        payload=response.json();assert payload["row_count"]==2 and payload["totals"]=={"transactions":2,"successful":1,"failed":1,"reverted":1,"amount":"125.50","encrypted_legacy_payloads":1}
        rows={row["transaction_id"]:row for row in payload["rows"]}
        assert rows["TRANS-1"]["front"]=="Front Office in Person" and rows["TRANS-1"]["reversal_status"]=="Reversed via credit by TRANS-2"
        assert rows["TRANS-3"]["error_message"]=="Encrypted legacy audit detail requires source installation keys" and rows["TRANS-3"]["mapped_transaction_id"]=="TRANS-1"
        filtered=client.post("/api/v1/reports/payment_processing_report/runs",headers=headers,json={"occurred_from":"2038-05-06T00:00:00Z","occurred_to":"2038-05-07T00:00:00Z","payment_ticket":"TICKET-1","payment_transaction_id":"TRANS-1","payment_action":"Sale"})
        assert filtered.status_code==201 and filtered.json()["row_count"]==1
        export=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers);assert export.status_code==200 and "legacy_payload_status" in export.text.splitlines()[0]


def test_payment_processing_report_requires_accounting_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:db.add(User(email="gateway-report-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:med:read"]));db.commit()
        assert client.post("/api/v1/reports/payment_processing_report/runs",headers=auth(client,"gateway-report-denied@example.com"),json={}).status_code==403
