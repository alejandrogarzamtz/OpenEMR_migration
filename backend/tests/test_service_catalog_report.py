from fastapi.testclient import TestClient
from app.db import SessionLocal
from app.main import app
from app.models import ServiceCode


def test_services_by_category_preserves_multilevel_prices_and_filters():
    with TestClient(app) as client:
        token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];headers={"Authorization":f"Bearer {token}"}
        with SessionLocal() as db:
            db.add_all([
                ServiceCode(code_type_id=1,code="99213",modifier="25",units=1,description="Office visit",category_code="office",category_title="Office",related_codes="ICD10:Z00.00",prices=[{"level":"standard","title":"Standard","amount":"125.00"},{"level":"discount","title":"Discount","amount":"90.00"}]),
                ServiceCode(code_type_id=2,code="LAB1",modifier="",units=1,description="Lab",category_code=None,category_title=None,prices=[{"level":"standard","title":"Standard","amount":"20.00"}]),
                ServiceCode(code_type_id=1,code="OLD",modifier="",units=1,description="Inactive",category_code="office",category_title="Office",prices=[],active=False),
            ]);db.commit()
        base=client.post("/api/v1/reports/services_by_category/runs",headers=headers,json={})
        assert base.status_code==201 and base.json()["row_count"]==1
        assert base.json()["rows"][0]["prices"][1]["amount"]=="90.00"
        assert base.json()["totals"]=={"services":1,"categories":1,"price_entries":2}
        all_rows=client.post("/api/v1/reports/services_by_category/runs",headers=headers,json={"include_uncategorized":True,"code_type_id":2})
        assert all_rows.status_code==201 and all_rows.json()["rows"][0]["category"]=="Uncategorized"
        exported=client.get(f"/api/v1/report-runs/{base.json()['uuid']}/export.csv",headers=headers)
        assert exported.status_code==200 and "service_uuid,category,code_type_id" in exported.text
