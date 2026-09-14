from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent


def test_care_team_lifecycle_supports_polymorphic_members_and_patient_isolation():
    with TestClient(app) as client:
        token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];headers={"Authorization":f"Bearer {token}"}
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"Team","last_name":"Patient","date_of_birth":"1970-01-02","sex":"unknown"}).json();other=client.post("/api/v1/patients",headers=headers,json={"first_name":"Other","last_name":"Team","date_of_birth":"1971-02-03","sex":"unknown"}).json()
        facility=client.post("/api/v1/admin/facilities",headers=headers,json={"name":"Community Clinic"}).json();practitioner=client.post("/api/v1/admin/practitioners",headers=headers,json={"first_name":"Ada","last_name":"Clinician","specialty":"Family medicine","primary_facility_uuid":facility["uuid"]}).json()
        base=f"/api/v1/patients/{patient['uuid']}/care-teams";created=client.post(base,headers=headers,json={"name":"Primary care team","status":"proposed","note":"Coordinate longitudinal care"})
        assert created.status_code==201;team=created.json();path=f"{base}/{team['uuid']}"
        assert client.post(base,headers=headers,json={"name":"Invalid terminal team","status":"inactive"}).status_code==422
        assert client.put(f"/api/v1/patients/{other['uuid']}/care-teams/{team['uuid']}",headers=headers,json={"name":"Wrong","status":"active"}).status_code==404
        catalog=client.get(f"/api/v1/patients/{patient['uuid']}/care-team-catalog",headers=headers).json();assert catalog["practitioners"][0]["name"]=="Ada Clinician"
        provider=client.post(f"{path}/members",headers=headers,json={"member_type":"practitioner","practitioner_uuid":practitioner["uuid"],"facility_uuid":facility["uuid"],"role":"family_medicine_specialist","provider_since":"2026-01-01"})
        assert provider.status_code==201 and provider.json()["display_name"]=="Ada Clinician"
        assert client.post(f"{path}/members",headers=headers,json={"member_type":"practitioner","practitioner_uuid":practitioner["uuid"],"facility_uuid":facility["uuid"],"role":"family_medicine_specialist"}).status_code==409
        contact=client.post(f"{path}/members",headers=headers,json={"member_type":"contact","contact_name":"Jordan Family","role":"caregiver"})
        assert contact.status_code==201
        contact_update=client.patch(f"{path}/members/{contact.json()['uuid']}",headers=headers,json={"role":"legal_guardian","status":"suspended","note":"Temporarily unavailable"})
        assert contact_update.status_code==200 and contact_update.json()["status"]=="suspended"
        facility_member=client.post(f"{path}/members",headers=headers,json={"member_type":"facility","facility_uuid":facility["uuid"],"role":"care_coordination_organization"})
        assert facility_member.status_code==201
        changed=client.put(path,headers=headers,json={"name":"Active primary team","status":"active","note":"Coordinated"});assert changed.status_code==200 and len(changed.json()["members"])==3
        assert client.delete(f"{path}/members/{contact.json()['uuid']}?reason=relationship%20ended",headers=headers).status_code==204
        assert client.delete(f"{path}?reason=team%20replaced",headers=headers).status_code==204
        assert client.get(base,headers=headers).json()==[]
        inactive=client.get(f"{base}?include_inactive=true",headers=headers).json()[0];assert inactive["inactivated_reason"]=="team replaced"
        with SessionLocal() as db:
            actions=set(db.scalars(select(AuditEvent.action).where(AuditEvent.resource_type.in_(("care_team","care_team_member")))))
            assert actions >= {"create","update","inactivate","search"}
