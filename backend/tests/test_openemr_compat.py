from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import InsuranceType, ReferenceOption
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


def test_standard_api_clinical_resources_and_encounter_notes():
    with TestClient(app) as client:
        headers=staff(client)
        patient=client.post("/apis/default/api/patient",headers=headers,json={"fname":"Clinical","lname":"Compatibility","DOB":"1985-05-05","sex":"unknown"}).json()["data"]
        encounter=client.post(f"/apis/default/api/patient/{patient['uuid']}/encounter",headers=headers,json={"date":"2026-09-15T12:00:00Z","reason":"Clinical compatibility"}).json()["data"]
        base=f"/apis/default/api/patient/{patient['uuid']}/encounter/{encounter['uuid']}"

        soap=client.post(f"{base}/soap_note",headers=headers,json={"subjective":"Headache","objective":"Alert","assessment":"Tension headache","plan":"Hydration"})
        assert soap.status_code==200,soap.text
        soap_uuid=soap.json()["data"]["uuid"]
        assert client.get(f"{base}/soap_note",headers=headers).json()["data"][0]["assessment"]=="Tension headache"
        assert client.get(f"{base}/soap_note/{soap_uuid}",headers=headers).status_code==200
        soap_update=client.put(f"{base}/soap_note/{soap_uuid}",headers=headers,json={"subjective":"Improving","plan":"Continue hydration"})
        assert soap_update.status_code==200 and soap_update.json()["data"]["subjective"]=="Improving"

        vital=client.post(f"{base}/vital",headers=headers,json={"date":"2026-09-15T12:05:00Z","bps":120,"bpd":80,"weight":80,"height":200})
        assert vital.status_code==200,vital.text
        vital_uuid=vital.json()["data"]["uuid"]
        assert vital.json()["data"]["bmi"]==20.0
        assert client.get(f"{base}/vital",headers=headers).json()["data"][0]["bps"]==120.0
        assert client.get(f"{base}/vital/{vital_uuid}",headers=headers).status_code==200
        vital_update=client.put(f"{base}/vital/{vital_uuid}",headers=headers,json={"pulse":72})
        assert vital_update.status_code==200 and vital_update.json()["data"]["pulse"]==72.0

        created={}
        for resource,title in {"medical_problem":"Migraine","allergy":"Penicillin","medication":"Ibuprofen","surgery":"Appendectomy","dental_issue":"Caries"}.items():
            route=f"/apis/default/api/patient/{patient['uuid']}/{resource}"
            result=client.post(route,headers=headers,json={"title":title,"onset_date":"2026-01-01","note":"Imported-compatible record"})
            assert result.status_code==200,(resource,result.text)
            created[resource]=result.json()["data"]["uuid"]
            assert client.get(route,headers=headers).json()["data"][0]["title"]==title
            assert client.get(f"{route}/{created[resource]}",headers=headers).status_code==200
            updated=client.put(f"{route}/{created[resource]}",headers=headers,json={"status":"inactive"})
            assert updated.status_code==200 and updated.json()["data"]["status"]=="inactive"

        for resource in ("medical_problem","allergy"):
            assert any(item["patient_uuid"]==patient["uuid"] for item in client.get(f"/apis/default/api/{resource}",headers=headers).json()["data"])
            assert client.get(f"/apis/default/api/{resource}/{created[resource]}",headers=headers).status_code==200
        for resource,item_uuid in created.items():
            assert client.delete(f"/apis/default/api/patient/{patient['uuid']}/{resource}/{item_uuid}",headers=headers).status_code==200
            assert client.get(f"/apis/default/api/patient/{patient['uuid']}/{resource}/{item_uuid}",headers=headers).status_code==404


def test_standard_api_administration_and_reference_catalogs():
    with TestClient(app) as client:
        headers=staff(client)
        with SessionLocal() as db:
            db.add_all([ReferenceOption(list_id="language",option_id="en",title="English",sequence=1,active=True,legacy_payload={"notes":"English language"}),InsuranceType(legacy_type_id=2,name="Medicare Part B",claim_type="MB")]);db.commit()
        options=client.get("/apis/default/api/list/language",headers=headers)
        assert options.status_code==200 and options.json()["data"][0]["option_id"]=="en"
        users=client.get("/apis/default/api/user",headers=headers)
        assert users.status_code==200 and "password_hash" not in users.text
        user_uuid=users.json()["data"][0]["uuid"]
        assert client.get(f"/apis/default/api/user/{user_uuid}",headers=headers).status_code==200
        types=client.get("/apis/default/api/insurance_type",headers=headers)
        assert types.status_code==200 and types.json()["data"][0]["claim_type"]=="MB"
        payer=client.post("/apis/default/api/insurance_company",headers=headers,json={"name":"Compatibility Health","cms_id":"CMS42","city":"Monterrey"})
        assert payer.status_code==201,payer.text
        payer_uuid=payer.json()["data"]["uuid"]
        assert any(item["name"]=="Compatibility Health" for item in client.get("/apis/default/api/insurance_company",headers=headers).json()["data"])
        assert client.get(f"/apis/default/api/insurance_company/{payer_uuid}",headers=headers).json()["data"]["city"]=="Monterrey"
        updated=client.put(f"/apis/default/api/insurance_company/{payer_uuid}",headers=headers,json={"name":"Compatibility Health North"})
        assert updated.status_code==200 and updated.json()["data"]["name"].endswith("North")
