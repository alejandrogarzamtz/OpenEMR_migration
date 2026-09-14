from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent


def test_fhir_core_resource_search_read_references_and_audit():
    with TestClient(app) as client:
        token = client.post(
            "/api/v1/auth/token",
            json={"email": "admin@example.com", "password": "change-me-now"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        patient = client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "first_name": "Core",
                "last_name": "FHIR",
                "date_of_birth": "1980-04-05",
                "sex": "unknown",
            },
        ).json()
        facility = client.post(
            "/api/v1/admin/facilities",
            headers=headers,
            json={
                "name": "FHIR North Clinic",
                "phone": "555-0100",
                "street": "100 Health Ave",
                "city": "Monterrey",
                "country_code": "MX",
                "npi": "1234567890",
            },
        ).json()
        practitioner = client.post(
            "/api/v1/admin/practitioners",
            headers=headers,
            json={
                "first_name": "Grace",
                "last_name": "FHIRCore",
                "npi": "1098765432",
                "specialty": "Family medicine",
                "primary_facility_uuid": facility["uuid"],
            },
        ).json()
        appointment = client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_uuid": patient["uuid"],
                "facility_uuid": facility["uuid"],
                "starts_at": "2026-11-01T10:00:00Z",
                "ends_at": "2026-11-01T10:30:00Z",
                "title": "FHIR follow-up",
                "reason": "Care review",
                "provider_name": "Grace FHIRCore",
            },
        ).json()
        encounter = client.post(
            "/api/v1/encounters",
            headers=headers,
            json={
                "patient_uuid": patient["uuid"],
                "appointment_uuid": appointment["uuid"],
                "occurred_at": "2026-11-01T10:02:00Z",
                "chief_complaint": "Care review",
            },
        ).json()
        problem = client.post(
            f"/api/v1/patients/{patient['uuid']}/clinical-items",
            headers=headers,
            json={"category": "problem", "title": "Hypertension", "code_system": "SNOMED", "code": "38341003"},
        ).json()
        allergy = client.post(
            f"/api/v1/patients/{patient['uuid']}/clinical-items",
            headers=headers,
            json={"category": "allergy", "title": "Latex", "reaction": "Rash"},
        ).json()
        medication = client.post(
            f"/api/v1/patients/{patient['uuid']}/clinical-items",
            headers=headers,
            json={"category": "medication", "title": "Lisinopril", "dosage": "10 mg daily"},
        ).json()
        immunization = client.post(
            f"/api/v1/patients/{patient['uuid']}/immunizations",
            headers=headers,
            json={"encounter_uuid": encounter["uuid"], "administered_at": "2026-11-01T10:10:00Z", "cvx_code": "140", "vaccine_name": "Influenza"},
        ).json()
        prescription = client.post(
            f"/api/v1/patients/{patient['uuid']}/prescriptions",
            headers=headers,
            json={"encounter_uuid": encounter["uuid"], "prescribed_at": "2026-11-01T10:15:00Z", "drug_name": "Lisinopril 10 MG", "rxnorm_code": "314076", "dosage_instructions": "Take daily"},
        ).json()
        vitals = client.post(
            f"/api/v1/patients/{patient['uuid']}/vitals",
            headers=headers,
            json={"encounter_uuid": encounter["uuid"], "observed_at": "2026-11-01T10:03:00Z", "systolic": "125", "diastolic": "82"},
        ).json()

        capability = client.get("/fhir/metadata", headers=headers).json()
        advertised = {resource["type"]: resource for resource in capability["rest"][0]["resource"]}
        expected = {"Appointment", "Encounter", "Organization", "Location", "Practitioner", "Condition", "AllergyIntolerance", "MedicationStatement", "Observation", "Immunization", "MedicationRequest"}
        assert expected <= advertised.keys()
        assert all({item["code"] for item in advertised[name]["interaction"]} == {"read", "search-type"} for name in expected)

        appointment_resource = client.get(f"/fhir/Appointment/{appointment['uuid']}", headers=headers).json()
        assert appointment_resource["status"] == "arrived"
        assert {entry["actor"].get("reference") for entry in appointment_resource["participant"]} >= {f"Patient/{patient['uuid']}", f"Location/{facility['uuid']}"}
        assert client.get(f"/fhir/Appointment?patient=Patient/{patient['uuid']}&status=arrived", headers=headers).json()["total"] == 1

        encounter_resource = client.get(f"/fhir/Encounter/{encounter['uuid']}", headers=headers).json()
        assert encounter_resource["subject"]["reference"] == f"Patient/{patient['uuid']}"
        assert encounter_resource["appointment"] == [{"reference": f"Appointment/{appointment['uuid']}"}]
        assert client.get(f"/fhir/Encounter?patient={patient['uuid']}&status=in-progress", headers=headers).json()["total"] == 1

        organization = client.get(f"/fhir/Organization/{facility['uuid']}", headers=headers).json()
        assert organization["name"] == "FHIR North Clinic" and organization["address"][0]["city"] == "Monterrey"
        organization_search = client.get("/fhir/Organization?name=North&active=true", headers=headers).json()
        assert facility["uuid"] in {entry["resource"]["id"] for entry in organization_search["entry"]}
        location = client.get(f"/fhir/Location/{facility['uuid']}", headers=headers).json()
        assert location["managingOrganization"]["reference"] == f"Organization/{facility['uuid']}"
        location_search = client.get("/fhir/Location?name=North&active=true", headers=headers).json()
        assert facility["uuid"] in {entry["resource"]["id"] for entry in location_search["entry"]}
        practitioner_resource = client.get(f"/fhir/Practitioner/{practitioner['uuid']}", headers=headers).json()
        assert practitioner_resource["identifier"][0]["value"] == "1098765432"
        practitioner_search = client.get("/fhir/Practitioner?family=FHIRCore&identifier=1098765432", headers=headers).json()
        assert practitioner["uuid"] in {entry["resource"]["id"] for entry in practitioner_search["entry"]}

        reads = (
            ("Condition", problem["uuid"]),
            ("AllergyIntolerance", allergy["uuid"]),
            ("MedicationStatement", medication["uuid"]),
            ("Immunization", immunization["uuid"]),
            ("MedicationRequest", prescription["uuid"]),
            ("Observation", f"{vitals['uuid']}-systolic"),
        )
        for resource_type, resource_uuid in reads:
            response = client.get(f"/fhir/{resource_type}/{resource_uuid}", headers=headers)
            assert response.status_code == 200
            assert response.json()["resourceType"] == resource_type
        missing = client.get("/fhir/Encounter/missing", headers=headers)
        assert missing.status_code == 404 and missing.json()["detail"]["resourceType"] == "OperationOutcome"

        client.get(f"/fhir/Condition?patient={patient['uuid']}", headers=headers)
        with SessionLocal() as db:
            actions = set(
                db.scalars(
                    select(AuditEvent.action).where(
                        AuditEvent.resource_type == "Condition",
                        AuditEvent.resource_id == patient["uuid"],
                    )
                )
            )
            assert "fhir-search" in actions
