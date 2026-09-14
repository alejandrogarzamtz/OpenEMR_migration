from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import User
from app.security import password_hash


def auth(client: TestClient) -> dict[str, str]:
    token = client.post("/api/v1/auth/token", json={"email": "admin@example.com", "password": "change-me-now"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_inventory_fefo_dispensing_movements_and_no_negative_stock():
    with TestClient(app) as client:
        headers = auth(client)
        patient = client.post("/api/v1/patients", headers=headers, json={"first_name":"Inventory","last_name":"Patient","date_of_birth":"1990-01-01","sex":"unknown"}).json()
        encounter = client.post("/api/v1/encounters", headers=headers, json={"patient_uuid":patient["uuid"],"occurred_at":"2026-09-14T12:00:00Z"}).json()
        product = client.post("/api/v1/inventory/products", headers=headers, json={"name":"Test Vaccine","ndc_number":"0001-0002","allow_combining":True}).json()
        first = client.post(f"/api/v1/inventory/products/{product['uuid']}/lots", headers=headers, json={"lot_number":"EARLY","expiration":"2027-01-01","warehouse_id":"main","opening_quantity":3}).json()
        second = client.post(f"/api/v1/inventory/products/{product['uuid']}/lots", headers=headers, json={"lot_number":"LATER","expiration":"2028-01-01","warehouse_id":"main","opening_quantity":5}).json()
        client.post(f"/api/v1/inventory/products/{product['uuid']}/lots", headers=headers, json={"lot_number":"EXPIRED","expiration":"2026-01-01","warehouse_id":"main","opening_quantity":20})

        dispensed = client.post(f"/api/v1/inventory/products/{product['uuid']}/dispense", headers=headers, json={"patient_uuid":patient["uuid"],"encounter_uuid":encounter["uuid"],"quantity":6,"fee":"60.00","warehouse_id":"main","occurred_on":"2026-09-14"})
        assert dispensed.status_code == 201
        assert [item["quantity"] for item in dispensed.json()] == [3, 3]
        assert [item["fee"] for item in dispensed.json()] == ["30.00", "30.00"]
        lots = client.get(f"/api/v1/inventory/products/{product['uuid']}/lots", headers=headers).json()
        balances = {lot["lot_number"]: lot["on_hand"] for lot in lots}
        assert balances == {"EXPIRED":20, "EARLY":0, "LATER":2}

        insufficient = client.post(f"/api/v1/inventory/products/{product['uuid']}/dispense", headers=headers, json={"patient_uuid":patient["uuid"],"encounter_uuid":encounter["uuid"],"quantity":3,"occurred_on":"2026-09-14"})
        assert insufficient.status_code == 409
        assert client.post(f"/api/v1/inventory/products/{product['uuid']}/movements", headers=headers, json={"transaction_type":"consumption","lot_uuid":second["uuid"],"quantity":3,"notes":"Damaged packaging"}).status_code == 409

        destination = client.post(f"/api/v1/inventory/products/{product['uuid']}/lots", headers=headers, json={"lot_number":"DEST","expiration":"2028-01-01","warehouse_id":"satellite"}).json()
        moved = client.post(f"/api/v1/inventory/products/{product['uuid']}/movements", headers=headers, json={"transaction_type":"transfer","lot_uuid":second["uuid"],"destination_lot_uuid":destination["uuid"],"quantity":2,"notes":"Restock satellite"})
        assert moved.status_code == 201
        refreshed = client.get(f"/api/v1/inventory/products/{product['uuid']}/lots", headers=headers).json()
        balances = {lot["lot_number"]: lot["on_hand"] for lot in refreshed}
        assert balances["LATER"] == 0 and balances["DEST"] == 2
        assert len(client.get(f"/api/v1/inventory/transactions?product_uuid={product['uuid']}", headers=headers).json()) == 6
        destroyed = client.post(f"/api/v1/inventory/products/{product['uuid']}/lots/{first['uuid']}/destroy", headers=headers, json={"method":"Expired stock","witness":"Pharmacist One","notes":"Verified count"})
        assert destroyed.status_code == 200
        assert client.post(f"/api/v1/inventory/products/{product['uuid']}/lots/{first['uuid']}/destroy", headers=headers, json={"method":"Again","witness":"Pharmacist One"}).status_code == 409


def test_inventory_requires_explicit_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email="inventory-denied@example.com", password_hash=password_hash.hash("viewer-password"), role="viewer", permissions=["patients:demo:read"]))
            db.commit()
        token = client.post("/api/v1/auth/token", json={"email":"inventory-denied@example.com","password":"viewer-password"}).json()["access_token"]
        assert client.get("/api/v1/inventory/products", headers={"Authorization":f"Bearer {token}"}).status_code == 403
