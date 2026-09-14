from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent


def test_fhir_related_person_and_person_contracts():
    with TestClient(app) as client:
        token = client.post(
            "/api/v1/auth/token",
            json={"email": "admin@example.com", "password": "change-me-now"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        patient = client.post(
            "/api/v1/patients",
            headers=headers,
            json={"first_name": "Family", "last_name": "FHIR", "date_of_birth": "2000-01-02", "sex": "unknown"},
        ).json()
        other = client.post(
            "/api/v1/patients",
            headers=headers,
            json={"first_name": "Other", "last_name": "FHIRFamily", "date_of_birth": "2001-02-03", "sex": "unknown"},
        ).json()
        related = client.post(
            f"/api/v1/patients/{patient['uuid']}/related-people",
            headers=headers,
            json={
                "first_name": "Elena",
                "middle_name": "María",
                "last_name": "FHIRFamily",
                "relationship_code": "MTH",
                "role_code": "family",
                "phone": "555-0101",
                "email": "elena.fhir@example.com",
                "sex": "female",
                "address_line1": "20 Family Road",
                "city": "Monterrey",
                "state": "NL",
                "postal_code": "64000",
                "country": "MX",
                "is_primary_contact": True,
                "is_emergency_contact": True,
                "can_make_medical_decisions": True,
                "can_receive_medical_info": True,
                "starts_at": "2026-01-01T00:00:00Z",
            },
        ).json()
        practitioner = client.post(
            "/api/v1/admin/practitioners",
            headers=headers,
            json={"first_name": "Person", "last_name": "FHIRDirectory", "npi": "1777777777", "phone": "555-0110"},
        ).json()

        capability = client.get("/fhir/metadata", headers=headers).json()
        advertised = {entry["type"]: entry for entry in capability["rest"][0]["resource"]}
        assert {"RelatedPerson", "Person"} <= advertised.keys()

        resource = client.get(f"/fhir/RelatedPerson/{related['uuid']}", headers=headers).json()
        assert resource["patient"]["reference"] == f"Patient/{patient['uuid']}"
        assert resource["relationship"][0]["coding"][0] == {
            "system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
            "code": "MTH",
        }
        assert resource["name"][0]["given"] == ["Elena", "María"]
        assert resource["gender"] == "female"
        assert resource["address"][0]["country"] == "MX"
        extensions = {entry["url"]: entry for entry in resource["extension"]}
        assert extensions["https://openrm.org/fhir/StructureDefinition/primary-contact"]["valueBoolean"] is True
        assert extensions["https://openrm.org/fhir/StructureDefinition/can-make-medical-decisions"]["valueBoolean"] is True
        related_search = client.get(
            f"/fhir/RelatedPerson?patient=Patient/{patient['uuid']}&name=Elena&relationship=http://terminology.hl7.org/CodeSystem/v3-RoleCode|MTH&active=true",
            headers=headers,
        ).json()
        assert related_search["total"] == 1 and related_search["entry"][0]["resource"]["id"] == related["uuid"]
        assert client.get(f"/fhir/RelatedPerson?patient={other['uuid']}", headers=headers).json()["total"] == 0

        person = client.get(f"/fhir/Person/{practitioner['uuid']}", headers=headers).json()
        assert person["link"] == [{"target": {"reference": f"Practitioner/{practitioner['uuid']}"}, "assurance": "level4"}]
        assert client.get(f"/fhir/{person['link'][0]['target']['reference']}", headers=headers).status_code == 200
        person_search = client.get("/fhir/Person?name=FHIRDirectory&identifier=1777777777&active=true", headers=headers).json()
        assert practitioner["uuid"] in {entry["resource"]["id"] for entry in person_search["entry"]}
        missing = client.get("/fhir/RelatedPerson/missing", headers=headers)
        assert missing.status_code == 404 and missing.json()["detail"]["resourceType"] == "OperationOutcome"

        with SessionLocal() as db:
            events = set(
                db.execute(
                    select(AuditEvent.action, AuditEvent.resource_type).where(
                        AuditEvent.resource_type.in_(("RelatedPerson", "Person"))
                    )
                ).all()
            )
            assert ("fhir-search", "RelatedPerson") in events
            assert ("fhir-read", "Person") in events
