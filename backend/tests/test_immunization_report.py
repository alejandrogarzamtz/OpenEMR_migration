from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Immunization, Patient, User
from app.security import password_hash


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    token = client.post("/api/v1/auth/token", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_immunization_report_filters_errors_protects_access_and_exports_snapshot():
    with TestClient(app) as client:
        admin_headers = login(client, "admin@example.com", "change-me-now")
        patient_payload = client.post(
            "/api/v1/patients",
            headers=admin_headers,
            json={"first_name": "Isa", "last_name": "Vaccine", "date_of_birth": "2012-06-03", "sex": "female"},
        ).json()
        administered_at = datetime(2029, 5, 6, 14, 15, tzinfo=timezone.utc)
        with SessionLocal() as db:
            patient = db.scalar(select(Patient).where(Patient.uuid == patient_payload["uuid"]))
            valid = Immunization(patient_id=patient.id, administered_at=administered_at, cvx_code="207", vaccine_name="COVID-19 mRNA", manufacturer="Example Pharma", lot_number="LOT-29", route="IM", site="left arm", dose="0.3 mL", status="completed")
            erroneous = Immunization(patient_id=patient.id, administered_at=administered_at, cvx_code="999", vaccine_name="Erroneous entry", status="entered-in-error")
            db.add_all([valid, erroneous, User(email="immunization-report@example.com", password_hash=password_hash.hash("report-password"), role="viewer", permissions=["patients:med:read"]), User(email="demographics-only@example.com", password_hash=password_hash.hash("report-password"), role="viewer", permissions=["patients:demo:read"])])
            db.commit(); valid_uuid = valid.uuid; erroneous_uuid = erroneous.uuid

        headers = login(client, "immunization-report@example.com", "report-password")
        run = client.post("/api/v1/reports/immunization_report/runs", headers=headers, json={"date_from": "2029-05-06", "date_to": "2029-05-06", "status": "completed"})
        assert run.status_code == 201
        report = run.json()
        assert report["row_count"] == 1 and report["totals"] == {"immunizations": 1, "patients": 1, "refused": 0}
        row = report["rows"][0]
        assert row["immunization_uuid"] == valid_uuid and row["patient"] == "Vaccine, Isa"
        assert row["cvx_code"] == "207" and row["manufacturer"] == "Example Pharma" and row["lot_number"] == "LOT-29"
        assert erroneous_uuid not in {item["immunization_uuid"] for item in report["rows"]}
        stored = client.get(f"/api/v1/report-runs/{report['uuid']}", headers=headers)
        assert stored.status_code == 200 and stored.json()["checksum"] == report["checksum"]
        exported = client.get(f"/api/v1/report-runs/{report['uuid']}/export.csv", headers=headers)
        assert exported.status_code == 200 and valid_uuid in exported.text
        assert exported.headers["x-report-checksum"] == report["checksum"]

        denied_headers = login(client, "demographics-only@example.com", "report-password")
        assert client.post("/api/v1/reports/immunization_report/runs", headers=denied_headers, json={}).status_code == 403
        catalog = client.get("/api/v1/reports", headers=headers).json()
        item = next(entry for entry in catalog if entry["key"] == "immunization_report")
        assert item["migrated"] is True and item["permission"] == "patients:med:read"
