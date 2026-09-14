from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent, User
from app.security import password_hash


def login(client: TestClient,email: str,password: str) -> dict[str,str]:
    response=client.post("/api/v1/auth/token",json={"email":email,"password":password})
    assert response.status_code==200
    return {"Authorization":f"Bearer {response.json()['access_token']}"}


def test_social_history_is_versioned_validated_audited_and_patient_scoped():
    with TestClient(app) as client:
        admin=login(client,"admin@example.com","change-me-now")
        patient=client.post("/api/v1/patients",headers=admin,json={"first_name":"Social","last_name":"History","date_of_birth":"1985-01-02","sex":"unknown"}).json()
        assert client.post(f"/api/v1/patients/{patient['uuid']}/social-history",headers=admin,json={}).status_code==422
        first=client.post(f"/api/v1/patients/{patient['uuid']}/social-history",headers=admin,json={"recorded_at":"2034-01-02T10:00:00Z","tobacco":"Never","alcohol":"Occasional"})
        second=client.post(f"/api/v1/patients/{patient['uuid']}/social-history",headers=admin,json={"recorded_at":"2034-02-03T10:00:00Z","tobacco":"Former","exercise_patterns":"Walks daily","additional_history":"Reviewed with patient"})
        assert first.status_code==201 and second.status_code==201
        versions=client.get(f"/api/v1/patients/{patient['uuid']}/social-history",headers=admin)
        assert versions.status_code==200 and [item["tobacco"] for item in versions.json()]==["Former","Never"]
        assert versions.json()[0]["source_payload"] is None and versions.json()[0]["legacy_patient_id"]==0
        assert client.get("/api/v1/patients/00000000-0000-0000-0000-000000000000/social-history",headers=admin).status_code==404
        with SessionLocal() as db:
            events=list(db.scalars(select(AuditEvent).where(AuditEvent.resource_type=="social_history")))
            assert sum(event.action=="create" for event in events)>=2 and any(event.action=="search" for event in events)


def test_social_history_write_requires_medical_write_permission():
    with TestClient(app) as client:
        admin=login(client,"admin@example.com","change-me-now")
        patient=client.post("/api/v1/patients",headers=admin,json={"first_name":"Read","last_name":"Only","date_of_birth":"1986-01-02","sex":"unknown"}).json()
        with SessionLocal() as db:
            db.add(User(email="social-reader@example.com",password_hash=password_hash.hash("social-password"),role="viewer",permissions=["patients:med:read"]));db.commit()
        reader=login(client,"social-reader@example.com","social-password")
        assert client.get(f"/api/v1/patients/{patient['uuid']}/social-history",headers=reader).status_code==200
        assert client.post(f"/api/v1/patients/{patient['uuid']}/social-history",headers=reader,json={"tobacco":"Never"}).status_code==403
