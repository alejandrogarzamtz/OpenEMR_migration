from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User
from app.security import password_hash


def test_patient_flow():
    with TestClient(app) as client:
        token = client.post("/api/v1/auth/token", json={"email": "admin@example.com", "password": "change-me-now"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/v1/patients", headers=headers, json={"first_name": "Ada", "last_name": "Lovelace", "date_of_birth": "1815-12-10", "sex": "female", "email": "ada@example.com"})
        assert created.status_code == 201
        patient_id = created.json()["uuid"]
        assert client.get(f"/api/v1/patients/{patient_id}", headers=headers).status_code == 200
        result = client.get("/api/v1/patients?q=Lovelace", headers=headers).json()
        assert result["total"] == 1
        appointment = client.post("/api/v1/appointments", headers=headers, json={"patient_uuid": patient_id, "starts_at": "2026-09-02T10:00:00Z", "ends_at": "2026-09-02T10:30:00Z", "reason": "Follow-up"})
        assert appointment.status_code == 201
        encounter = client.post("/api/v1/encounters", headers=headers, json={"patient_uuid": patient_id, "appointment_uuid": appointment.json()["uuid"], "occurred_at": "2026-09-02T10:01:00Z", "chief_complaint": "Headache"})
        assert encounter.status_code == 201
        assert len(client.get(f"/api/v1/patients/{patient_id}/encounters", headers=headers).json()) == 1
        problem = client.post(f"/api/v1/patients/{patient_id}/clinical-items", headers=headers, json={"category": "problem", "title": "Migraine", "code_system": "ICD-10-CM", "code": "G43.909"})
        assert problem.status_code == 201
        allergy = client.post(f"/api/v1/patients/{patient_id}/clinical-items", headers=headers, json={"category": "allergy", "title": "Penicillin", "reaction": "Rash", "severity": "moderate"})
        assert allergy.status_code == 201
        medication = client.post(f"/api/v1/patients/{patient_id}/clinical-items", headers=headers, json={"category": "medication", "title": "Sumatriptan", "dosage": "50 mg as needed"})
        assert medication.status_code == 201
        summary = client.get(f"/api/v1/patients/{patient_id}/summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["problems"][0]["code"] == "G43.909"
        resolved = client.patch(f"/api/v1/patients/{patient_id}/clinical-items/{problem.json()['uuid']}/status?status_value=resolved", headers=headers)
        assert resolved.json()["status"] == "resolved"
        order = client.post(f"/api/v1/patients/{patient_id}/lab-orders", headers=headers, json={"encounter_uuid": encounter.json()["uuid"], "ordered_at": "2026-09-02T10:05:00Z", "code": "718-7", "name": "Hemoglobin"})
        assert order.status_code == 201
        result = client.post(f"/api/v1/lab-orders/{order.json()['uuid']}/results", headers=headers, json={"observed_at": "2026-09-02T11:00:00Z", "code": "718-7", "name": "Hemoglobin", "value": "13.4", "unit": "g/dL", "reference_range": "12-16", "status": "final"})
        assert result.status_code == 201
        assert client.get(f"/api/v1/lab-orders/{order.json()['uuid']}", headers=headers).json()["results"][0]["value"] == "13.4"
        uploaded = client.post(f"/api/v1/patients/{patient_id}/documents", headers=headers, files={"file": ("note.txt", b"clinical note", "text/plain")})
        assert uploaded.status_code == 201
        downloaded = client.get(f"/api/v1/patients/{patient_id}/documents/{uploaded.json()['uuid']}/content", headers=headers)
        assert downloaded.content == b"clinical note"
        coverage = client.post(f"/api/v1/patients/{patient_id}/coverages", headers=headers, json={"payer_name":"Acme Health","payer_identifier":"99999","policy_number":"P-123","subscriber_name":"Ada Lovelace"})
        assert coverage.status_code == 201
        charge = client.post(f"/api/v1/patients/{patient_id}/charges", headers=headers, json={"encounter_uuid":encounter.json()["uuid"],"code_system":"CPT","code":"99213","description":"Office visit","units":1,"unit_price":"125.00"})
        assert charge.status_code == 201
        claim = client.post(f"/api/v1/patients/{patient_id}/claims", headers=headers, json={"encounter_uuid":encounter.json()["uuid"],"coverage_uuid":coverage.json()["uuid"],"charge_uuids":[charge.json()["uuid"]]})
        assert claim.json()["total"] == "125.00"
        submitted = client.post(f"/api/v1/claims/{claim.json()['uuid']}/submit", headers=headers)
        assert submitted.json()["status"] == "submitted"
        paid = client.post(f"/api/v1/claims/{claim.json()['uuid']}/payments", headers=headers, json={"amount":"125.00","method":"EFT","reference":"EOB-1"})
        assert paid.json()["status"] == "paid"
        assert paid.json()["balance"] == "0.00"
        assert client.get(f"/api/v1/patients/{patient_id}/claims", headers=headers).json()[0]["status"] == "paid"
        assert client.get(f"/fhir/Patient/{patient_id}", headers=headers).json()["resourceType"] == "Patient"
        assert client.get(f"/fhir/Condition?patient={patient_id}", headers=headers).json()["total"] == 1
        observation = client.get(f"/fhir/Observation?patient={patient_id}", headers=headers).json()
        assert observation["entry"][0]["resource"]["code"]["coding"][0]["system"] == "http://loinc.org"
        immunization = client.post(f"/api/v1/patients/{patient_id}/immunizations", headers=headers, json={"encounter_uuid":encounter.json()["uuid"],"administered_at":"2026-09-02T10:10:00Z","cvx_code":"207","vaccine_name":"COVID-19 mRNA"})
        assert immunization.status_code == 201
        vitals = client.post(f"/api/v1/patients/{patient_id}/vitals", headers=headers, json={"encounter_uuid":encounter.json()["uuid"],"observed_at":"2026-09-02T10:02:00Z","systolic":"120","diastolic":"80","weight_kg":"60","height_cm":"165","oxygen_saturation":"98"})
        assert vitals.status_code == 201
        assert vitals.json()["bmi"] == "22.04"
        prescription = client.post(f"/api/v1/patients/{patient_id}/prescriptions", headers=headers, json={"encounter_uuid":encounter.json()["uuid"],"prescribed_at":"2026-09-02T10:15:00Z","drug_name":"Sumatriptan 50 MG","rxnorm_code":"313161","dosage_instructions":"Take one tablet as needed","quantity":"9","refills":2})
        assert prescription.status_code == 201
        assert len(client.get(f"/api/v1/patients/{patient_id}/immunizations",headers=headers).json()) == 1
        assert len(client.get(f"/api/v1/patients/{patient_id}/prescriptions",headers=headers).json()) == 1
        assert client.get(f"/fhir/Immunization?patient={patient_id}",headers=headers).json()["total"] == 1
        assert client.get(f"/fhir/MedicationRequest?patient={patient_id}",headers=headers).json()["total"] == 1
        assert client.get(f"/fhir/Observation?patient={patient_id}",headers=headers).json()["total"] >= 7
        soap = client.post(f"/api/v1/patients/{patient_id}/clinical-forms", headers=headers, json={"encounter_uuid": encounter.json()["uuid"], "form_type": "soap", "title": "SOAP note", "content": {"subjective": "Headache improving", "objective": "Neurologic exam normal", "assessment": "Migraine", "plan": "Continue treatment"}})
        assert soap.status_code == 201
        assert soap.json()["status"] == "draft"
        assert client.post(f"/api/v1/patients/{patient_id}/clinical-forms/{soap.json()['uuid']}/sign", headers=headers, json={"password":"wrong-password","lock":True}).status_code == 401
        signed = client.post(f"/api/v1/patients/{patient_id}/clinical-forms/{soap.json()['uuid']}/sign", headers=headers, json={"password":"change-me-now","lock":True,"attestation":"I attest that this note is accurate and complete."})
        assert signed.status_code == 201 and signed.json()["is_lock"] is True and signed.json()["integrity_valid"] is True
        assert client.put(f"/api/v1/patients/{patient_id}/clinical-forms/{soap.json()['uuid']}",headers=headers,json={"title":"Changed","content":{"assessment":"tampered"}}).status_code == 423
        assert client.post(f"/api/v1/patients/{patient_id}/clinical-forms/{soap.json()['uuid']}/sign", headers=headers,json={"password":"change-me-now","lock":True}).status_code == 409
        amendment=client.post(f"/api/v1/patients/{patient_id}/clinical-forms/{soap.json()['uuid']}/sign",headers=headers,json={"password":"change-me-now","lock":False,"amendment":"Reviewed after final laboratory result."})
        assert amendment.status_code==201 and amendment.json()["previous_signature_hash"]==signed.json()["signature_hash"]
        signatures=client.get(f"/api/v1/patients/{patient_id}/clinical-forms/{soap.json()['uuid']}/signatures",headers=headers).json()
        assert len(signatures)==2 and all(item["integrity_valid"] for item in signatures)
        form=client.get(f"/api/v1/patients/{patient_id}/clinical-forms?form_type=soap", headers=headers).json()[0]
        assert form["content"]["assessment"] == "Migraine" and form["locked"] and form["signature_count"]==2
        definitions = client.get("/api/v1/questionnaires", headers=headers).json()
        phq9 = next(item for item in definitions if item["code"] == "PHQ-9")
        answers = {f"q{x}": 1 for x in range(1, 10)}
        response = client.post(f"/api/v1/patients/{patient_id}/questionnaire-responses", headers=headers, json={"questionnaire_uuid": phq9["uuid"], "encounter_uuid": encounter.json()["uuid"], "answers": answers})
        assert response.status_code == 201
        assert response.json()["score"] == 9
        assert response.json()["interpretation"] == "mild"
        assert client.get(f"/api/v1/patients/{patient_id}/questionnaire-responses", headers=headers).json()[0]["code"] == "PHQ-9"
        assert client.post(f"/api/v1/patients/{patient_id}/questionnaire-responses", headers=headers, json={"questionnaire_uuid": phq9["uuid"], "answers": {"q1": 4}}).status_code == 422


def test_auth_required():
    with TestClient(app) as client:
        assert client.get("/api/v1/patients").status_code == 403


def test_extended_patient_demographics_and_consent_validation():
    with TestClient(app) as client:
        token = client.post(
            "/api/v1/auth/token",
            json={"email": "admin@example.com", "password": "change-me-now"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "first_name": "Alex",
                "middle_name": "Q",
                "last_name": "Rivera",
                "preferred_name": "Lex",
                "date_of_birth": "1992-06-10",
                "sex": "female",
                "gender_identity": "nonbinary",
                "pronouns": "they/them",
                "language": "es",
                "email": "alex@example.com",
                "phone": "+528112345678",
                "address_line_1": "100 Salud",
                "city": "Monterrey",
                "state": "NL",
                "postal_code": "64000",
                "country_code": "mx",
                "allow_email": True,
                "allow_sms": True,
            },
        )
        assert created.status_code == 201
        assert created.json()["country_code"] == "MX"
        updated = client.patch(
            f"/api/v1/patients/{created.json()['uuid']}",
            headers=headers,
            json={"preferred_name": "Ale", "portal_allowed": True},
        )
        assert updated.status_code == 200
        assert updated.json()["preferred_name"] == "Ale"
        assert updated.json()["portal_allowed"] is True
        replaced = client.put(
            f"/api/v1/patients/{created.json()['uuid']}",
            headers=headers,
            json={
                "first_name": "Alexandra",
                "last_name": "Rivera",
                "date_of_birth": "1992-06-10",
                "sex": "female",
                "language": "es",
                "country_code": "mx",
            },
        )
        assert replaced.status_code == 200
        assert replaced.json()["first_name"] == "Alexandra"
        assert replaced.json()["preferred_name"] is None

        invalid_consent = client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "first_name": "No",
                "last_name": "Email",
                "date_of_birth": "2000-01-01",
                "sex": "unknown",
                "allow_email": True,
            },
        )
        assert invalid_consent.status_code == 422
        future_birth = client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "first_name": "Future",
                "last_name": "Patient",
                "date_of_birth": "2999-01-01",
                "sex": "unknown",
            },
        )
        assert future_birth.status_code == 422


def test_appointment_resources_filters_lifecycle_and_conflicts():
    with TestClient(app) as client:
        token = client.post("/api/v1/auth/token", json={"email": "admin@example.com", "password": "change-me-now"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        patient = client.post("/api/v1/patients", headers=headers, json={"first_name":"Calendar","last_name":"Patient","date_of_birth":"1980-01-01","sex":"unknown"}).json()
        body = {
            "patient_uuid": patient["uuid"], "starts_at": "2026-10-01T15:00:00Z", "ends_at": "2026-10-01T15:30:00Z",
            "title": "Follow-up", "provider_name": "Dr. Rivera", "legacy_provider_id": 42,
            "facility_name": "North Clinic", "legacy_facility_id": 7, "room": "A1",
            "contact_phone": "+528112345678", "send_sms": True,
        }
        created = client.post("/api/v1/appointments", headers=headers, json=body)
        assert created.status_code == 201
        appointment_uuid = created.json()["uuid"]
        assert client.get(f"/api/v1/appointments/{appointment_uuid}", headers=headers).status_code == 200
        filtered = client.get("/api/v1/appointments?provider_id=42&facility_id=7&starts_from=2026-10-01T00:00:00Z&starts_before=2026-10-02T00:00:00Z", headers=headers)
        assert [item["uuid"] for item in filtered.json()] == [appointment_uuid]
        conflict = client.post("/api/v1/appointments", headers=headers, json={**body, "starts_at":"2026-10-01T15:15:00Z", "ends_at":"2026-10-01T15:45:00Z"})
        assert conflict.status_code == 409
        moved = client.patch(f"/api/v1/appointments/{appointment_uuid}", headers=headers, json={"starts_at":"2026-10-01T16:00:00Z", "ends_at":"2026-10-01T16:30:00Z", "status":"confirmed"})
        assert moved.status_code == 200
        assert moved.json()["status"] == "confirmed"
        assert client.delete(f"/api/v1/appointments/{appointment_uuid}", headers=headers).status_code == 204
        assert client.get(f"/api/v1/appointments/{appointment_uuid}", headers=headers).json()["status"] == "cancelled"
        invalid_reminder = client.post("/api/v1/appointments", headers=headers, json={**body, "contact_phone": None})
        assert invalid_reminder.status_code == 422


def test_patient_flow_board_tracks_immutable_transitions_and_syncs_appointment():
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
                "first_name": "Flow",
                "last_name": "Patient",
                "date_of_birth": "1985-04-03",
                "sex": "unknown",
            },
        ).json()
        appointment = client.post(
            "/api/v1/appointments",
            headers=headers,
            json={
                "patient_uuid": patient["uuid"],
                "starts_at": "2026-11-01T15:00:00Z",
                "ends_at": "2026-11-01T15:30:00Z",
                "room": "Lobby",
            },
        ).json()

        started = client.post(
            f"/api/v1/appointments/{appointment['uuid']}/patient-flow",
            headers=headers,
            json={"status": "arrived", "room": "Lobby"},
        )
        assert started.status_code == 201
        episode = started.json()
        assert episode["current_status"] == "arrived"
        assert episode["events"][0]["sequence"] == 1
        assert client.post(
            f"/api/v1/appointments/{appointment['uuid']}/patient-flow",
            headers=headers,
            json={"status": "arrived", "room": "Lobby"},
        ).status_code == 409
        assert client.post(
            f"/api/v1/patient-flow/{episode['uuid']}/events",
            headers=headers,
            json={"status": "arrived", "room": "Lobby"},
        ).status_code == 409

        transitioned = client.post(
            f"/api/v1/patient-flow/{episode['uuid']}/events",
            headers=headers,
            json={"status": "in-progress", "room": "Exam 2"},
        )
        assert transitioned.status_code == 201
        assert [event["sequence"] for event in transitioned.json()["events"]] == [1, 2]
        assert client.get(
            f"/api/v1/appointments/{appointment['uuid']}", headers=headers
        ).json()["room"] == "Exam 2"
        board = client.get(
            "/api/v1/patient-flow?status=in-progress", headers=headers
        ).json()
        assert [item["uuid"] for item in board] == [episode["uuid"]]


def test_explicit_permission_and_inactive_account_enforcement():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(
                email="viewer@example.com",
                password_hash=password_hash.hash("viewer-password"),
                role="viewer",
                permissions=["patients:demo:read"],
            ))
            db.add(User(
                email="disabled@example.com",
                password_hash=password_hash.hash("disabled-password"),
                role="clinician",
                active=False,
                permissions=["patients:med:read"],
            ))
            db.commit()

        viewer_token = client.post(
            "/api/v1/auth/token",
            json={"email": "viewer@example.com", "password": "viewer-password"},
        ).json()["access_token"]
        response = client.get(
            "/api/v1/patients",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 200
        assert client.get("/api/v1/appointments", headers={"Authorization": f"Bearer {viewer_token}"}).status_code == 403
        denied_write = client.post(
            "/api/v1/patients",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "first_name": "Read",
                "last_name": "Only",
                "date_of_birth": "1990-01-01",
                "sex": "unknown",
            },
        )
        assert denied_write.status_code == 403
        assert denied_write.json() == {"detail": "Permission denied"}

        disabled = client.post(
            "/api/v1/auth/token",
            json={"email": "disabled@example.com", "password": "disabled-password"},
        )
        assert disabled.status_code == 401
