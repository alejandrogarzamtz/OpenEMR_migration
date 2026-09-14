from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent, AuditEventSeal, IdentityAuditEvent, User
from app.security import password_hash


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    token = client.post("/api/v1/auth/token", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_audit_seals_detect_modified_and_deleted_events_with_admin_only_report():
    with TestClient(app) as client:
        headers = login(client, "admin@example.com", "change-me-now")
        first = client.post("/api/v1/patients", headers=headers, json={"first_name": "Audit", "last_name": "Modified", "date_of_birth": "1980-01-01", "sex": "unknown"}).json()
        second = client.post("/api/v1/patients", headers=headers, json={"first_name": "Audit", "last_name": "Deleted", "date_of_birth": "1981-01-01", "sex": "unknown"}).json()
        third = client.post("/api/v1/patients", headers=headers, json={"first_name": "Audit", "last_name": "Unsealed", "date_of_birth": "1982-01-01", "sex": "unknown"}).json()
        with SessionLocal() as db:
            modified = db.scalar(select(AuditEvent).where(AuditEvent.resource_type == "patient", AuditEvent.resource_id == first["uuid"]))
            deleted = db.scalar(select(AuditEvent).where(AuditEvent.resource_type == "patient", AuditEvent.resource_id == second["uuid"]))
            unsealed = db.scalar(select(AuditEvent).where(AuditEvent.resource_type == "patient", AuditEvent.resource_id == third["uuid"]))
            assert db.scalar(select(AuditEventSeal).where(AuditEventSeal.stream == "staff", AuditEventSeal.event_id == modified.id))
            assert db.scalar(select(AuditEventSeal).where(AuditEventSeal.stream == "staff", AuditEventSeal.event_id == deleted.id))
            missing_seal = db.scalar(select(AuditEventSeal).where(AuditEventSeal.stream == "staff", AuditEventSeal.event_id == unsealed.id))
            admin = db.scalar(select(User).where(User.email == "admin@example.com"))
            identity = IdentityAuditEvent(identity_kind="staff", user_id=admin.id, action="test", resource_type="integrity", detail="original")
            db.add(identity); db.commit()
            assert db.scalar(select(AuditEventSeal).where(AuditEventSeal.stream == "identity", AuditEventSeal.event_id == identity.id))
            modified.detail = "database value changed outside the application"
            identity.detail = "identity value changed outside the application"
            deleted_id = deleted.id
            unsealed_id = unsealed.id
            identity_id = identity.id
            db.delete(deleted)
            db.delete(missing_seal)
            db.commit(); modified_id = modified.id

        run = client.post("/api/v1/reports/audit_log_tamper_report/runs", headers=headers, json={})
        assert run.status_code == 201
        report = run.json(); failures = {(row["stream"], row["event_id"], row["integrity"]): row for row in report["rows"]}
        assert ("staff", modified_id, "tampered") in failures and ("staff", deleted_id, "deleted") in failures
        assert ("staff", unsealed_id, "unsealed") in failures and ("identity", identity_id, "tampered") in failures
        assert failures[("staff", modified_id, "tampered")]["stored_checksum"] != failures[("staff", modified_id, "tampered")]["computed_checksum"]
        assert failures[("staff", deleted_id, "deleted")]["computed_checksum"] is None
        assert report["totals"]["tampered"] >= 2 and report["totals"]["deleted"] >= 1 and report["totals"]["unsealed"] >= 1
        assert report["totals"]["integrity_failures"] == report["row_count"]
        exported = client.get(f"/api/v1/report-runs/{report['uuid']}/export.csv", headers=headers)
        assert exported.status_code == 200 and "tampered" in exported.text and "deleted" in exported.text
        assert exported.headers["x-report-checksum"] == report["checksum"]

        with SessionLocal() as db:
            db.add(User(email="audit-denied@example.com", password_hash=password_hash.hash("report-password"), role="viewer", permissions=["patients:med:read"])); db.commit()
        denied = login(client, "audit-denied@example.com", "report-password")
        assert client.post("/api/v1/reports/audit_log_tamper_report/runs", headers=denied, json={}).status_code == 403
        catalog = client.get("/api/v1/reports", headers=headers).json()
        item = next(entry for entry in catalog if entry["key"] == "audit_log_tamper_report")
        assert item["migrated"] is True and item["permission"] == "admin:super:read"
