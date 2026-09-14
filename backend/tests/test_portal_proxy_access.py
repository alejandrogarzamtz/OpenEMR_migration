from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import IdentityAuditEvent, PortalAccessGrant
from test_communications import create_patient, staff_headers


def representative_headers(client: TestClient, staff: dict[str, str]) -> dict[str, str]:
    created = client.post("/api/v1/portal-representatives", headers=staff, json={
        "username": "caregiver-one",
        "email": "caregiver@example.com",
        "display_name": "Casey Caregiver",
        "temporary_password": "temporary-password-123",
    })
    assert created.status_code == 201
    assert created.json()["patient_uuid"] is None
    login = client.post("/api/v1/portal/auth/token", json={"username": "caregiver-one", "password": "temporary-password-123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.post("/api/v1/portal/password", headers=headers, json={"new_password": "permanent-password-456"}).status_code == 204
    return headers


def test_representative_access_is_explicit_scoped_isolated_and_immediately_revocable():
    with TestClient(app) as client:
        staff = staff_headers(client)
        patient = create_patient(client, staff, "ProxyTarget")
        other = create_patient(client, staff, "ProxyOther")
        representative = representative_headers(client, staff)

        assert client.get("/api/v1/portal/contexts", headers=representative).json() == []
        assert client.get("/api/v1/portal/appointments", headers=representative).status_code == 400
        target_headers = {**representative, "X-Portal-Patient": patient["uuid"]}
        assert client.get("/api/v1/portal/appointments", headers=target_headers).status_code == 404

        appointment = client.post("/api/v1/appointments", headers=staff, json={
            "patient_uuid": patient["uuid"], "starts_at": "2026-11-01T14:00:00Z", "ends_at": "2026-11-01T14:30:00Z", "title": "Proxy-visible visit"
        }).json()
        grant = client.post(f"/api/v1/patients/{patient['uuid']}/portal-access-grants", headers=staff, json={
            "representative_username": "caregiver-one",
            "relationship_code": "caregiver",
            "scopes": ["appointments", "records"],
            "consent_basis": "patient-consent",
            "evidence_reference": "consent-2026-001",
        })
        assert grant.status_code == 201
        assert grant.json()["scopes"] == ["appointments", "records"]
        contexts = client.get("/api/v1/portal/contexts", headers=representative).json()
        assert contexts == [{"patient_uuid": patient["uuid"], "patient_name": "ProxyTarget Portal", "relationship_code": "caregiver", "scopes": ["appointments", "records"], "is_self": False}]
        assert client.get("/api/v1/portal/appointments", headers=target_headers).json()[0]["uuid"] == appointment["uuid"]
        assert client.get("/api/v1/portal/messages", headers=target_headers).status_code == 403
        assert client.get("/api/v1/portal/appointments", headers={**representative, "X-Portal-Patient": other["uuid"]}).status_code == 404

        listed = client.get(f"/api/v1/patients/{patient['uuid']}/portal-access-grants", headers=staff)
        assert listed.status_code == 200 and listed.json()[0]["representative_name"] == "Casey Caregiver"
        revoked = client.post(f"/api/v1/patients/{patient['uuid']}/portal-access-grants/{grant.json()['uuid']}/revoke", headers=staff, json={"reason": "Consent withdrawn"})
        assert revoked.status_code == 200 and revoked.json()["revoked_at"] is not None
        assert client.get("/api/v1/portal/appointments", headers=target_headers).status_code == 404

    with SessionLocal() as db:
        stored = db.scalar(select(PortalAccessGrant).where(PortalAccessGrant.uuid == grant.json()["uuid"]))
        assert stored.revoke_reason == "Consent withdrawn"
        audit = db.scalar(select(IdentityAuditEvent).where(IdentityAuditEvent.identity_kind == "portal", IdentityAuditEvent.patient_id == stored.patient_id, IdentityAuditEvent.action == "search", IdentityAuditEvent.resource_type == "appointment"))
        assert audit is not None and audit.portal_account_id == stored.grantee_portal_account_id
