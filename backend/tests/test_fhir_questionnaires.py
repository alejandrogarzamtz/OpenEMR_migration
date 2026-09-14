from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent


def test_fhir_questionnaire_and_response_contracts_preserve_scoring():
    with TestClient(app) as client:
        token = client.post(
            "/api/v1/auth/token",
            json={"email": "admin@example.com", "password": "change-me-now"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        patient = client.post(
            "/api/v1/patients",
            headers=headers,
            json={"first_name": "Screening", "last_name": "FHIR", "date_of_birth": "1990-05-06", "sex": "unknown"},
        ).json()
        other = client.post(
            "/api/v1/patients",
            headers=headers,
            json={"first_name": "Other", "last_name": "FHIRScreen", "date_of_birth": "1991-06-07", "sex": "unknown"},
        ).json()
        encounter = client.post(
            "/api/v1/encounters",
            headers=headers,
            json={"patient_uuid": patient["uuid"], "occurred_at": "2026-09-14T14:00:00Z"},
        ).json()
        definitions = client.get("/api/v1/questionnaires", headers=headers).json()
        phq9 = next(item for item in definitions if item["code"] == "PHQ-9")
        response = client.post(
            f"/api/v1/patients/{patient['uuid']}/questionnaire-responses",
            headers=headers,
            json={
                "questionnaire_uuid": phq9["uuid"],
                "encounter_uuid": encounter["uuid"],
                "answers": {f"q{index}": 1 for index in range(1, 10)},
            },
        ).json()

        capability = client.get("/fhir/metadata", headers=headers).json()
        advertised = {entry["type"]: entry for entry in capability["rest"][0]["resource"]}
        assert {"Questionnaire", "QuestionnaireResponse"} <= advertised.keys()
        questionnaire = client.get(f"/fhir/Questionnaire/{phq9['uuid']}", headers=headers).json()
        assert questionnaire["status"] == "active" and questionnaire["version"] == "1"
        assert questionnaire["code"][0]["code"] == "44249-1"
        assert len(questionnaire["item"]) == 9
        assert questionnaire["item"][0]["text"] == "Little interest or pleasure in doing things"
        assert questionnaire["item"][-1]["text"] == "Thoughts that you would be better off dead, or of hurting yourself"
        assert all(item["type"] == "integer" and item["required"] for item in questionnaire["item"])
        questionnaire_search = client.get("/fhir/Questionnaire?code=http://loinc.org|44249-1&title=Health&status=active", headers=headers).json()
        assert phq9["uuid"] in {entry["resource"]["id"] for entry in questionnaire_search["entry"]}

        resource = client.get(f"/fhir/QuestionnaireResponse/{response['uuid']}", headers=headers).json()
        assert resource["status"] == "completed"
        assert resource["subject"]["reference"] == f"Patient/{patient['uuid']}"
        assert resource["encounter"]["reference"] == f"Encounter/{encounter['uuid']}"
        assert resource["questionnaire"] == f"https://openrm.org/fhir/Questionnaire/{phq9['uuid']}|1"
        assert [item["answer"][0]["valueInteger"] for item in resource["item"]] == [1] * 9
        extensions = {entry["url"]: entry for entry in resource["extension"]}
        assert extensions["https://openrm.org/fhir/StructureDefinition/questionnaire-score"]["valueInteger"] == 9
        assert extensions["https://openrm.org/fhir/StructureDefinition/questionnaire-interpretation"]["valueString"] == "mild"
        authored_date = resource["authored"][:10]
        search = client.get(
            f"/fhir/QuestionnaireResponse?patient=Patient/{patient['uuid']}&questionnaire=Questionnaire/{phq9['uuid']}&authored=eq{authored_date}",
            headers=headers,
        ).json()
        assert search["total"] == 1 and search["entry"][0]["resource"]["id"] == response["uuid"]
        assert client.get(f"/fhir/QuestionnaireResponse?patient={other['uuid']}", headers=headers).json()["total"] == 0
        missing = client.get("/fhir/QuestionnaireResponse/missing", headers=headers)
        assert missing.status_code == 404 and missing.json()["detail"]["resourceType"] == "OperationOutcome"

        with SessionLocal() as db:
            events = set(
                db.execute(
                    select(AuditEvent.action, AuditEvent.resource_type).where(
                        AuditEvent.resource_type.in_(("Questionnaire", "QuestionnaireResponse"))
                    )
                ).all()
            )
            assert ("fhir-search", "Questionnaire") in events
            assert ("fhir-read", "QuestionnaireResponse") in events
