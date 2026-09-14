from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent


def test_fhir_service_request_and_diagnostic_report_contracts():
    with TestClient(app) as client:
        token = client.post(
            "/api/v1/auth/token",
            json={"email": "admin@example.com", "password": "change-me-now"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        patient = client.post(
            "/api/v1/patients",
            headers=headers,
            json={"first_name": "Lab", "last_name": "FHIR", "date_of_birth": "1988-01-02", "sex": "unknown"},
        ).json()
        other = client.post(
            "/api/v1/patients",
            headers=headers,
            json={"first_name": "Other", "last_name": "FHIRLab", "date_of_birth": "1989-02-03", "sex": "unknown"},
        ).json()
        encounter = client.post(
            "/api/v1/encounters",
            headers=headers,
            json={"patient_uuid": patient["uuid"], "occurred_at": "2026-12-01T08:00:00Z"},
        ).json()
        order = client.post(
            f"/api/v1/patients/{patient['uuid']}/lab-orders",
            headers=headers,
            json={
                "encounter_uuid": encounter["uuid"],
                "ordered_at": "2026-12-01T08:05:00Z",
                "code": "718-7",
                "name": "Hemoglobin",
                "priority": "urgent",
                "instructions": "Collect venous sample",
            },
        ).json()
        pending_order = client.post(
            f"/api/v1/patients/{patient['uuid']}/lab-orders",
            headers=headers,
            json={"ordered_at": "2026-12-02T08:05:00Z", "code": "6690-2", "name": "Leukocytes"},
        ).json()

        service = client.get(f"/fhir/ServiceRequest/{order['uuid']}", headers=headers).json()
        assert service["status"] == "active" and service["priority"] == "urgent"
        assert service["subject"]["reference"] == f"Patient/{patient['uuid']}"
        assert service["encounter"]["reference"] == f"Encounter/{encounter['uuid']}"
        assert client.get(f"/fhir/DiagnosticReport/{pending_order['uuid']}", headers=headers).status_code == 404

        result = client.post(
            f"/api/v1/lab-orders/{order['uuid']}/results",
            headers=headers,
            json={
                "observed_at": "2026-12-01T09:00:00Z",
                "code": "718-7",
                "name": "Hemoglobin",
                "value": "14.2",
                "unit": "g/dL",
                "reference_range": "12-16",
                "status": "final",
            },
        ).json()
        completed_service = client.get(f"/fhir/ServiceRequest/{order['uuid']}", headers=headers).json()
        assert completed_service["status"] == "completed"
        report = client.get(f"/fhir/DiagnosticReport/{order['uuid']}", headers=headers).json()
        assert report["status"] == "final"
        assert report["basedOn"] == [{"reference": f"ServiceRequest/{order['uuid']}"}]
        assert report["result"] == [{"reference": f"Observation/{result['uuid']}", "display": "Hemoglobin"}]
        observation = client.get(f"/fhir/Observation/{result['uuid']}", headers=headers)
        assert observation.status_code == 200 and observation.json()["valueQuantity"]["value"] == 14.2

        service_search = client.get(
            f"/fhir/ServiceRequest?patient=Patient/{patient['uuid']}&status=completed&code=http://loinc.org|718-7&authored=eq2026-12-01",
            headers=headers,
        ).json()
        assert service_search["total"] == 1 and service_search["entry"][0]["resource"]["id"] == order["uuid"]
        report_search = client.get(
            f"/fhir/DiagnosticReport?patient={patient['uuid']}&status=final&code=718-7&date=ge2026-12-01",
            headers=headers,
        ).json()
        assert report_search["total"] == 1 and report_search["entry"][0]["resource"]["id"] == order["uuid"]
        assert client.get(f"/fhir/DiagnosticReport?patient={other['uuid']}", headers=headers).json()["total"] == 0

        capability = client.get("/fhir/metadata", headers=headers).json()
        advertised = {entry["type"]: entry for entry in capability["rest"][0]["resource"]}
        assert {"ServiceRequest", "DiagnosticReport"} <= advertised.keys()
        assert {item["code"] for item in advertised["ServiceRequest"]["interaction"]} == {"read", "search-type"}

        with SessionLocal() as db:
            events = set(
                db.execute(
                    select(AuditEvent.action, AuditEvent.resource_type).where(
                        AuditEvent.resource_type.in_(("ServiceRequest", "DiagnosticReport"))
                    )
                ).all()
            )
            assert ("fhir-read", "ServiceRequest") in events
            assert ("fhir-search", "DiagnosticReport") in events
