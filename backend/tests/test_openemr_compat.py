from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import BackgroundService, ExternalProcedure, Immunization, InsuranceType, InventoryProduct, Patient, PatientEmployment, ReferenceOption
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


def test_standard_api_patient_documents_employer_and_insurance():
    with TestClient(app) as client:
        headers=staff(client)
        patient=client.post("/apis/default/api/patient",headers=headers,json={"fname":"Coverage","lname":"Compatibility","DOB":"1978-07-08","sex":"unknown"}).json()["data"]
        with SessionLocal() as db:
            stored=db.query(Patient).filter(Patient.uuid==patient["uuid"]).one();db.add(PatientEmployment(patient_id=stored.id,employer_name="OpenRM Community",active=True));db.commit()
        employer=client.get(f"/apis/default/api/patient/{patient['uuid']}/employer",headers=headers)
        assert employer.status_code==200 and employer.json()["data"][0]["employer_name"]=="OpenRM Community"
        uploaded=client.post(f"/apis/default/api/patient/{patient['uuid']}/document",headers=headers,files={"document":("note.txt",b"clinical document","text/plain")})
        assert uploaded.status_code==201,uploaded.text
        document_uuid=uploaded.json()["data"]["uuid"]
        assert client.get(f"/apis/default/api/patient/{patient['uuid']}/document",headers=headers).json()["data"][0]["uuid"]==document_uuid
        downloaded=client.get(f"/apis/default/api/patient/{patient['uuid']}/document/{document_uuid}",headers=headers)
        assert downloaded.status_code==200 and downloaded.content==b"clinical document"
        first=client.post(f"/apis/default/api/patient/{patient['uuid']}/insurance",headers=headers,json={"payer_name":"Primary Health","type":"primary","policy_number":"P-1","subscriber_name":"Coverage Compatibility"})
        second=client.post(f"/apis/default/api/patient/{patient['uuid']}/insurance",headers=headers,json={"payer_name":"Secondary Health","type":"secondary","policy_number":"S-1","subscriber_name":"Coverage Compatibility"})
        assert first.status_code==201 and second.status_code==201
        second_uuid=second.json()["data"]["uuid"]
        assert client.get(f"/apis/default/api/patient/{patient['uuid']}/insurance/{second_uuid}",headers=headers).status_code==200
        updated=client.put(f"/apis/default/api/patient/{patient['uuid']}/insurance/{second_uuid}",headers=headers,json={"plan_name":"Modern Plan"})
        assert updated.status_code==200 and updated.json()["data"]["plan_name"]=="Modern Plan"
        swapped=client.get(f"/apis/default/api/patient/{patient['uuid']}/insurance/$swap-insurance",headers=headers,params={"type":"primary","uuid":second_uuid})
        assert swapped.status_code==200 and swapped.json()["data"]["priority"]=="primary"
        assert len(client.get(f"/apis/default/api/patient/{patient['uuid']}/insurance",headers=headers).json()["data"])==2


def test_standard_api_patient_messages_and_transactions():
    with TestClient(app) as client:
        headers=staff(client);patient=client.post("/apis/default/api/patient",headers=headers,json={"fname":"Message","lname":"Compatibility","DOB":"1988-08-08","sex":"unknown"}).json()["data"];base=f"/apis/default/api/patient/{patient['uuid']}"
        message=client.post(f"{base}/message",headers=headers,json={"subject":"Follow-up","body":"Please call the patient"})
        assert message.status_code==201,message.text
        message_uuid=message.json()["data"]["uuid"]
        updated=client.put(f"{base}/message/{message_uuid}",headers=headers,json={"body":"Patient contacted"})
        assert updated.status_code==200 and updated.json()["data"]["body"]=="Patient contacted"
        assert client.delete(f"{base}/message/{message_uuid}",headers=headers).status_code==200
        assert client.put(f"{base}/message/{message_uuid}",headers=headers,json={"body":"invalid"}).status_code==404
        transaction=client.post(f"{base}/transaction",headers=headers,json={"title":"Referral transaction","date":"2026-09-15T13:00:00Z","body":"Referral sent"})
        assert transaction.status_code==201,transaction.text
        transaction_uuid=transaction.json()["data"]["uuid"]
        assert client.get(f"{base}/transaction",headers=headers).json()["data"][0]["uuid"]==transaction_uuid
        changed=client.put(f"/apis/default/api/transaction/{transaction_uuid}",headers=headers,json={"status":"completed"})
        assert changed.status_code==200 and changed.json()["data"]["status"]=="completed"


def test_standard_api_global_clinical_catalogs_and_background_services():
    with TestClient(app) as client:
        headers=staff(client);patient=client.post("/apis/default/api/patient",headers=headers,json={"fname":"Global","lname":"Compatibility","DOB":"1980-01-01","sex":"unknown"}).json()["data"]
        with SessionLocal() as db:
            stored=db.query(Patient).filter(Patient.uuid==patient["uuid"]).one();immunization=Immunization(patient_id=stored.id,administered_at=datetime(2026,9,15,10,tzinfo=timezone.utc),cvx_code="207",vaccine_name="COVID-19");procedure=ExternalProcedure(patient_id=stored.id,occurred_on=date(2026,9,14),code_system="CPT",code="99213",code_text="Office visit");drug=InventoryProduct(name="Compatibility Drug",active=True);service=BackgroundService(name="compat",title="Compatibility service",active=True,running_state=-1,next_run=datetime(2020,1,1,tzinfo=timezone.utc),execute_interval_minutes=60,handler="compat_handler");db.add_all([immunization,procedure,drug,service]);db.commit();ids={"immunization":immunization.uuid,"procedure":procedure.uuid,"drug":drug.uuid}
        for resource,item_uuid in ids.items():
            assert client.get(f"/apis/default/api/{resource}",headers=headers).status_code==200
            assert client.get(f"/apis/default/api/{resource}/{item_uuid}",headers=headers).status_code==200
        prescription=client.post("/apis/default/api/prescription",headers=headers,json={"patient_uuid":patient["uuid"],"drug_name":"Compatibility Drug","dosage_instructions":"Once daily"})
        assert prescription.status_code==201,prescription.text
        prescription_uuid=prescription.json()["data"]["uuid"]
        assert client.get("/apis/default/api/prescription",headers=headers).status_code==200
        assert client.get(f"/apis/default/api/prescription/{prescription_uuid}",headers=headers).status_code==200
        assert client.delete(f"/apis/default/api/prescription/{prescription_uuid}",headers=headers).status_code==200
        assert client.get("/apis/default/api/background_service",headers=headers).status_code==200
        assert client.get("/apis/default/api/background_service/compat",headers=headers).status_code==200
        assert client.post("/apis/default/api/background_service/compat/run",headers=headers).status_code==200
        assert client.post("/apis/default/api/background_service/$run",headers=headers).status_code==200
