from fastapi.testclient import TestClient
from app.main import app
from test_communications import create_patient, staff_headers


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
