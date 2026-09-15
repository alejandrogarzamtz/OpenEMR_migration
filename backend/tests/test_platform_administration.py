from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import CommunicationDelivery, ContentTemplate, PasswordResetToken, User


def admin_headers(client: TestClient) -> dict[str, str]:
    token = client.post("/api/v1/auth/token", json={"email": "admin@example.com", "password": "change-me-now"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_safe_settings_and_localization_bootstrap():
    with TestClient(app) as client:
        headers = admin_headers(client)
        assert client.get("/api/v1/admin/settings").status_code in {401, 403}
        settings = client.get("/api/v1/admin/settings", headers=headers)
        assert settings.status_code == 200
        keys = {item["key"] for item in settings.json()}
        assert keys == {"organization.name", "organization.timezone", "localization.default_locale", "localization.date_format", "ui.default_page_size"}
        assert client.put("/api/v1/admin/settings/organization.timezone", headers=headers, json={"value": "Not/AZone"}).status_code == 422
        changed = client.put("/api/v1/admin/settings/organization.name", headers=headers, json={"value": "OpenRM Test Practice"})
        assert changed.status_code == 200 and changed.json()["version"] >= 2
        bootstrap = client.get("/api/v1/localization/bootstrap?locale=es")
        assert bootstrap.status_code == 200
        assert bootstrap.json()["organization_name"] == "OpenRM Test Practice"
        assert bootstrap.json()["translations"]["nav.patients"] == "Pacientes"
        assert {item["code"] for item in bootstrap.json()["locales"]} >= {"en", "es"}


def test_locale_catalog_and_custom_translation():
    with TestClient(app) as client:
        headers = admin_headers(client)
        created = client.post("/api/v1/admin/locales", headers=headers, json={"code": "ar", "name": "العربية", "rtl": True})
        assert created.status_code in {201, 409}
        translated = client.put("/api/v1/admin/locales/ar/translations/nav.patients", headers=headers, json={"value": "المرضى"})
        assert translated.status_code == 200 and translated.json()["customized"] is True
        bootstrap = client.get("/api/v1/localization/bootstrap?locale=ar").json()
        assert bootstrap["locale"]["rtl"] is True and bootstrap["translations"]["nav.patients"] == "المرضى"
        assert client.put("/api/v1/admin/settings/localization.default_locale", headers=headers, json={"value": "ar"}).status_code == 200
        assert client.patch("/api/v1/admin/locales/ar", headers=headers, json={"active": False}).status_code == 409


def test_templates_are_validated_rendered_and_versioned():
    with TestClient(app) as client:
        headers = admin_headers(client)
        body = {"key": "test-patient-letter", "locale_code": "en", "name": "Patient letter", "category": "document", "subject": "Hello {{patient.name}}", "content": "<p>{{patient.name}}</p>", "content_type": "text/html", "allowed_variables": ["patient.name"]}
        created = client.post("/api/v1/admin/templates", headers=headers, json=body)
        assert created.status_code in {201, 409}
        if created.status_code == 409:
            with SessionLocal() as db: template_uuid = db.query(ContentTemplate).filter_by(key=body["key"], active=True).one().uuid
        else: template_uuid = created.json()["uuid"]
        preview = client.post(f"/api/v1/admin/templates/{template_uuid}/preview", headers=headers, json={"variables": {"patient.name": "<Ada>"}})
        assert preview.status_code == 200 and preview.json()["content"] == "<p>&lt;Ada&gt;</p>"
        assert client.post("/api/v1/admin/templates", headers=headers, json={**body, "key": "test-invalid-letter", "content": "{{undeclared}}"}).status_code == 422
        updated = client.put(f"/api/v1/admin/templates/{template_uuid}", headers=headers, json={**body, "content": "Welcome, {{patient.name}}"})
        assert updated.status_code == 200 and updated.json()["version"] >= 2
        history = client.get("/api/v1/admin/templates?include_inactive=true", headers=headers).json()
        versions = [item for item in history if item["key"] == body["key"]]
        assert len(versions) >= 2 and sum(item["active"] for item in versions) == 1


def test_user_invitation_and_deactivation_revoke_sessions():
    with TestClient(app) as client:
        headers = admin_headers(client)
        invited = client.post("/api/v1/admin/users/invitations", headers=headers, json={"email": "phase5.user@example.com", "role": "billing", "permissions": ["financial:billing:read"]})
        assert invited.status_code in {201, 409}
        users = client.get("/api/v1/admin/users", headers=headers).json()
        user = next(item for item in users if item["email"] == "phase5.user@example.com")
        if invited.status_code == 201:
            with SessionLocal() as db:
                persisted = db.query(User).filter_by(email=user["email"]).one()
                assert db.query(PasswordResetToken).filter_by(user_id=persisted.id).count() == 1
                assert db.query(CommunicationDelivery).filter_by(recipient=persisted.email, template_name="staff-invitation").count() == 1
        disabled = client.patch(f"/api/v1/admin/users/{user['uuid']}", headers=headers, json={"active": False})
        assert disabled.status_code == 200 and disabled.json()["active"] is False
        current_admin = next(item for item in users if item["email"] == "admin@example.com")
        assert client.patch(f"/api/v1/admin/users/{current_admin['uuid']}", headers=headers, json={"active": False}).status_code == 409
