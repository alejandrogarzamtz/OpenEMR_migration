from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent


def test_fhir_care_plan_goal_and_care_team_search_read_and_references():
    with TestClient(app) as client:
        token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];headers={"Authorization":f"Bearer {token}"}
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"FHIR","last_name":"Coordination","date_of_birth":"1970-01-02","sex":"unknown"}).json();other=client.post("/api/v1/patients",headers=headers,json={"first_name":"FHIR","last_name":"Other","date_of_birth":"1971-02-03","sex":"unknown"}).json()
        encounter=client.post("/api/v1/encounters",headers=headers,json={"patient_uuid":patient["uuid"],"occurred_at":"2026-09-14T12:00:00Z"}).json();plans=f"/api/v1/patients/{patient['uuid']}/care-plans"
        goal=client.post(plans,headers=headers,json={"encounter_uuid":encounter["uuid"],"recorded_at":"2026-09-14T12:00:00Z","code":"SNOMED-CT:229065009","code_text":"Exercise therapy goal","description":"Walk fifteen minutes daily","plan_type":"goal","status":"active","target_date":"2026-10-14T12:00:00Z"}).json()
        outcome=client.post(f"{plans}/{goal['uuid']}/outcomes",headers=headers,json={"event_type":"outcome","recorded_at":"2026-09-15T12:00:00Z","plan_status":"completed","achievement_status":"achieved","note":"Target met"});assert outcome.status_code==201
        plan=client.post(plans,headers=headers,json={"encounter_uuid":encounter["uuid"],"recorded_at":"2026-09-14T12:00:00Z","code":"SNOMED-CT:409073007","code_text":"Education","description":"Exercise education","plan_type":"intervention","status":"active"}).json()
        facility=client.post("/api/v1/admin/facilities",headers=headers,json={"name":"FHIR Clinic"}).json();practitioner=client.post("/api/v1/admin/practitioners",headers=headers,json={"first_name":"Ada","last_name":"FHIR","primary_facility_uuid":facility["uuid"]}).json()
        team=client.post(f"/api/v1/patients/{patient['uuid']}/care-teams",headers=headers,json={"name":"Coordination team","status":"active"}).json();member_path=f"/api/v1/patients/{patient['uuid']}/care-teams/{team['uuid']}/members"
        assert client.post(member_path,headers=headers,json={"member_type":"practitioner","practitioner_uuid":practitioner["uuid"],"role":"primary-care"}).status_code==201
        assert client.post(member_path,headers=headers,json={"member_type":"facility","facility_uuid":facility["uuid"],"role":"care-site"}).status_code==201
        capability=client.get("/fhir/metadata",headers=headers).json();types={item["type"] for item in capability["rest"][0]["resource"]};assert {"CarePlan","Goal","CareTeam"} <= types
        care_bundle=client.get(f"/fhir/CarePlan?patient=Patient/{patient['uuid']}&status=active",headers=headers).json();assert care_bundle["total"]==1;care=care_bundle["entry"][0]["resource"];assert care["id"]==plan["uuid"] and care["goal"]==[{"reference":f"Goal/{goal['uuid']}"}] and care["encounter"]["reference"]==f"Encounter/{encounter['uuid']}"
        assert client.get(f"/fhir/CarePlan/{plan['uuid']}",headers=headers).json()["subject"]["reference"]==f"Patient/{patient['uuid']}"
        goal_bundle=client.get(f"/fhir/Goal?patient={patient['uuid']}&status=completed",headers=headers).json();assert goal_bundle["total"]==1;resource=goal_bundle["entry"][0]["resource"];assert resource["achievementStatus"]["coding"][0]["code"]=="achieved" and resource["target"][0]["dueDate"]=="2026-10-14"
        assert client.get(f"/fhir/Goal/{goal['uuid']}",headers=headers).json()["resourceType"]=="Goal"
        team_resource=client.get(f"/fhir/CareTeam/{team['uuid']}",headers=headers).json();references={item["member"].get("reference") for item in team_resource["participant"]};assert references=={f"Practitioner/{practitioner['uuid']}",f"Organization/{facility['uuid']}"}
        assert client.get(f"/fhir/CareTeam?patient={other['uuid']}",headers=headers).json()["total"]==0
        missing=client.get("/fhir/Goal/not-found",headers=headers);assert missing.status_code==404 and missing.json()["detail"]["resourceType"]=="OperationOutcome"
        with SessionLocal() as db:
            resources=set(db.scalars(select(AuditEvent.resource_type).where(AuditEvent.action.in_(("fhir-read","fhir-search")))));assert {"CarePlan","Goal","CareTeam"} <= resources
