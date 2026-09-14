from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import IdentityAuditEvent
from test_communications import create_patient, create_portal, staff_headers


def test_portal_records_require_release_and_are_patient_isolated():
    with TestClient(app) as client:
        staff = staff_headers(client)
        first = create_patient(client, staff, "RecordsOne")
        second = create_patient(client, staff, "RecordsTwo")
        first_portal = create_portal(client, staff, first, "records-one")
        second_portal = create_portal(client, staff, second, "records-two")

        appointment = client.post("/api/v1/appointments", headers=staff, json={
            "patient_uuid": first["uuid"], "starts_at": "2026-10-01T14:00:00Z", "ends_at": "2026-10-01T14:30:00Z", "title": "Follow-up"
        })
        assert appointment.status_code == 201
        assert [item["uuid"] for item in client.get("/api/v1/portal/appointments", headers=first_portal).json()] == [appointment.json()["uuid"]]
        assert client.get("/api/v1/portal/appointments", headers=second_portal).json() == []

        order = client.post(f"/api/v1/patients/{first['uuid']}/lab-orders", headers=staff, json={
            "ordered_at": "2026-09-15T10:00:00Z", "code": "718-7", "name": "Hemoglobin"
        }).json()
        preliminary = client.post(f"/api/v1/lab-orders/{order['uuid']}/results", headers=staff, json={
            "observed_at": "2026-09-15T11:00:00Z", "code": "718-7", "name": "Hemoglobin", "value": "pending", "status": "preliminary"
        }).json()
        final = client.post(f"/api/v1/lab-orders/{order['uuid']}/results", headers=staff, json={
            "observed_at": "2026-09-15T12:00:00Z", "code": "718-7", "name": "Hemoglobin", "value": "14.1", "unit": "g/dL", "status": "final"
        }).json()
        assert client.post(f"/api/v1/lab-results/{preliminary['uuid']}/release", headers=staff).status_code == 409
        assert client.get("/api/v1/portal/results", headers=first_portal).json() == []
        assert client.post(f"/api/v1/lab-results/{final['uuid']}/release", headers=staff).status_code == 200
        assert client.get("/api/v1/portal/results", headers=first_portal).json()[0]["value"] == "14.1"
        assert client.get("/api/v1/portal/results", headers=second_portal).json() == []

        document = client.post(f"/api/v1/patients/{first['uuid']}/documents", headers=staff, files={"file": ("instructions.txt", b"private instructions", "text/plain")}).json()
        assert client.get("/api/v1/portal/documents", headers=first_portal).json() == []
        assert client.post(f"/api/v1/patients/{first['uuid']}/documents/{document['uuid']}/release", headers=staff).status_code == 200
        assert client.get(f"/api/v1/portal/documents/{document['uuid']}/content", headers=second_portal).status_code == 404
        downloaded = client.get(f"/api/v1/portal/documents/{document['uuid']}/content", headers=first_portal)
        assert downloaded.content == b"private instructions"
        assert client.delete(f"/api/v1/patients/{first['uuid']}/documents/{document['uuid']}/release", headers=staff).status_code == 204
        assert client.get(f"/api/v1/portal/documents/{document['uuid']}/content", headers=first_portal).status_code == 404

        encounter = client.post("/api/v1/encounters", headers=staff, json={"patient_uuid": first["uuid"], "occurred_at": "2026-09-15T13:00:00Z", "type": "office"}).json()
        form = client.post(f"/api/v1/patients/{first['uuid']}/clinical-forms", headers=staff, json={"encounter_uuid": encounter["uuid"], "form_type": "soap", "title": "Visit summary", "content": {"plan": "Hydrate"}}).json()
        assert client.post(f"/api/v1/patients/{first['uuid']}/clinical-forms/{form['uuid']}/release", headers=staff).status_code == 409
        client.post(f"/api/v1/patients/{first['uuid']}/clinical-forms/{form['uuid']}/sign", headers=staff)
        assert client.post(f"/api/v1/patients/{first['uuid']}/clinical-forms/{form['uuid']}/release", headers=staff).status_code == 200
        assert client.get("/api/v1/portal/forms", headers=first_portal).json()[0]["content"] == {"plan": "Hydrate"}
        assert client.get("/api/v1/portal/forms", headers=second_portal).json() == []

    with SessionLocal() as db:
        events = list(db.scalars(select(IdentityAuditEvent).where(IdentityAuditEvent.identity_kind == "portal")))
        assert any(event.action == "read" and event.resource_type == "document" for event in events)
        assert all(event.portal_account_id is not None and event.patient_id is not None for event in events)
