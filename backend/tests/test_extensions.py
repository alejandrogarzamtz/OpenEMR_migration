from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import ExtensionPackage, IntegrationEvent, WebhookDelivery, WebhookSubscription
from app.services.extensions import process_webhook_deliveries, publish_event


def admin_headers(client):
    token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def public_resolver(host,port,type):
    assert host=="hooks.example.test" and port==443
    return [(2,1,6,"",("93.184.216.34",443))]


def test_extension_manifest_credentials_namespace_and_signed_delivery():
    with TestClient(app) as client:
        headers=admin_headers(client)
        manifest={"key":"lab-bridge","name":"Lab Bridge","version":"1.0.0","api_version":"v1","capabilities":["events:publish"],"events":["extension.lab-bridge.result-ready"]}
        assert client.get("/api/v1/extensions/me").status_code==401
        assert client.post("/api/v1/admin/extensions",headers=headers,json={**manifest,"key":"wrong-namespace"}).status_code==422
        installed=client.post("/api/v1/admin/extensions",headers=headers,json=manifest)
        assert installed.status_code in {201,409}
        if installed.status_code==201:credential=installed.json()["credential"];extension_uuid=installed.json()["uuid"]
        else:
            extension=next(item for item in client.get("/api/v1/admin/extensions/overview",headers=headers).json()["extensions"] if item["key"]=="lab-bridge")
            extension_uuid=extension["uuid"];credential=client.post(f"/api/v1/admin/extensions/{extension_uuid}/rotate-credential",headers=headers).json()["credential"]
        subscription=client.post("/api/v1/admin/webhooks",headers=headers,json={"name":"Lab result receiver","endpoint_url":"https://hooks.example.test/events","event_types":["extension.lab-bridge.result-ready"],"extension_uuid":extension_uuid,"max_attempts":3})
        assert subscription.status_code==201;secret=subscription.json()["secret"]
        assert "secret" not in client.get("/api/v1/admin/extensions/overview",headers=headers).text
        extension_headers={"X-OpenRM-Extension-Key":credential}
        identity=client.get("/api/v1/extensions/me",headers=extension_headers)
        assert identity.status_code==200,identity.text
        assert identity.json()["key"]=="lab-bridge"
        updated=client.put(f"/api/v1/admin/extensions/{extension_uuid}",headers=headers,json={**manifest,"version":"1.1.0"})
        assert updated.status_code==200 and updated.json()["version"]=="1.1.0"
        assert client.put(f"/api/v1/admin/extensions/{extension_uuid}",headers=headers,json={**manifest,"key":"renamed"}).status_code==422
        assert client.post("/api/v1/extensions/events",headers=extension_headers,json={"event_type":"patient.updated","data":{}}).status_code==422
        published=client.post("/api/v1/extensions/events",headers=extension_headers,json={"event_type":"extension.lab-bridge.result-ready","resource_type":"DiagnosticReport","resource_id":"external-42","data":{"external_id":"42"}})
        assert published.status_code==202
        captured={}
        def send(url,body,delivery_headers):captured.update(url=url,body=body,headers=delivery_headers);return 204
        with SessionLocal() as db:
            result=process_webhook_deliveries(db,send=send,resolver=public_resolver)
            assert result["delivered"]>=1
        body=captured["body"];delivery_id=captured["headers"]["OpenRM-Webhook-Id"];timestamp=captured["headers"]["OpenRM-Webhook-Timestamp"]
        expected=hmac.new(secret.encode(),f"{delivery_id}.{timestamp}.".encode()+body,hashlib.sha256).hexdigest()
        assert captured["headers"]["OpenRM-Webhook-Signature"]==f"v1={expected}"
        assert json.loads(body)["data"]=={"external_id":"42"}


def test_webhook_ssrf_retry_dead_letter_and_replay_controls():
    with TestClient(app) as client:
        headers=admin_headers(client)
        assert client.post("/api/v1/admin/webhooks",headers=headers,json={"name":"Unsafe","endpoint_url":"http://127.0.0.1/hook","event_types":["api.mutation"]}).status_code==422
        created=client.post("/api/v1/admin/webhooks",headers=headers,json={"name":"Retry receiver","endpoint_url":"https://hooks.example.test/retry","event_types":["test.retry"],"max_attempts":2})
        assert created.status_code==201
        with SessionLocal() as db:
            publish_event(db,"test.retry",{"safe":"payload"});db.commit()
            now=datetime.now(timezone.utc)+timedelta(seconds=1)
            first=process_webhook_deliveries(db,send=lambda *_:500,resolver=public_resolver,current_time=now)
            delivery=db.scalar(select(WebhookDelivery).join(IntegrationEvent).where(IntegrationEvent.event_type=="test.retry").order_by(WebhookDelivery.id.desc()))
            assert first["retrying"]==1 and delivery.status=="retry" and delivery.attempts==1
            second=process_webhook_deliveries(db,send=lambda *_:500,resolver=public_resolver,current_time=now+timedelta(minutes=1))
            db.refresh(delivery);assert second["dead_letter"]==1 and delivery.status=="dead-letter" and delivery.attempts==2;delivery_uuid=delivery.uuid
        replay=client.post(f"/api/v1/admin/webhook-deliveries/{delivery_uuid}/replay",headers=headers)
        assert replay.status_code==200 and replay.json()["status"]=="pending"


def test_disabling_extension_blocks_credentials_and_new_delivery_queueing():
    with TestClient(app) as client:
        headers=admin_headers(client)
        installed=client.post("/api/v1/admin/extensions",headers=headers,json={"key":"disabled-source","name":"Disabled Source","version":"1.0.0","capabilities":["events:publish"],"events":["extension.disabled-source.changed"]})
        assert installed.status_code==201
        credential=installed.json()["credential"];uuid=installed.json()["uuid"]
        assert client.patch(f"/api/v1/admin/extensions/{uuid}",headers=headers,json={"status":"disabled"}).status_code==200
        assert client.get("/api/v1/extensions/me",headers={"X-OpenRM-Extension-Key":credential}).status_code==401
