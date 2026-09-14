from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import ClaimPayment, PaymentIntent
from test_communications import create_patient, create_portal, staff_headers


def create_claim(client: TestClient, staff: dict[str, str], patient_uuid: str) -> dict:
    encounter = client.post("/api/v1/encounters", headers=staff, json={"patient_uuid": patient_uuid, "occurred_at": "2026-09-16T09:00:00Z", "type": "office"}).json()
    charge = client.post(f"/api/v1/patients/{patient_uuid}/charges", headers=staff, json={"encounter_uuid": encounter["uuid"], "code_system": "CPT", "code": "99213", "description": "Office visit", "units": 1, "unit_price": "20.00"}).json()
    response = client.post(f"/api/v1/patients/{patient_uuid}/claims", headers=staff, json={"encounter_uuid": encounter["uuid"], "charge_uuids": [charge["uuid"]]})
    assert response.status_code == 201
    return response.json()


def test_portal_statement_release_isolation_and_idempotent_tokenized_payment():
    original_provider = settings.payment_provider
    original_environment = settings.deployment_environment
    try:
        with TestClient(app) as client:
            staff = staff_headers(client)
            first = create_patient(client, staff, "BillingOne")
            second = create_patient(client, staff, "BillingTwo")
            first_portal = create_portal(client, staff, first, "billing-one")
            second_portal = create_portal(client, staff, second, "billing-two")
            claim = create_claim(client, staff, first["uuid"])

            assert client.get("/api/v1/portal/billing/statement", headers=first_portal).json()["claims"] == []
            released = client.post(f"/api/v1/patients/{first['uuid']}/claims/{claim['uuid']}/release", headers=staff)
            assert released.status_code == 200
            assert client.get("/api/v1/portal/billing/statement", headers=second_portal).json()["claims"] == []

            settings.payment_provider = "disabled"
            unavailable = client.post("/api/v1/portal/billing/payment-intents", headers={**first_portal, "Idempotency-Key": "disabled-attempt-1"}, json={"claim_uuid": claim["uuid"], "amount": "5.00", "payment_method_token": "opaque-token-never-stored"})
            assert unavailable.status_code == 201
            assert unavailable.json()["status"] == "failed"
            assert unavailable.json()["failure_code"] == "processor_not_configured"

            settings.payment_provider = "test"
            settings.deployment_environment = "production"
            forbidden_test = client.post("/api/v1/portal/billing/payment-intents", headers={**first_portal, "Idempotency-Key": "forbidden-test-adapter"}, json={"claim_uuid": claim["uuid"], "amount": "1.00", "payment_method_token": "tok_test_visa"})
            assert forbidden_test.json()["status"] == "failed"
            assert forbidden_test.json()["failure_code"] == "processor_not_configured"
            settings.deployment_environment = "test"
            body = {"claim_uuid": claim["uuid"], "amount": "10.00", "payment_method_token": "tok_test_visa"}
            headers = {**first_portal, "Idempotency-Key": "successful-attempt-1"}
            paid = client.post("/api/v1/portal/billing/payment-intents", headers=headers, json=body)
            assert paid.status_code == 201
            assert paid.json()["status"] == "succeeded"
            replay = client.post("/api/v1/portal/billing/payment-intents", headers=headers, json=body)
            assert replay.json()["uuid"] == paid.json()["uuid"]
            assert client.post("/api/v1/portal/billing/payment-intents", headers=headers, json={**body, "amount": "9.00"}).status_code == 409
            assert client.post("/api/v1/portal/billing/payment-intents", headers={**second_portal, "Idempotency-Key": "cross-patient-1"}, json=body).status_code == 404

            statement = client.get("/api/v1/portal/billing/statement", headers=first_portal).json()
            assert Decimal(statement["total_charges"]) == Decimal("20.00")
            assert Decimal(statement["total_paid"]) == Decimal("10.00")
            assert Decimal(statement["balance"]) == Decimal("10.00")
            assert len(statement["claims"][0]["payments"]) == 1

        with SessionLocal() as db:
            intents = list(db.scalars(select(PaymentIntent).where(PaymentIntent.claim_id.is_not(None))))
            assert any(item.status == "failed" for item in intents)
            assert any(item.status == "succeeded" for item in intents)
            assert len(list(db.scalars(select(ClaimPayment).where(ClaimPayment.method == "portal-card")))) == 1
            assert "payment_method_token" not in PaymentIntent.__table__.columns
    finally:
        settings.payment_provider = original_provider
        settings.deployment_environment = original_environment
