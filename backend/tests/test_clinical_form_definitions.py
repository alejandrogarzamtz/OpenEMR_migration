from fastapi.testclient import TestClient

from app.main import app
from app.services.clinical_forms import PHYSICAL_EXAM_LINES, ROS_FIELDS


def test_specialized_form_definitions_and_semantic_validation():
    with TestClient(app) as client:
        assert client.get("/api/v1/clinical-form-definitions").status_code == 403
        token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"]
        headers={"Authorization":f"Bearer {token}"}
        definitions=client.get("/api/v1/clinical-form-definitions",headers=headers)
        assert definitions.status_code==200
        assert len(definitions.json()["ros"]["fields"])==len(ROS_FIELDS)==138
        assert len(definitions.json()["physical_exam"]["lines"])==len(PHYSICAL_EXAM_LINES)==37
        created=client.post("/api/v1/patients",headers=headers,json={"first_name":"Semantic","last_name":"Formcheck","date_of_birth":"1977-03-19","sex":"unknown"})
        assert created.status_code==201, created.text
        patient=created.json()
        encounter=client.post("/api/v1/encounters",headers=headers,json={"patient_uuid":patient["uuid"],"occurred_at":"2026-09-14T12:00:00Z"}).json()
        path=f"/api/v1/patients/{patient['uuid']}/clinical-forms"
        base={"encounter_uuid":encounter["uuid"],"title":"Specialized form"}
        assert client.post(path,headers=headers,json=base|{"form_type":"soap","content":{}}).status_code==422
        soap=client.post(path,headers=headers,json=base|{"form_type":"soap","content":{"assessment":" Migraine "}})
        assert soap.status_code==201 and soap.json()["content"]=={"assessment":"Migraine"}
        assert client.post(path,headers=headers,json=base|{"form_type":"ros","content":{"fever":"maybe"}}).status_code==422
        ros=client.post(path,headers=headers,json=base|{"form_type":"ros","content":{"fever":"positive","chills":"negative"}})
        assert ros.status_code==201 and ros.json()["content"]=={"fever":"positive","chills":"negative"}
        assert client.post(path,headers=headers,json=base|{"form_type":"physical_exam","content":{"findings":[{"line_id":"INVALID","status":"normal"}]}}).status_code==422
        physical=client.post(path,headers=headers,json=base|{"form_type":"physical_exam","content":{"findings":[{"line_id":"GENWELL","status":"normal","comments":"Well appearing"}]}})
        assert physical.status_code==201 and physical.json()["content"]["findings"][0]=={"line_id":"GENWELL","status":"normal","diagnosis":"","comments":"Well appearing"}
        update=client.put(f"{path}/{physical.json()['uuid']}",headers=headers,json={"title":"Invalid update","content":{"findings":[]}})
        assert update.status_code==422
        assert client.post(path,headers=headers,json=base|{"form_type":"dictation","content":{"additional_notes":"No dictated content"}}).status_code==422
        dictation=client.post(path,headers=headers,json=base|{"form_type":"dictation","content":{"dictation":"Patient reports improvement","additional_notes":"Reviewed"}})
        assert dictation.status_code==201 and dictation.json()["content"]["dictation"]=="Patient reports improvement"
        assert client.post(path,headers=headers,json=base|{"form_type":"clinic_note","content":{"history":"Stable","followup_required":True}}).status_code==422
        clinic=client.post(path,headers=headers,json=base|{"form_type":"clinic_note","content":{"history":"Stable","followup_required":True,"followup_timing":"Two weeks"}})
        assert clinic.status_code==201 and clinic.json()["content"]["followup_required"] is True
        assert client.post(path,headers=headers,json=base|{"form_type":"aftercare_plan","content":{"admit_date":"09/14/2026","goal_c_relapse_potential":"Reduce relapse risk"}}).status_code==422
        transfer=client.post(path,headers=headers,json=base|{"form_type":"transfer_summary","content":{"transfer_to":"Community clinic","transfer_date":"2026-09-15","diagnosis":"Stable"}})
        assert transfer.status_code==201 and transfer.json()["content"]["transfer_date"]=="2026-09-15"
