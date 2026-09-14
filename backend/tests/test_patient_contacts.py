from fastapi.testclient import TestClient
from app.main import app
from test_communications import create_patient, create_portal, staff_headers


def test_patient_contacts_are_isolated_prioritized_and_inactivated_without_deletion():
    with TestClient(app) as client:
        staff=staff_headers(client); patient=create_patient(client,staff,"ContactOne"); other=create_patient(client,staff,"ContactTwo")
        first=client.post(f"/api/v1/patients/{patient['uuid']}/addresses",headers=staff,json={"line1":"One Main","is_primary":True}).json()
        second=client.post(f"/api/v1/patients/{patient['uuid']}/addresses",headers=staff,json={"line1":"Two Main","is_primary":True}).json()
        rows=client.get(f"/api/v1/patients/{patient['uuid']}/addresses",headers=staff).json()
        assert sum(row["is_primary"] for row in rows)==1 and next(row for row in rows if row["uuid"]==second["uuid"])["is_primary"]
        assert client.get(f"/api/v1/patients/{patient['uuid']}",headers=staff).json()["address_line_1"]=="Two Main"
        assert client.post(f"/api/v1/patients/{other['uuid']}/addresses/{first['uuid']}/inactivate",headers=staff,json={"reason":"Moved"}).status_code==404
        inactive=client.post(f"/api/v1/patients/{patient['uuid']}/addresses/{second['uuid']}/inactivate",headers=staff,json={"reason":"Moved"})
        assert inactive.status_code==200 and not inactive.json()["active"] and inactive.json()["inactivated_reason"]=="Moved"
        assert client.get(f"/api/v1/patients/{patient['uuid']}",headers=staff).json()["address_line_1"]=="One Main"
        telecom=client.post(f"/api/v1/patients/{patient['uuid']}/telecoms",headers=staff,json={"system":"sms","use":"mobile","value":"5550100","is_primary":True}).json()
        assert client.get(f"/api/v1/patients/{patient['uuid']}",headers=staff).json()["phone"]=="5550100"
        assert client.post(f"/api/v1/patients/{patient['uuid']}/telecoms/{telecom['uuid']}/inactivate",headers=staff,json={"reason":"Disconnected"}).json()["active"] is False
        assert client.get(f"/api/v1/patients/{patient['uuid']}",headers=staff).json()["phone"] is None
        person=client.post(f"/api/v1/patients/{patient['uuid']}/related-people",headers=staff,json={"first_name":"Grace","last_name":"Guardian","relationship_code":"MTH","role_code":"GUARD","is_emergency_contact":True,"can_make_medical_decisions":True}).json()
        ended=client.post(f"/api/v1/patients/{patient['uuid']}/related-people/{person['uuid']}/inactivate",headers=staff,json={"reason":"Authority ended"}).json()
        assert not ended["active"] and not ended["can_make_medical_decisions"] and not ended["is_emergency_contact"]


def test_previous_names_are_structured_audited_and_searchable():
    with TestClient(app) as client:
        staff=staff_headers(client); patient=create_patient(client,staff,"CurrentName")
        created=client.post(f"/api/v1/patients/{patient['uuid']}/name-history",headers=staff,json={"first_name":"Former","last_name":"Surname","use":"official","period_end":"2020-01-01","reason":"Legal name change"})
        assert created.status_code==201 and created.json()["last_name"]=="Surname"
        history=client.get(f"/api/v1/patients/{patient['uuid']}/name-history",headers=staff).json()
        assert [item["uuid"] for item in history]==[created.json()["uuid"]]
        results=client.get("/api/v1/patients",headers=staff,params={"q":"Surname"}).json()["items"]
        assert [item["uuid"] for item in results]==[patient["uuid"]]


def test_employment_history_is_patient_scoped_validated_and_preserved_on_inactivation():
    with TestClient(app) as client:
        staff=staff_headers(client); patient=create_patient(client,staff,"WorkerOne"); other=create_patient(client,staff,"WorkerTwo")
        created=client.post(f"/api/v1/patients/{patient['uuid']}/employments",headers=staff,json={"employer_name":"Community Clinic","occupation_code":"RN","industry_code":"6211","country":"Mexico","starts_at":"2021-01-01T00:00:00Z"})
        assert created.status_code==201 and created.json()["active"] is True
        invalid=client.post(f"/api/v1/patients/{patient['uuid']}/employments",headers=staff,json={"employer_name":"Invalid","starts_at":"2025-01-01T00:00:00Z","ends_at":"2024-01-01T00:00:00Z"})
        assert invalid.status_code==422
        assert client.post(f"/api/v1/patients/{other['uuid']}/employments/{created.json()['uuid']}/inactivate",headers=staff,json={"reason":"Employment ended"}).status_code==404
        ended=client.post(f"/api/v1/patients/{patient['uuid']}/employments/{created.json()['uuid']}/inactivate",headers=staff,json={"reason":"Employment ended"})
        assert ended.status_code==200 and ended.json()["active"] is False and ended.json()["ends_at"]
        history=client.get(f"/api/v1/patients/{patient['uuid']}/employments",headers=staff).json()
        assert len(history)==1 and history[0]["inactivated_reason"]=="Employment ended"


def test_consents_are_versioned_scoped_validated_and_synchronize_operational_flags():
    with TestClient(app) as client:
        staff=staff_headers(client); patient=create_patient(client,staff,"ConsentOne"); other=create_patient(client,staff,"ConsentTwo")
        granted=client.post(f"/api/v1/patients/{patient['uuid']}/consents",headers=staff,json={"purpose":"email","decision":"permit","evidence_reference":"signed-form-1"})
        assert granted.status_code==201 and granted.json()["status"]=="active"
        denied=client.post(f"/api/v1/patients/{patient['uuid']}/consents",headers=staff,json={"purpose":"email","decision":"deny"})
        assert denied.status_code==201
        history=client.get(f"/api/v1/patients/{patient['uuid']}/consents",headers=staff).json()
        assert len(history)==2 and sum(item["status"]=="active" for item in history)==1
        assert next(item for item in history if item["uuid"]==granted.json()["uuid"])["revocation_reason"].startswith("Superseded")
        assert client.get(f"/api/v1/patients/{patient['uuid']}",headers=staff).json()["allow_email"] is False
        assert client.post(f"/api/v1/patients/{other['uuid']}/consents/{denied.json()['uuid']}/revoke",headers=staff,json={"reason":"Wrong patient"}).status_code==404
        revoked=client.post(f"/api/v1/patients/{patient['uuid']}/consents/{denied.json()['uuid']}/revoke",headers=staff,json={"reason":"Patient withdrew decision"})
        assert revoked.status_code==200 and revoked.json()["status"]=="revoked"
        assert client.post(f"/api/v1/patients/{patient['uuid']}/consents/{denied.json()['uuid']}/revoke",headers=staff,json={"reason":"Again"}).status_code==409
        assert client.post(f"/api/v1/patients/{patient['uuid']}/consents",headers=staff,json={"purpose":"privacy-notice","decision":"permit"}).status_code==422
        assert client.post(f"/api/v1/patients/{patient['uuid']}/consents",headers=staff,json={"purpose":"message-delegate","decision":"permit"}).status_code==422
        assert client.post(f"/api/v1/patients/{patient['uuid']}/consents",headers=staff,json={"purpose":"sms","decision":"permit"}).status_code==409
        portal_headers=create_portal(client,staff,patient,"consent-one-portal")
        portal_denied=client.post(f"/api/v1/patients/{patient['uuid']}/consents",headers=staff,json={"purpose":"patient-portal","decision":"deny"})
        assert portal_denied.status_code==201
        assert client.get("/api/v1/portal/me",headers=portal_headers).status_code==401
        assert client.post("/api/v1/portal/auth/token",json={"username":"consent-one-portal","password":"permanent-password-456"}).status_code==401
