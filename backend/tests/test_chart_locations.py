from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent, User
from app.security import password_hash


def login(client: TestClient, email="admin@example.com", password="change-me-now"):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":password}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def patient(client, headers, first, last):
    response=client.post("/api/v1/patients",headers=headers,json={"first_name":first,"last_name":last,"date_of_birth":"1980-01-02","sex":"unknown"})
    assert response.status_code==201
    return response.json()


def test_append_only_chart_custody_history_and_legacy_reports():
    with TestClient(app) as client:
        headers=login(client)
        first=patient(client,headers,"Ana","Archive")
        second=patient(client,headers,"Ben","Borrower")
        with SessionLocal() as db:
            custodian=User(email="custodian@example.com",username="custodian",password_hash=password_hash.hash("custodian-password"),role="viewer",permissions=["patients:demo:read"])
            db.add(custodian);db.commit();db.refresh(custodian);custodian_uuid=custodian.uuid

        movements=[
            {"destination_type":"location","location":"Records room A","occurred_at":"2027-03-01T09:00:00Z"},
            {"destination_type":"user","custodian_user_uuid":custodian_uuid,"occurred_at":"2027-03-01T10:00:00Z","note":"Review"},
            {"destination_type":"returned","occurred_at":"2027-03-01T11:00:00Z"},
        ]
        for movement in movements:
            assert client.post(f"/api/v1/patients/{first['uuid']}/chart-locations",headers=headers,json=movement).status_code==201
        checkout=client.post(f"/api/v1/patients/{second['uuid']}/chart-locations",headers=headers,json={"destination_type":"user","custodian_name":"External records reviewer","occurred_at":"2027-03-02T10:00:00Z"})
        assert checkout.status_code==201 and checkout.json()["custodian_name"]=="External records reviewer"

        history=client.get(f"/api/v1/patients/{first['uuid']}/chart-locations",headers=headers)
        assert history.status_code==200
        assert [row["destination_type"] for row in history.json()]==["returned","user","location"]
        assert history.json()[1]["custodian_user_uuid"]==custodian_uuid
        assert client.post(f"/api/v1/patients/{first['uuid']}/chart-locations",headers=headers,json={"destination_type":"user"}).status_code==422
        assert client.post(f"/api/v1/patients/{first['uuid']}/chart-locations",headers=headers,json={"destination_type":"location","location":"X","occurred_at":"2027-03-01T12:00:00"}).status_code==422

        activity=client.post("/api/v1/reports/chart_location_activity/runs",headers=headers,json={"patient_uuid":first["uuid"],"date_from":"2027-03-01","date_to":"2027-03-01"})
        assert activity.status_code==201
        assert activity.json()["totals"]=={"events":3,"checkouts":1,"locations":1,"returns":1}
        assert activity.json()["rows"][2]["destination"]=="Returned to records"
        assert client.post("/api/v1/reports/chart_location_activity/runs",headers=headers,json={}).status_code==422

        checked_out=client.post("/api/v1/reports/charts_checked_out/runs",headers=headers,json={})
        assert checked_out.status_code==201 and checked_out.json()["row_count"]==1
        assert checked_out.json()["rows"][0]["patient_uuid"]==second["uuid"]
        assert checked_out.json()["rows"][0]["custodian"]=="External records reviewer"
        with SessionLocal() as db:
            assert db.query(AuditEvent).filter(AuditEvent.resource_type=="chart_location").count()>=5


def test_chart_custody_acl_is_read_write_specific():
    with TestClient(app) as client:
        admin=login(client); item=patient(client,admin,"Read","Only")
        with SessionLocal() as db:
            db.add(User(email="chart-reader@example.com",password_hash=password_hash.hash("reader-password"),role="viewer",permissions=["patients:demo:read"]));db.commit()
        reader=login(client,"chart-reader@example.com","reader-password")
        assert client.get(f"/api/v1/patients/{item['uuid']}/chart-locations",headers=reader).status_code==200
        assert client.post(f"/api/v1/patients/{item['uuid']}/chart-locations",headers=reader,json={"destination_type":"returned"}).status_code==403
        assert client.post("/api/v1/reports/charts_checked_out/runs",headers=reader,json={}).status_code==201
