from base64 import b64decode
from hashlib import sha256

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent


def test_fhir_coverage_document_reference_binary_and_payer_organization():
    with TestClient(app) as client:
        token = client.post(
            "/api/v1/auth/token",
            json={"email": "admin@example.com", "password": "change-me-now"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        patient = client.post(
            "/api/v1/patients",
            headers=headers,
            json={"first_name": "Document", "last_name": "FHIR", "date_of_birth": "1975-03-04", "sex": "unknown"},
        ).json()
        other = client.post(
            "/api/v1/patients",
            headers=headers,
            json={"first_name": "Other", "last_name": "FHIRDoc", "date_of_birth": "1976-04-05", "sex": "unknown"},
        ).json()
        encounter = client.post(
            "/api/v1/encounters",
            headers=headers,
            json={"patient_uuid": patient["uuid"], "occurred_at": "2026-09-14T12:00:00Z"},
        ).json()
        coverage = client.post(
            f"/api/v1/patients/{patient['uuid']}/coverages",
            headers=headers,
            json={
                "payer_name": "FHIR Example Health",
                "payer_identifier": "FHIR-PAYER-01",
                "policy_number": "POLICY-100",
                "group_number": "GROUP-A",
                "plan_name": "Community Plan",
                "subscriber_name": "Document FHIR",
                "starts_on": "2026-01-01",
                "ends_on": "2027-12-31",
            },
        ).json()
        content = b"FHIR document payload\n"
        document = client.post(
            f"/api/v1/patients/{patient['uuid']}/documents?encounter_uuid={encounter['uuid']}",
            headers=headers,
            files={"file": ("care-summary.txt", content, "text/plain")},
        ).json()

        capability = client.get("/fhir/metadata", headers=headers).json()
        advertised = {entry["type"]: entry for entry in capability["rest"][0]["resource"]}
        assert {"Coverage", "DocumentReference", "Binary"} <= advertised.keys()
        assert {item["code"] for item in advertised["Binary"]["interaction"]} == {"read"}

        coverage_resource = client.get(f"/fhir/Coverage/{coverage['uuid']}", headers=headers).json()
        assert coverage_resource["beneficiary"]["reference"] == f"Patient/{patient['uuid']}"
        assert coverage_resource["subscriberId"] == "POLICY-100"
        payer_reference = coverage_resource["payor"][0]["reference"]
        assert payer_reference.startswith("Organization/")
        payer = client.get(f"/fhir/{payer_reference}", headers=headers).json()
        assert payer["name"] == "FHIR Example Health"
        payer_search = client.get("/fhir/Organization?name=Example+Health&active=true", headers=headers).json()
        assert payer["id"] in {entry["resource"]["id"] for entry in payer_search["entry"]}
        assert client.get(f"/fhir/Coverage?patient=Patient/{patient['uuid']}&status=active", headers=headers).json()["total"] == 1
        assert client.get(f"/fhir/Coverage?patient={other['uuid']}", headers=headers).json()["total"] == 0

        reference = client.get(f"/fhir/DocumentReference/{document['uuid']}", headers=headers).json()
        attachment = reference["content"][0]["attachment"]
        assert reference["subject"]["reference"] == f"Patient/{patient['uuid']}"
        assert reference["context"]["encounter"] == [{"reference": f"Encounter/{encounter['uuid']}"}]
        assert b64decode(attachment["hash"]) == sha256(content).digest()
        upload_date = document["uploaded_at"][:10]
        search = client.get(
            f"/fhir/DocumentReference?patient={patient['uuid']}&type=text/plain&date=eq{upload_date}",
            headers=headers,
        ).json()
        assert document["uuid"] in {entry["resource"]["id"] for entry in search["entry"]}
        assert client.get(f"/fhir/DocumentReference?patient={other['uuid']}", headers=headers).json()["total"] == 0

        binary = client.get(attachment["url"], headers=headers)
        assert binary.content == content and binary.headers["content-type"].startswith("text/plain")
        assert binary.headers["etag"] == sha256(content).hexdigest()
        missing = client.get("/fhir/Binary/missing", headers=headers)
        assert missing.status_code == 404 and missing.json()["detail"]["resourceType"] == "OperationOutcome"
        invalid_date = client.get(f"/fhir/DocumentReference?patient={patient['uuid']}&date=bad", headers=headers)
        assert invalid_date.status_code == 400 and invalid_date.json()["detail"]["resourceType"] == "OperationOutcome"

        with SessionLocal() as db:
            events = set(
                db.execute(
                    select(AuditEvent.action, AuditEvent.resource_type).where(
                        AuditEvent.resource_type.in_(("Coverage", "DocumentReference", "Binary"))
                    )
                ).all()
            )
            assert ("fhir-search", "Coverage") in events
            assert ("fhir-read", "DocumentReference") in events
            assert ("fhir-read", "Binary") in events
