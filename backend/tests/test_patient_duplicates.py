from fastapi.testclient import TestClient

from app.main import app


def patient(first_name="Ana", last_name="García", date_of_birth="1980-01-01", **values):
    return {"first_name": first_name, "last_name": last_name, "date_of_birth": date_of_birth, "sex": "female", **values}


def test_duplicate_registration_requires_reviewed_override_and_candidates_are_scored():
    with TestClient(app) as client:
        token = client.post("/api/v1/auth/token", json={"email": "admin@example.com", "password": "change-me-now"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        original = client.post("/api/v1/patients", headers=headers, json=patient(email="ana@example.com", phone="+52 81 1234 5678"))
        assert original.status_code == 201

        blocked = client.post("/api/v1/patients", headers=headers, json=patient(first_name="ANA", last_name="Garcia"))
        assert blocked.status_code == 409
        detail = blocked.json()["detail"]
        assert detail["code"] == "possible_duplicate_patient"
        assert detail["candidates"][0]["uuid"] == original.json()["uuid"]
        assert detail["candidates"][0]["score"] == 85

        reviewed = client.post("/api/v1/patients", headers=headers, json=patient(
            first_name="ANA", last_name="Garcia", duplicate_override_reason="Identity verified as a distinct twin patient."
        ))
        assert reviewed.status_code == 201

        candidates = client.get(f"/api/v1/patients/{reviewed.json()['uuid']}/duplicate-candidates", headers=headers)
        assert candidates.status_code == 200
        assert candidates.json()[0]["patient"]["uuid"] == original.json()["uuid"]
        assert candidates.json()[0]["matched_fields"] == ["date_of_birth", "last_name", "first_name"]


def test_duplicate_scoring_does_not_block_weak_demographic_overlap():
    with TestClient(app) as client:
        token = client.post("/api/v1/auth/token", json={"email": "admin@example.com", "password": "change-me-now"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.post("/api/v1/patients", headers=headers, json=patient(first_name="María", last_name="Ortega", date_of_birth="1975-04-03")).status_code == 201
        distinct = client.post("/api/v1/patients", headers=headers, json=patient(first_name="Lucía", last_name="Santos", date_of_birth="1975-04-03"))
        assert distinct.status_code == 201
