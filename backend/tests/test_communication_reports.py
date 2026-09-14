from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import CommunicationDelivery, MessageThread, Patient, SecureMessage, User
from app.security import password_hash


def headers_for(client: TestClient, email: str, password: str) -> dict[str, str]:
    token = client.post("/api/v1/auth/token", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_message_and_delivery_reports_preserve_filters_permissions_snapshots_and_csv():
    with TestClient(app) as client:
        admin_headers = headers_for(client, "admin@example.com", "change-me-now")
        patient_payload = client.post(
            "/api/v1/patients",
            headers=admin_headers,
            json={"first_name": "Marina", "last_name": "Report", "date_of_birth": "1984-04-22", "sex": "female"},
        ).json()
        report_time = datetime(2028, 3, 4, 15, 30, tzinfo=timezone.utc)
        with SessionLocal() as db:
            patient = db.scalar(select(Patient).where(Patient.uuid == patient_payload["uuid"]))
            admin = db.scalar(select(User).where(User.email == "admin@example.com"))
            thread = MessageThread(patient_id=patient.id, subject="Referral follow-up", status="closed", assigned_user_id=admin.id, created_at=report_time, updated_at=report_time)
            db.add(thread); db.flush()
            message = SecureMessage(thread_id=thread.id, sender_kind="staff", sender_user_id=admin.id, sender_name=admin.email, body="Private content is intentionally excluded from reporting.", created_at=report_time)
            delivery = CommunicationDelivery(patient_id=patient.id, channel="direct", recipient="specialist@example.test", subject="Referral", body="Protected payload", status="failed", queued_at=report_time, failed_at=report_time, attempts=2, error_message="test failure")
            db.add_all([message, delivery])
            db.add(User(email="message-report@example.com", password_hash=password_hash.hash("report-password"), role="viewer", permissions=["patients:med:read"]))
            db.commit(); message_uuid = message.uuid; delivery_uuid = delivery.uuid

        message_headers = headers_for(client, "message-report@example.com", "report-password")
        message_run = client.post("/api/v1/reports/message_list/runs", headers=message_headers, json={"date_from": "2028-03-04", "date_to": "2028-03-04", "status": "closed"})
        assert message_run.status_code == 201
        message_report = message_run.json()
        row = next(item for item in message_report["rows"] if item["message_uuid"] == message_uuid)
        assert row["patient"] == "Report, Marina" and row["type"] == "Referral follow-up" and row["status"] == "closed"
        assert "body" not in row and message_report["totals"] == {"messages": 1, "threads": 1}
        assert client.post("/api/v1/reports/direct_message_log/runs", headers=message_headers, json={}).status_code == 403

        delivery_run = client.post("/api/v1/reports/direct_message_log/runs", headers=admin_headers, json={"date_from": "2028-03-04", "date_to": "2028-03-04", "status": "failed"})
        assert delivery_run.status_code == 201
        delivery_report = delivery_run.json()
        delivery_row = next(item for item in delivery_report["rows"] if item["delivery_uuid"] == delivery_uuid)
        assert delivery_row["direction"] == "sent" and delivery_row["channel"] == "direct"
        assert delivery_row["recipient"] == "specialist@example.test" and delivery_row["attempts"] == 2
        assert "body" not in delivery_row and delivery_report["totals"] == {"deliveries": 1, "failed": 1}
        exported = client.get(f"/api/v1/report-runs/{delivery_report['uuid']}/export.csv", headers=admin_headers)
        assert exported.status_code == 200 and delivery_uuid in exported.text
        assert exported.headers["x-report-checksum"] == delivery_report["checksum"]

        catalog = client.get("/api/v1/reports", headers=admin_headers).json()
        status_by_key = {item["key"]: item for item in catalog}
        assert status_by_key["message_list"]["migrated"] is True
        assert status_by_key["message_list"]["permission"] == "patients:med:read"
        assert status_by_key["direct_message_log"]["migrated"] is True
