from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent


def test_longitudinal_care_plan_lifecycle_is_scoped_validated_audited_and_locked():
    with TestClient(app) as client:
        token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];headers={"Authorization":f"Bearer {token}"}
        first=client.post("/api/v1/patients",headers=headers,json={"first_name":"Care","last_name":"Planone","date_of_birth":"1975-04-12","sex":"unknown"}).json()
        second=client.post("/api/v1/patients",headers=headers,json={"first_name":"Care","last_name":"Plantwo","date_of_birth":"1976-05-13","sex":"unknown"}).json()
        encounter=client.post("/api/v1/encounters",headers=headers,json={"patient_uuid":first["uuid"],"occurred_at":"2026-09-14T12:00:00Z"}).json()
        path=f"/api/v1/patients/{first['uuid']}/care-plans"
        missing_timezone=client.post(path,headers=headers,json={"encounter_uuid":encounter["uuid"],"recorded_at":"2026-09-14T12:00:00","description":"Improve mobility"})
        assert missing_timezone.status_code==422
        invalid=client.post(path,headers=headers,json={"encounter_uuid":encounter["uuid"],"recorded_at":"2026-09-14T12:00:00Z","description":"Improve mobility","reason_description":"Patient declined"})
        assert invalid.status_code==422
        created=client.post(path,headers=headers,json={"encounter_uuid":encounter["uuid"],"recorded_at":"2026-09-14T12:00:00Z","code":"SNOMED-CT:711282006","code_text":"Mobility care plan","description":"Walk for ten minutes daily","plan_type":"therapeutic","status":"active","target_date":"2026-10-14T12:00:00Z","engagement_category":"shared-decision","reason_code":"PATIENT-PREFERENCE","reason_description":"Patient selected walking","reason_status":"active","reason_recorded_at":"2026-09-14T12:00:00Z"})
        assert created.status_code==201 and created.json()["active"] is True and created.json()["status"]=="active"
        plan=created.json();assert client.get(path,headers=headers).json()[0]["uuid"]==plan["uuid"]
        assert client.get(f"/api/v1/patients/{second['uuid']}/care-plans",headers=headers).json()==[]
        assert client.put(f"/api/v1/patients/{second['uuid']}/care-plans/{plan['uuid']}",headers=headers,json={key:value for key,value in plan.items() if key not in {"uuid","encounter_uuid","active","created_at","updated_at"}}).status_code==404
        update={key:value for key,value in plan.items() if key not in {"uuid","encounter_uuid","active","created_at","updated_at"}};update["description"]="Walk for fifteen minutes daily";update["status"]="on-hold"
        changed=client.put(f"{path}/{plan['uuid']}",headers=headers,json=update)
        assert changed.status_code==200 and changed.json()["description"].startswith("Walk for fifteen")
        signature=client.post(f"/api/v1/patients/{first['uuid']}/encounters/{encounter['uuid']}/sign",headers=headers,json={"password":"change-me-now","lock":True,"attestation":"I attest that this encounter is accurate and complete."})
        assert signature.status_code==201
        assert client.delete(f"{path}/{plan['uuid']}?reason=entered%20in%20error",headers=headers).status_code==423
        with SessionLocal() as db:
            events=list(db.scalars(select(AuditEvent).where(AuditEvent.resource_type=="care_plan",AuditEvent.resource_id==plan["uuid"])))
            assert {event.action for event in events} >= {"create","update"}
