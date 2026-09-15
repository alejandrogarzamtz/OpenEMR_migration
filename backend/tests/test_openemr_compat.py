from fastapi.testclient import TestClient

from app.main import app
from test_communications import create_portal


def staff(client:TestClient):
    token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_standard_api_core_contract_and_legacy_envelope():
    with TestClient(app) as client:
        headers=staff(client)
        version=client.get("/apis/default/api/version",headers=headers)
        assert version.status_code==200 and version.json()["data"]["version"]=="0.1.0"
        facility=client.post("/apis/default/api/facility",headers=headers,json={"name":"Compatibility Clinic","city":"Monterrey"})
        assert facility.status_code==201 and facility.json()["validationErrors"]==[]
        facility_uuid=facility.json()["data"]["uuid"]
        assert client.get(f"/apis/default/api/facility/{facility_uuid}",headers=headers).status_code==200
        renamed=client.put(f"/apis/default/api/facility/{facility_uuid}",headers=headers,json={"name":"Compatibility Clinic North"})
        assert renamed.status_code==200 and renamed.json()["data"]["name"].endswith("North")
        patient=client.post("/apis/default/api/patient",headers=headers,json={"fname":"Legacy","lname":"Client","DOB":"1990-01-01","sex":"unknown","portal_allowed":True})
        assert patient.status_code==201,patient.text
        patient_data=patient.json()["data"];assert patient_data["fname"]=="Legacy" and patient_data["lname"]=="Client"
        fetched=client.get(f"/apis/default/api/patient/{patient_data['uuid']}",headers=headers)
        assert fetched.status_code==200 and fetched.json()["data"]["DOB"]=="1990-01-01"
        encounter=client.post(f"/apis/default/api/patient/{patient_data['uuid']}/encounter",headers=headers,json={"date":"2026-09-15T09:00:00Z","reason":"Compatibility visit"})
        assert encounter.status_code==201 and encounter.json()["data"]["patient_uuid"]==patient_data["uuid"]
        encounter_uuid=encounter.json()["data"]["uuid"]
        assert client.get(f"/apis/default/api/patient/{patient_data['uuid']}/encounter/{encounter_uuid}",headers=headers).status_code==200
        updated=client.put(f"/apis/default/api/patient/{patient_data['uuid']}/encounter/{encounter_uuid}",headers=headers,json={"status":"finished"})
        assert updated.status_code==200 and updated.json()["data"]["status"]=="finished"
        listing=client.get(f"/apis/default/api/patient/{patient_data['uuid']}/encounter",headers=headers)
        assert listing.status_code==200 and listing.json()["data"][0]["chief_complaint"]=="Compatibility visit"
        practitioner=client.post("/apis/default/api/practitioner",headers=headers,json={"fname":"API","lname":"Clinician","email":"api-clinician@example.com"})
        assert practitioner.status_code==201 and practitioner.json()["data"]["first_name"]=="API"
        practitioner_uuid=practitioner.json()["data"]["uuid"]
        assert client.get(f"/apis/default/api/practitioner/{practitioner_uuid}",headers=headers).status_code==200
        practitioner_update=client.put(f"/apis/default/api/practitioner/{practitioner_uuid}",headers=headers,json={"fname":"API","lname":"Clinician Updated","email":"api-clinician@example.com"})
        assert practitioner_update.status_code==200 and practitioner_update.json()["data"]["last_name"].endswith("Updated")
        appointment=client.post(f"/apis/default/api/patient/{patient_data['uuid']}/appointment",headers=headers,json={"starts_at":"2026-10-15T09:00:00Z","ends_at":"2026-10-15T09:30:00Z","reason":"API follow-up"})
        assert appointment.status_code==201,appointment.text
        appointment_uuid=appointment.json()["data"]["uuid"]
        assert client.get(f"/apis/default/api/appointment/{appointment_uuid}",headers=headers).status_code==200
        assert len(client.get(f"/apis/default/api/patient/{patient_data['uuid']}/appointment",headers=headers).json()["data"])==1
        assert client.delete(f"/apis/default/api/patient/{patient_data['uuid']}/appointment/{appointment_uuid}",headers=headers).status_code==200


def test_portal_compatibility_contract_is_patient_isolated():
    with TestClient(app) as client:
        headers=staff(client)
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"PortalCompat","last_name":"Patient","date_of_birth":"1992-01-01","sex":"unknown","email":"portal-compat@example.com","portal_allowed":True,"allow_email":True}).json()
        encounter=client.post("/api/v1/encounters",headers=headers,json={"patient_uuid":patient["uuid"],"occurred_at":"2026-09-15T10:00:00Z","chief_complaint":"Portal-visible visit"}).json()
        appointment=client.post("/api/v1/appointments",headers=headers,json={"patient_uuid":patient["uuid"],"starts_at":"2026-11-15T10:00:00Z","ends_at":"2026-11-15T10:30:00Z","reason":"Portal appointment"}).json()
        portal=create_portal(client,headers,patient,"portal-compat")
        me=client.get("/apis/default/portal/patient",headers=portal)
        assert me.status_code==200 and me.json()["data"]["uuid"]==patient["uuid"]
        appointments=client.get("/apis/default/portal/patient/appointment",headers=portal)
        assert appointments.status_code==200 and appointments.json()["data"][0]["uuid"]==appointment["uuid"]
        assert client.get(f"/apis/default/portal/patient/appointment/{appointment['uuid']}",headers=portal).status_code==200
        assert client.get(f"/apis/default/portal/patient/encounter/{encounter['uuid']}",headers=portal).status_code==200
        assert client.get("/apis/default/portal/patient/encounter",headers=portal).json()["data"][0]["uuid"]==encounter["uuid"]
        assert client.get("/apis/unknown/portal/patient",headers=portal).status_code==404


def test_compatibility_routes_reject_wrong_identity_type():
    with TestClient(app) as client:
        assert client.get("/apis/default/api/patient").status_code==403
