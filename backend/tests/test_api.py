import os
os.environ["DATABASE_URL"] = "sqlite://"
from fastapi.testclient import TestClient
from app.main import app


def test_patient_flow():
    with TestClient(app) as client:
        token = client.post("/api/v1/auth/token", json={"email": "admin@example.com", "password": "change-me-now"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/v1/patients", headers=headers, json={"first_name": "Ada", "last_name": "Lovelace", "date_of_birth": "1815-12-10", "sex": "female", "email": "ada@example.com"})
        assert created.status_code == 201
        patient_id = created.json()["uuid"]
        assert client.get(f"/api/v1/patients/{patient_id}", headers=headers).status_code == 200
        result = client.get("/api/v1/patients?q=Lovelace", headers=headers).json()
        assert result["total"] == 1
        appointment = client.post("/api/v1/appointments", headers=headers, json={"patient_uuid": patient_id, "starts_at": "2026-09-02T10:00:00Z", "ends_at": "2026-09-02T10:30:00Z", "reason": "Follow-up"})
        assert appointment.status_code == 201
        encounter = client.post("/api/v1/encounters", headers=headers, json={"patient_uuid": patient_id, "appointment_uuid": appointment.json()["uuid"], "occurred_at": "2026-09-02T10:01:00Z", "chief_complaint": "Headache"})
        assert encounter.status_code == 201
        assert len(client.get(f"/api/v1/patients/{patient_id}/encounters", headers=headers).json()) == 1
        problem = client.post(f"/api/v1/patients/{patient_id}/clinical-items", headers=headers, json={"category": "problem", "title": "Migraine", "code_system": "ICD-10-CM", "code": "G43.909"})
        assert problem.status_code == 201
        allergy = client.post(f"/api/v1/patients/{patient_id}/clinical-items", headers=headers, json={"category": "allergy", "title": "Penicillin", "reaction": "Rash", "severity": "moderate"})
        assert allergy.status_code == 201
        medication = client.post(f"/api/v1/patients/{patient_id}/clinical-items", headers=headers, json={"category": "medication", "title": "Sumatriptan", "dosage": "50 mg as needed"})
        assert medication.status_code == 201
        summary = client.get(f"/api/v1/patients/{patient_id}/summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["problems"][0]["code"] == "G43.909"
        resolved = client.patch(f"/api/v1/patients/{patient_id}/clinical-items/{problem.json()['uuid']}/status?status_value=resolved", headers=headers)
        assert resolved.json()["status"] == "resolved"
        order = client.post(f"/api/v1/patients/{patient_id}/lab-orders", headers=headers, json={"encounter_uuid": encounter.json()["uuid"], "ordered_at": "2026-09-02T10:05:00Z", "code": "718-7", "name": "Hemoglobin"})
        assert order.status_code == 201
        result = client.post(f"/api/v1/lab-orders/{order.json()['uuid']}/results", headers=headers, json={"observed_at": "2026-09-02T11:00:00Z", "code": "718-7", "name": "Hemoglobin", "value": "13.4", "unit": "g/dL", "reference_range": "12-16", "status": "final"})
        assert result.status_code == 201
        assert client.get(f"/api/v1/lab-orders/{order.json()['uuid']}", headers=headers).json()["results"][0]["value"] == "13.4"
        uploaded = client.post(f"/api/v1/patients/{patient_id}/documents", headers=headers, files={"file": ("note.txt", b"clinical note", "text/plain")})
        assert uploaded.status_code == 201
        downloaded = client.get(f"/api/v1/patients/{patient_id}/documents/{uploaded.json()['uuid']}/content", headers=headers)
        assert downloaded.content == b"clinical note"


def test_auth_required():
    with TestClient(app) as client:
        assert client.get("/api/v1/patients").status_code == 403
