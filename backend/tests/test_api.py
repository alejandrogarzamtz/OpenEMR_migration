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


def test_auth_required():
    with TestClient(app) as client:
        assert client.get("/api/v1/patients").status_code == 403
