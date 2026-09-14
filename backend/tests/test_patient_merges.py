from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.import_legacy import patient_for_legacy
from app.models import Patient, PatientCustomFieldDefinition, PatientCustomFieldValue, PatientMerge, PortalAccount, User
from app.security import password_hash
from test_communications import create_portal, staff_headers


def test_reviewed_merge_moves_records_preserves_alias_and_disables_duplicate_portal_identity():
    with TestClient(app) as client:
        staff = staff_headers(client)
        demographics = {"first_name":"Merge","last_name":"Candidate","date_of_birth":"1988-03-04","sex":"unknown","email":"merge@example.com","portal_allowed":True,"allow_email":True}
        target = client.post("/api/v1/patients", headers=staff, json=demographics).json()
        source_response = client.post("/api/v1/patients", headers=staff, json={**demographics,"email":"duplicate@example.com","duplicate_override_reason":"Separate legacy chart pending merge review."})
        assert source_response.status_code == 201
        source = source_response.json()
        create_portal(client, staff, target, "merge-target")
        create_portal(client, staff, source, "merge-source")
        with SessionLocal() as db:
            source_row = db.scalar(select(Patient).where(Patient.uuid == source["uuid"])); target_row = db.scalar(select(Patient).where(Patient.uuid == target["uuid"]))
            source_row.legacy_pid = 987654
            definition = PatientCustomFieldDefinition(field_key="merge_test", title="Merge test"); db.add(definition); db.flush()
            db.add_all([PatientCustomFieldValue(patient_id=source_row.id, definition_id=definition.id, value_text="legacy-source", source="legacy", legacy_value="legacy-source"), PatientCustomFieldValue(patient_id=target_row.id, definition_id=definition.id, value_text="canonical", source="staff")]); db.commit()
            db.add(User(email="merge-viewer@example.com", password_hash=password_hash.hash("merge-viewer-password"), role="viewer", permissions=["patients:demo:read"])); db.commit()
        address = client.post(f"/api/v1/patients/{source['uuid']}/addresses", headers=staff, json={"line1":"55 Legacy Way"}).json()
        encounter = client.post("/api/v1/encounters", headers=staff, json={"patient_uuid":source["uuid"],"occurred_at":"2026-01-02T10:00:00Z","chief_complaint":"Legacy chart visit"}).json()

        preview = client.get(f"/api/v1/patients/{source['uuid']}/merge-preview/{target['uuid']}", headers=staff)
        assert preview.status_code == 200
        assert preview.json()["record_counts"]["patient_addresses"] == 1
        assert any(item["type"] == "portal-account" for item in preview.json()["conflicts"])
        assert any(item["type"] == "custom-field" and item["source_value"] == "legacy-source" for item in preview.json()["conflicts"])
        viewer_token = client.post("/api/v1/auth/token", json={"email":"merge-viewer@example.com","password":"merge-viewer-password"}).json()["access_token"]
        viewer = {"Authorization":f"Bearer {viewer_token}"}
        assert client.get(f"/api/v1/patients/{source['uuid']}/merge-preview/{target['uuid']}", headers=viewer).status_code == 200
        assert client.post(f"/api/v1/patients/{source['uuid']}/merge", headers=viewer, json={"target_patient_uuid":target["uuid"],"confirmation":target["uuid"],"reason":"Viewer must not merge records."}).status_code == 403
        assert client.post(f"/api/v1/patients/{source['uuid']}/merge", headers=staff, json={"target_patient_uuid":target["uuid"],"confirmation":"wrong","reason":"Confirmed duplicate after identity review."}).status_code == 422

        merged = client.post(f"/api/v1/patients/{source['uuid']}/merge", headers=staff, json={"target_patient_uuid":target["uuid"],"confirmation":target["uuid"],"reason":"Confirmed duplicate after identity review."})
        assert merged.status_code == 200
        assert merged.json()["source_uuid"] == source["uuid"] and merged.json()["target_uuid"] == target["uuid"]
        assert merged.json()["moved_counts"]["patient_addresses"] == 1
        assert client.get(f"/api/v1/patients/{source['uuid']}", headers=staff).json()["uuid"] == target["uuid"]
        assert address["uuid"] in {item["uuid"] for item in client.get(f"/api/v1/patients/{target['uuid']}/addresses", headers=staff).json()}
        assert encounter["uuid"] in {item["uuid"] for item in client.get(f"/api/v1/patients/{target['uuid']}/encounters", headers=staff).json()}
        assert source["uuid"] not in {item["uuid"] for item in client.get("/api/v1/patients", headers=staff).json()["items"]}
        history = client.get(f"/api/v1/patients/{target['uuid']}/merges", headers=staff)
        assert history.status_code == 200 and history.json()[0]["source_uuid"] == source["uuid"]
        assert client.post(f"/api/v1/patients/{source['uuid']}/merge", headers=staff, json={"target_patient_uuid":target["uuid"],"confirmation":target["uuid"],"reason":"Attempted repeat merge must fail."}).status_code == 409

        with SessionLocal() as db:
            source_row = db.scalar(select(Patient).where(Patient.uuid == source["uuid"]))
            source_portal = db.scalar(select(PortalAccount).where(PortalAccount.username == "merge-source"))
            evidence = db.scalar(select(PatientMerge).where(PatientMerge.source_uuid == source["uuid"]))
            assert source_row.merged_into_id is not None and source_row.merge_reason
            assert source_portal.patient_id is None and source_portal.active is False
            assert evidence and any(item["type"] == "portal-account" for item in evidence.resolved_conflicts)
            assert any(item["type"] == "custom-field" and item["legacy_value"] == "legacy-source" for item in evidence.resolved_conflicts)
            assert patient_for_legacy(db, 987654).uuid == target["uuid"]
