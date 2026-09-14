from fastapi.testclient import TestClient
from app.main import app

def test_patient_education_catalog_safe_search_administration_and_report():
    with TestClient(app) as client:
        token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];headers={"Authorization":f"Bearer {token}"}
        invalid=client.post("/api/v1/admin/patient-education/resources",headers=headers,json={"name":"Unsafe","url_template":"javascript:alert([%])"})
        assert invalid.status_code==422
        missing_placeholder=client.post("/api/v1/admin/patient-education/resources",headers=headers,json={"name":"Invalid","url_template":"https://example.org/search"})
        assert missing_placeholder.status_code==422
        created=client.post("/api/v1/admin/patient-education/resources",headers=headers,json={"name":"Medical Library","url_template":"https://example.org/search?q=[%]&source=openrm","sequence":10,"active":True})
        assert created.status_code==201;uuid=created.json()["uuid"]
        catalog=client.get("/api/v1/patient-education/resources",headers=headers)
        assert catalog.status_code==200 and any(item["uuid"]==uuid for item in catalog.json())
        search=client.get(f"/api/v1/patient-education/resources/{uuid}/search",headers=headers,params={"q":"heart health & diet"})
        assert search.status_code==200 and search.json()["url"]=="https://example.org/search?q=heart%20health%20%26%20diet&source=openrm"
        updated=client.patch(f"/api/v1/admin/patient-education/resources/{uuid}",headers=headers,json={"name":"Medical Library","url_template":"https://example.org/search?q=[%]","sequence":10,"active":False})
        assert updated.status_code==200 and updated.json()["active"] is False
        assert client.get(f"/api/v1/patient-education/resources/{uuid}/search",headers=headers,params={"q":"heart"}).status_code==409
        report=client.post("/api/v1/reports/patient_edu_web_lookup/runs",headers=headers,json={})
        assert report.status_code==201 and report.json()["totals"]["resources"]>=1
        assert report.json()["columns"]==["resource_uuid","name","url_template","sequence","active","legacy_option_id"]
