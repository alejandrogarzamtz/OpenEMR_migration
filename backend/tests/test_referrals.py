from fastapi.testclient import TestClient
from app.main import app


def test_referral_loop_and_report():
    with TestClient(app) as client:
        token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];headers={"Authorization":f"Bearer {token}"}
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"Referral","last_name":"Patient","date_of_birth":"1975-04-03","sex":"unknown"}).json()
        created=client.post(f"/api/v1/patients/{patient['uuid']}/referrals",headers=headers,json={"recipient_name":"Ada Specialist","recipient_organization":"Specialty Group","referred_at":"2027-04-05T10:00:00Z","reason":"Evaluate persistent symptoms"})
        assert created.status_code==201 and created.json()["status"]=="requested"
        uuid=created.json()["uuid"]
        assert client.post(f"/api/v1/patients/{patient['uuid']}/referrals/{uuid}/reply",headers=headers,json={"replied_at":"2027-04-04T10:00:00Z","reply":"Early"}).status_code==422
        reply=client.post(f"/api/v1/patients/{patient['uuid']}/referrals/{uuid}/reply",headers=headers,json={"replied_at":"2027-04-08T10:00:00Z","reply":"Consultation completed"})
        assert reply.status_code==200 and reply.json()["status"]=="completed"
        assert client.post(f"/api/v1/patients/{patient['uuid']}/referrals/{uuid}/reply",headers=headers,json={"replied_at":"2027-04-09T10:00:00Z","reply":"Again"}).status_code==409
        history=client.get(f"/api/v1/patients/{patient['uuid']}/referrals",headers=headers)
        assert history.status_code==200 and history.json()[0]["reply"]=="Consultation completed"
        report=client.post("/api/v1/reports/referrals_report/runs",headers=headers,json={"date_from":"2027-04-01","date_to":"2027-04-30","status":"completed"})
        assert report.status_code==201 and report.json()["row_count"]==1
        assert report.json()["rows"][0]["refer_to"]=="Specialty Group"
        assert report.json()["totals"]=={"referrals":1,"completed":1,"pending":0}
