from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent


def test_patient_provider_assignment_history_and_audit():
    with TestClient(app) as client:
        token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];headers={"Authorization":f"Bearer {token}"}
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"Assigned","last_name":"Patient","date_of_birth":"1990-01-01","sex":"unknown"}).json()
        facility=client.post("/api/v1/admin/facilities",headers=headers,json={"name":"Assignment Clinic"}).json()
        first=client.post("/api/v1/admin/practitioners",headers=headers,json={"first_name":"First","last_name":"Doctor","primary_facility_uuid":facility["uuid"]}).json()
        second=client.post("/api/v1/admin/practitioners",headers=headers,json={"first_name":"Second","last_name":"Doctor","primary_facility_uuid":facility["uuid"]}).json()
        path=f"/api/v1/patients/{patient['uuid']}/provider-assignments"
        created=client.post(path,headers=headers,json={"practitioner_uuid":first["uuid"],"role":"primary","assigned_at":"2026-01-01T00:00:00Z"})
        assert created.status_code==201 and created.json()["facility_uuid"]==facility["uuid"]
        replacement=client.post(path,headers=headers,json={"practitioner_uuid":second["uuid"],"facility_uuid":facility["uuid"],"role":"primary","assigned_at":"2026-02-01T00:00:00Z"})
        assert replacement.status_code==201
        records=client.get(path,headers=headers).json()
        assert [(item["practitioner_name"],item["status"]) for item in records]==[("Second Doctor","active"),("First Doctor","ended")]
        assert records[1]["ended_at"].startswith("2026-02-01T00:00:00")
        assert client.delete(f"{path}/{replacement.json()['uuid']}",headers=headers).status_code==204
        assert client.get(path,headers=headers).json()[0]["status"]=="ended"
        with SessionLocal() as db:
            actions={event.action for event in db.query(AuditEvent).filter(AuditEvent.resource_type=="patient_provider_assignment")}
            assert {"create","search","end"}.issubset(actions)
