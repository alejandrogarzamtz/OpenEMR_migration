from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import json
import socket
from typing import Callable
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..mfa import decrypt_secret
from ..models import ExtensionPackage, IntegrationEvent, WebhookDelivery, WebhookSubscription

EVENT_NAME = r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$"


def event_matches(patterns: list[str], event_type: str) -> bool:
    return "*" in patterns or event_type in patterns or any(item.endswith(".*") and event_type.startswith(item[:-1]) for item in patterns)


def validate_webhook_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Webhook endpoint must be an HTTPS URL without credentials or fragments")
    try:
        address = ipaddress.ip_address(parsed.hostname)
        if not address.is_global: raise ValueError("Webhook endpoint cannot use a private or local address")
    except ValueError as exc:
        if "private or local" in str(exc): raise
    return value


def assert_public_destination(url: str, resolver: Callable = socket.getaddrinfo) -> None:
    hostname = urlparse(url).hostname
    if not hostname: raise ValueError("Webhook endpoint has no hostname")
    addresses = {result[4][0] for result in resolver(hostname, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(item).is_global for item in addresses):
        raise ValueError("Webhook destination resolved to a private, local, or invalid address")


def event_document(item: IntegrationEvent) -> dict:
    return {"id": item.uuid, "type": item.event_type, "schema_version": item.schema_version, "occurred_at": item.occurred_at.isoformat(), "resource": {"type": item.resource_type, "id": item.resource_id} if item.resource_type else None, "data": item.payload}


def publish_event(db: Session, event_type: str, payload: dict, *, source_extension_id: int | None = None, resource_type: str | None = None, resource_id: str | None = None) -> IntegrationEvent:
    item = IntegrationEvent(event_type=event_type, payload=payload, source_extension_id=source_extension_id, resource_type=resource_type, resource_id=resource_id)
    db.add(item); db.flush()
    subscriptions = list(db.scalars(select(WebhookSubscription).where(WebhookSubscription.active.is_(True))))
    for subscription in subscriptions:
        if subscription.extension_id:
            extension = db.get(ExtensionPackage, subscription.extension_id)
            if not extension or extension.status != "enabled": continue
        if event_matches(subscription.event_types, event_type): db.add(WebhookDelivery(subscription_id=subscription.id, event_id=item.id))
    return item


def signed_headers(delivery: WebhookDelivery, body: bytes, secret: str, timestamp: int) -> dict[str, str]:
    signed = f"{delivery.uuid}.{timestamp}.".encode() + body
    signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "OpenRM-Webhook-Id": delivery.uuid, "OpenRM-Webhook-Timestamp": str(timestamp), "OpenRM-Webhook-Signature": f"v1={signature}", "User-Agent": "OpenRM-Webhooks/1.0"}


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def http_send(url: str, body: bytes, headers: dict[str, str]) -> int:
    with build_opener(RejectRedirects).open(Request(url, data=body, headers=headers, method="POST"), timeout=10) as response:
        return response.status


def process_webhook_deliveries(db: Session, limit: int = 100, *, send: Callable = http_send, resolver: Callable = socket.getaddrinfo, current_time: datetime | None = None) -> dict:
    now = current_time or datetime.now(timezone.utc)
    rows = list(db.scalars(select(WebhookDelivery).where(WebhookDelivery.status.in_(["pending", "retry"]), WebhookDelivery.next_attempt_at <= now).order_by(WebhookDelivery.next_attempt_at, WebhookDelivery.id).limit(limit).with_for_update(skip_locked=True)))
    result = {"processed": 0, "delivered": 0, "retrying": 0, "dead_letter": 0}
    for delivery in rows:
        subscription = db.get(WebhookSubscription, delivery.subscription_id); event = db.get(IntegrationEvent, delivery.event_id)
        if not subscription or not event or not subscription.active:
            delivery.status = "dead-letter"; delivery.error_message = "Subscription or event is unavailable"; result["dead_letter"] += 1; continue
        document = event_document(event); body = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        delivery.attempts += 1; delivery.last_attempt_at = now; result["processed"] += 1
        try:
            assert_public_destination(subscription.endpoint_url, resolver)
            status = send(subscription.endpoint_url, body, signed_headers(delivery, body, decrypt_secret(subscription.encrypted_secret), int(now.timestamp())))
            delivery.response_status = status
            if not 200 <= status < 300: raise RuntimeError(f"Webhook endpoint returned HTTP {status}")
            delivery.status = "delivered"; delivery.delivered_at = now; delivery.error_message = None; result["delivered"] += 1
        except Exception as exc:
            delivery.error_message = str(exc)[:1000]
            if delivery.attempts >= subscription.max_attempts:
                delivery.status = "dead-letter"; result["dead_letter"] += 1
            else:
                delivery.status = "retry"; delivery.next_attempt_at = now + timedelta(seconds=min(86400, 30 * (2 ** (delivery.attempts - 1)))); result["retrying"] += 1
    db.commit(); return result
