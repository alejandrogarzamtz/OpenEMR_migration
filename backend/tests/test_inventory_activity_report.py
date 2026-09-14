from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import InventoryLot, InventoryProduct, InventoryTransaction, User
from app.security import password_hash


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    token = client.post("/api/v1/auth/token", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_inventory_activity_reconciles_balances_transfers_filters_acl_and_csv():
    with TestClient(app) as client:
        with SessionLocal() as db:
            product = InventoryProduct(name="Activity Vaccine", ndc_number="00011-2222")
            db.add(product); db.flush()
            source = InventoryLot(product_id=product.id, lot_number="SOURCE", warehouse_id="main", on_hand=4)
            destination = InventoryLot(product_id=product.id, lot_number="DEST", warehouse_id="satellite", on_hand=2)
            activity_date = date(2030, 2, 3)
            destroyed = InventoryLot(product_id=product.id, lot_number="DESTROYED", warehouse_id="main", on_hand=5, destroyed_at=activity_date)
            db.add_all([source, destination, destroyed]); db.flush()
            db.add_all([
                InventoryTransaction(product_id=product.id, lot_id=source.id, transaction_type="purchase", occurred_on=activity_date, quantity=10),
                InventoryTransaction(product_id=product.id, lot_id=destroyed.id, transaction_type="purchase", occurred_on=activity_date, quantity=5),
                InventoryTransaction(product_id=product.id, lot_id=source.id, transaction_type="dispense", occurred_on=activity_date, quantity=3),
                InventoryTransaction(product_id=product.id, lot_id=source.id, destination_lot_id=destination.id, transaction_type="transfer", occurred_on=activity_date, quantity=2),
                InventoryTransaction(product_id=product.id, lot_id=source.id, transaction_type="adjustment", occurred_on=activity_date, quantity=-1),
                User(email="activity-report@example.com", password_hash=password_hash.hash("report-password"), role="viewer", permissions=["acct:rep:read"]),
                User(email="activity-denied@example.com", password_hash=password_hash.hash("report-password"), role="viewer", permissions=["patients:demo:read"]),
            ])
            db.commit(); product_name = product.name

        headers = login(client, "activity-report@example.com", "report-password")
        run = client.post("/api/v1/reports/inventory_activity/runs", headers=headers, json={"date_from": "2030-02-03", "date_to": "2030-02-03"})
        assert run.status_code == 201
        report = run.json(); rows = {row["warehouse"]: row for row in report["rows"] if row["product"] == product_name}
        assert rows["main"] == {"product": product_name, "ndc": "00011-2222", "warehouse": "main", "starting_inventory": 0, "sales": -3, "distributions": 0, "purchases": 15, "transfers": -2, "adjustments": -6, "ending_inventory": 4}
        assert rows["satellite"]["starting_inventory"] == 0 and rows["satellite"]["transfers"] == 2 and rows["satellite"]["ending_inventory"] == 2
        for row in rows.values():
            assert row["ending_inventory"] == row["starting_inventory"] + sum(row[key] for key in ("sales", "distributions", "purchases", "transfers", "adjustments"))
        totals = report["totals"]
        assert {key: totals[key] for key in ("sales", "distributions", "purchases", "transfers", "adjustments")} == {"sales": -3, "distributions": 0, "purchases": 15, "transfers": 0, "adjustments": -6}
        assert totals["ending_inventory"] == totals["starting_inventory"] + sum(totals[key] for key in ("sales", "distributions", "purchases", "transfers", "adjustments"))

        main = client.post("/api/v1/reports/inventory_activity/runs", headers=headers, json={"date_from": "2030-02-03", "date_to": "2030-02-03", "warehouse_code": "main"})
        assert main.status_code == 201 and {row["warehouse"] for row in main.json()["rows"]} == {"main"}
        exported = client.get(f"/api/v1/report-runs/{report['uuid']}/export.csv", headers=headers)
        assert exported.status_code == 200 and product_name in exported.text
        assert exported.headers["x-report-checksum"] == report["checksum"]

        denied = login(client, "activity-denied@example.com", "report-password")
        assert client.post("/api/v1/reports/inventory_activity/runs", headers=denied, json={}).status_code == 403
        catalog = client.get("/api/v1/reports", headers=headers).json()
        item = next(entry for entry in catalog if entry["key"] == "inventory_activity")
        assert item["migrated"] is True and item["permission"] == "acct:rep:read"
