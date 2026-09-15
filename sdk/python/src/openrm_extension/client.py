from collections.abc import Callable, Mapping
import hashlib
import hmac
import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class ExtensionError(RuntimeError):
    pass


class ExtensionClient:
    def __init__(self, base_url: str, credential: str, *, opener: Callable = urlopen):
        self.base_url = base_url.rstrip("/")
        self.credential = credential
        self.opener = opener

    def identity(self) -> dict:
        return self._request("GET", "/api/v1/extensions/me")

    def publish(self, event_type: str, data: dict, *, resource_type: str | None = None, resource_id: str | None = None) -> dict:
        return self._request("POST", "/api/v1/extensions/events", {"event_type": event_type, "resource_type": resource_type, "resource_id": resource_id, "data": data})

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode() if payload is not None else None
        request = Request(self.base_url + path, data=body, method=method, headers={"X-OpenRM-Extension-Key": self.credential, "Content-Type": "application/json"})
        try:
            with self.opener(request, timeout=10) as response: return json.loads(response.read())
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise ExtensionError(f"OpenRM returned HTTP {exc.code}: {detail}") from exc


def verify_webhook(body: bytes, headers: Mapping[str, str], secret: str, *, now: int | None = None, tolerance_seconds: int = 300, seen: Callable[[str], bool] | None = None) -> dict:
    normalized_headers = {key.lower(): value for key, value in headers.items()}
    delivery_id = normalized_headers.get("openrm-webhook-id", "")
    timestamp_text = normalized_headers.get("openrm-webhook-timestamp", "")
    signature = normalized_headers.get("openrm-webhook-signature", "")
    try: timestamp = int(timestamp_text)
    except ValueError as exc: raise ExtensionError("Webhook timestamp is invalid") from exc
    current = int(time.time()) if now is None else now
    if not delivery_id or abs(current - timestamp) > tolerance_seconds: raise ExtensionError("Webhook is missing an ID or is outside the replay window")
    expected = hmac.new(secret.encode(), f"{delivery_id}.{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    if not signature.startswith("v1=") or not hmac.compare_digest(signature[3:], expected): raise ExtensionError("Webhook signature is invalid")
    if seen and seen(delivery_id): raise ExtensionError("Webhook delivery was already processed")
    document = json.loads(body)
    if document.get("id") == delivery_id: raise ExtensionError("Event ID and delivery ID must be distinct")
    return document
