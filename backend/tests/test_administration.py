from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import User
from app.security import password_hash


def login(client: TestClient, email: str = "admin@example.com", password: str = "change-me-now") -> dict[str,str]:
    token=client.post("/api/v1/auth/token",json={"email":email,"password":password}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_administration_catalog_and_facility_warehouse_scope():
    with TestClient(app) as client:
        admin=login(client)
        north=client.post("/api/v1/admin/facilities",headers=admin,json={"name":"North Clinic","email":"north@example.com","npi":"1234567890"})
        south=client.post("/api/v1/admin/facilities",headers=admin,json={"name":"South Clinic"})
        assert north.status_code==201 and south.status_code==201
        north=north.json(); south=south.json()
        north_wh=client.post("/api/v1/admin/warehouses",headers=admin,json={"code":"north-main","name":"North Pharmacy","facility_uuid":north["uuid"]}).json()
        south_wh=client.post("/api/v1/admin/warehouses",headers=admin,json={"code":"south-main","name":"South Pharmacy","facility_uuid":south["uuid"]}).json()
        practitioner=client.post("/api/v1/admin/practitioners",headers=admin,json={"first_name":"Ana","last_name":"Rivera","npi":"1098765432","primary_facility_uuid":north["uuid"],"calendar_enabled":True})
        assert practitioner.status_code==201 and practitioner.json()["primary_facility_uuid"]==north["uuid"]
        with SessionLocal() as db:
            restricted=User(email="scoped@example.com",password_hash=password_hash.hash("scoped-password"),role="clinician",permissions=["patients:demo:read","patients:appt:read","patients:appt:write","inventory:lots:read","inventory:lots:write","inventory:consumption:write"])
            db.add(restricted); db.commit(); db.refresh(restricted); restricted_uuid=restricted.uuid
        grant=client.post(f"/api/v1/admin/users/{restricted_uuid}/facility-access",headers=admin,json={"facility_uuid":north["uuid"],"warehouse_uuid":north_wh["uuid"]})
        assert grant.status_code==201
        scoped=login(client,"scoped@example.com","scoped-password")
        patient=client.post("/api/v1/patients",headers=admin,json={"first_name":"Scoped","last_name":"Patient","date_of_birth":"1990-01-01","sex":"unknown"}).json()
        base={"patient_uuid":patient["uuid"],"starts_at":"2026-12-01T10:00:00Z","ends_at":"2026-12-01T10:30:00Z"}
        allowed=client.post("/api/v1/appointments",headers=admin,json={**base,"facility_uuid":north["uuid"]}).json()
        denied=client.post("/api/v1/appointments",headers=admin,json={**base,"starts_at":"2026-12-01T11:00:00Z","ends_at":"2026-12-01T11:30:00Z","facility_uuid":south["uuid"]}).json()
        assert [item["uuid"] for item in client.get("/api/v1/appointments",headers=scoped).json()]==[allowed["uuid"]]
        assert client.get(f"/api/v1/appointments/{denied['uuid']}",headers=scoped).status_code==403
        assert client.post("/api/v1/appointments",headers=scoped,json={**base,"starts_at":"2026-12-01T12:00:00Z","ends_at":"2026-12-01T12:30:00Z","facility_uuid":south["uuid"]}).status_code==403
        allowed_flow=client.post(f"/api/v1/appointments/{allowed['uuid']}/patient-flow",headers=scoped,json={"status":"arrived","room":"N1"})
        assert allowed_flow.status_code==201
        assert client.post(f"/api/v1/appointments/{denied['uuid']}/patient-flow",headers=scoped,json={"status":"arrived","room":"S1"}).status_code==403
        assert [item["uuid"] for item in client.get("/api/v1/patient-flow",headers=scoped).json()]==[allowed_flow.json()["uuid"]]
        product=client.post("/api/v1/inventory/products",headers=admin,json={"name":"Scoped Supply"}).json()
        client.post(f"/api/v1/inventory/products/{product['uuid']}/lots",headers=admin,json={"lot_number":"N","warehouse_id":north_wh["code"],"opening_quantity":4})
        client.post(f"/api/v1/inventory/products/{product['uuid']}/lots",headers=admin,json={"lot_number":"S","warehouse_id":south_wh["code"],"opening_quantity":9})
        visible=client.get(f"/api/v1/inventory/products/{product['uuid']}/lots",headers=scoped).json()
        assert [lot["lot_number"] for lot in visible]==["N"]
        scoped_product=next(item for item in client.get("/api/v1/inventory/products",headers=scoped).json() if item["uuid"]==product["uuid"])
        assert scoped_product["on_hand"]==4
        assert client.post(f"/api/v1/inventory/products/{product['uuid']}/lots",headers=scoped,json={"lot_number":"X","warehouse_id":south_wh["code"]}).status_code==403
