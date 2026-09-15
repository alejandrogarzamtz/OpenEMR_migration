from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db import SessionLocal
from app.main import app
from app.models import RegulatoryMetricEvent, User
from app.security import password_hash


def auth(client,email):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":"report-password"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_rwt_2026_counts_all_six_metrics_and_api_dimensions():
    with TestClient(app) as client:
        with SessionLocal() as db:db.add(User(email="rwt-report@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["admin:super:read"]));db.commit()
        headers=auth(client,"rwt-report@example.com")
        with SessionLocal() as db:
            db.execute(delete(RegulatoryMetricEvent));when=datetime(2026,6,15,12,tzinfo=timezone.utc)
            fixtures=[
                ("ccda-generated",True,None,None),("direct-sent",True,None,None),("direct-received",True,None,None),("qrda-import",True,None,None),("qrda3-export",True,None,None),("ehi-export",True,None,None),
                ("api-request",True,"user","Patient"),("api-request",True,"patient","Patient"),("api-request",False,"user","Observation"),
            ]
            for index,(kind,success,actor,resource) in enumerate(fixtures):db.add(RegulatoryMetricEvent(source_key=f"test:rwt:{index}",metric_type=kind,occurred_at=when,success=success,actor_kind=actor,resource=resource,legacy_payload={"fixture":index}))
            db.add(RegulatoryMetricEvent(source_key="test:rwt:outside",metric_type="ccda-generated",occurred_at=datetime(2026,10,1,tzinfo=timezone.utc),success=True))
            db.commit()
        response=client.post("/api/v1/reports/rwt_2026_report/runs",headers=headers,json={"date_from":"2020-01-01","date_to":"2030-01-01"})
        assert response.status_code==201,response.text
        payload=response.json();assert payload["totals"]=={"measurement_period_start":"2026-04-01","measurement_period_end":"2026-09-30","evidence_events":9,"metrics":6}
        values={(row["measure"],row["resource"]):row["count"] for row in payload["rows"]}
        assert values[("generated_ccda_documents",None)]==1 and values[("sent_direct_messages",None)]==1 and values[("received_direct_messages",None)]==1
        assert values[("qrda_imports",None)]==1 and values[("generated_cqm_qrda3_reports",None)]==1 and values[("ehi_exports",None)]==1
        assert values[("successful_api_requests",None)]==2 and values[("unsuccessful_api_requests",None)]==1
        assert values[("api_requests_by_users",None)]==1 and values[("api_requests_by_patients",None)]==1 and values[("api_requests_for_resource","Patient")]==2
        export=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers);assert export.status_code==200 and export.text.splitlines()[0]=="metric,measure,resource,count"


def test_rwt_2026_requires_super_admin_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:db.add(User(email="rwt-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["acct:rep_a:read"]));db.commit()
        assert client.post("/api/v1/reports/rwt_2026_report/runs",headers=auth(client,"rwt-denied@example.com"),json={}).status_code==403
