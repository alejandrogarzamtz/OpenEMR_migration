from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent, PreferenceValueSet


def test_patient_preference_value_semantics_history_and_isolation():
    with TestClient(app) as client:
        token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];headers={"Authorization":f"Bearer {token}"}
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"Preference","last_name":"Patient","date_of_birth":"1970-01-02","sex":"unknown"}).json()
        other=client.post("/api/v1/patients",headers=headers,json={"first_name":"Other","last_name":"Preference","date_of_birth":"1971-02-03","sex":"unknown"}).json()
        with SessionLocal() as db:
            db.add(PreferenceValueSet(observation_code="81329-5",answer_code="LA33487-5",answer_system="http://loinc.org",answer_display="Attempt resuscitation",sort_order=1));db.commit()
        base=f"/api/v1/patients/{patient['uuid']}/preferences";now="2026-09-14T12:00:00Z"
        coded={"category":"treatment-intervention","observation_code":"81329-5","observation_code_text":"Cardiopulmonary resuscitation preference","value_type":"coded","value_code":"LA33487-5","value_code_system":"http://loinc.org","value_display":"Attempt resuscitation","effective_at":now,"status":"final"}
        created=client.post(base,headers=headers,json=coded);assert created.status_code==201;preference=created.json()
        invalid={**coded,"value_text":"also text"};assert client.post(base,headers=headers,json=invalid).status_code==422
        assert client.post(base,headers=headers,json={**coded,"value_type":"text","value_code":None,"value_code_system":None,"value_display":None,"value_text":None}).status_code==422
        boolean={"category":"care-experience","observation_code":"81364-2","value_type":"boolean","value_boolean":False,"effective_at":now,"status":"preliminary"}
        assert client.post(base,headers=headers,json=boolean).status_code==201
        text={"category":"care-experience","observation_code":"81338-6","value_type":"text","value_text":"Keep family at bedside","effective_at":now,"status":"final"}
        assert client.post(base,headers=headers,json=text).status_code==201
        amendment={**coded,"value_code":"LA33488-3","value_display":"Do not attempt resuscitation","status":"final","amendment_reason":"Patient changed decision"}
        changed=client.post(f"{base}/{preference['uuid']}/amend",headers=headers,json=amendment);assert changed.status_code==201 and changed.json()["supersedes_uuid"]==preference["uuid"]
        assert client.post(f"{base}/{preference['uuid']}/amend",headers=headers,json=amendment).status_code==409
        assert client.post(f"/api/v1/patients/{other['uuid']}/preferences/{changed.json()['uuid']}/amend",headers=headers,json=amendment).status_code==404
        current=client.get(base,headers=headers).json();assert len(current)==3 and all(item["active"] for item in current)
        history=client.get(f"{base}?include_history=true",headers=headers).json();assert len(history)==4 and next(item for item in history if item["uuid"]==preference["uuid"])["status"]=="amended"
        assert client.delete(f"{base}/{changed.json()['uuid']}",headers=headers).status_code==422
        assert client.delete(f"{base}/{changed.json()['uuid']}?reason=decision%20withdrawn",headers=headers).status_code==204
        catalog=client.get(f"/api/v1/patients/{patient['uuid']}/preference-catalog",headers=headers).json();assert any(item["code"]=="81329-5" for item in catalog["observations"]["treatment-intervention"]);assert catalog["answers"]["81329-5"][0]["answer_code"]=="LA33487-5"
        with SessionLocal() as db:
            actions=set(db.scalars(select(AuditEvent.action).where(AuditEvent.resource_type=="patient_preference")));assert actions >= {"create","amend","inactivate","search"}
