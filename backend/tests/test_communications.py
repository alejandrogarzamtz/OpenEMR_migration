from fastapi.testclient import TestClient

from app.main import app


def staff_headers(client: TestClient) -> dict[str, str]:
    token = client.post(
        "/api/v1/auth/token",
        json={"email": "admin@example.com", "password": "change-me-now"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_patient(client: TestClient, headers: dict[str, str], name: str, *, consent: bool = True) -> dict:
    response = client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "first_name": name,
            "last_name": "Portal",
            "date_of_birth": "1990-01-01",
            "sex": "unknown",
            "email": f"{name.lower()}@example.com",
            "portal_allowed": True,
            "allow_email": consent,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_portal(client: TestClient, headers: dict[str, str], patient: dict, username: str) -> dict[str, str]:
    response = client.post(
        f"/api/v1/patients/{patient['uuid']}/portal-account",
        headers=headers,
        json={"username": username, "temporary_password": "temporary-password-123"},
    )
    assert response.status_code == 201
    login = client.post(
        "/api/v1/portal/auth/token",
        json={"username": username, "password": "temporary-password-123"},
    )
    assert login.status_code == 200
    portal_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert login.json()["force_password_reset"] is True
    assert client.get("/api/v1/portal/messages", headers=portal_headers).status_code == 403
    changed = client.post(
        "/api/v1/portal/password",
        headers=portal_headers,
        json={"new_password": "permanent-password-456"},
    )
    assert changed.status_code == 204
    return portal_headers


def test_secure_messages_isolate_patients_and_protect_notification_content():
    with TestClient(app) as client:
        staff = staff_headers(client)
        first = create_patient(client, staff, "CommsOne")
        second = create_patient(client, staff, "CommsTwo")
        first_portal = create_portal(client, staff, first, "comms-one")
        second_portal = create_portal(client, staff, second, "comms-two")

        clinical_body = "Private diagnosis: information that must remain in the portal."
        created = client.post(
            f"/api/v1/patients/{first['uuid']}/messages",
            headers=staff,
            json={"subject": "Care plan", "body": clinical_body},
        )
        assert created.status_code == 201
        thread_uuid = created.json()["uuid"]

        assert client.get("/api/v1/portal/messages", headers=first_portal).json()[0]["uuid"] == thread_uuid
        assert client.get(f"/api/v1/portal/messages/{thread_uuid}", headers=second_portal).status_code == 404
        assert client.get("/api/v1/patients", headers=first_portal).status_code == 401
        assert client.get("/api/v1/portal/messages", headers=staff).status_code == 401

        reply = client.post(
            f"/api/v1/portal/messages/{thread_uuid}/replies",
            headers=first_portal,
            json={"body": "Thank you. I have reviewed the plan."},
        )
        assert reply.status_code == 200
        staff_view = client.get(f"/api/v1/messages/{thread_uuid}", headers=staff).json()
        assert [message["sender_kind"] for message in staff_view["messages"]] == ["staff", "patient"]

        outbox = client.get("/api/v1/communications/outbox", headers=staff)
        assert outbox.status_code == 200
        notice = next(item for item in outbox.json() if item["recipient"] == first["email"])
        assert clinical_body not in notice["subject"] + notice.get("body", "")


def test_no_consent_means_no_email_and_tasks_complete():
    with TestClient(app) as client:
        staff = staff_headers(client)
        patient = create_patient(client, staff, "CommsNoConsent", consent=False)
        created = client.post(
            f"/api/v1/patients/{patient['uuid']}/messages",
            headers=staff,
            json={"subject": "Portal only", "body": "This should not create email."},
        )
        assert created.status_code == 201
        recipients = [item["recipient"] for item in client.get("/api/v1/communications/outbox", headers=staff).json()]
        assert patient["email"] not in recipients

        task = client.post(
            "/api/v1/tasks",
            headers=staff,
            json={"patient_uuid": patient["uuid"], "method": "portal", "comment": "Review response"},
        )
        assert task.status_code == 201
        completed = client.patch(f"/api/v1/tasks/{task.json()['uuid']}/complete", headers=staff)
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"


def test_portal_login_locks_after_repeated_failures():
    with TestClient(app) as client:
        staff = staff_headers(client)
        patient = create_patient(client, staff, "CommsLocked")
        client.post(
            f"/api/v1/patients/{patient['uuid']}/portal-account",
            headers=staff,
            json={"username": "comms-locked", "temporary_password": "temporary-password-123"},
        )
        for _ in range(5):
            response = client.post(
                "/api/v1/portal/auth/token",
                json={"username": "comms-locked", "password": "incorrect-password"},
            )
            assert response.status_code == 401
        locked = client.post(
            "/api/v1/portal/auth/token",
            json={"username": "comms-locked", "password": "temporary-password-123"},
        )
        assert locked.status_code == 401


def test_portal_session_refresh_and_logout_are_revocable():
    with TestClient(app) as client:
        staff = staff_headers(client)
        patient = create_patient(client, staff, "CommsSession")
        portal = create_portal(client, staff, patient, "comms-session")
        old_access = portal["Authorization"].removeprefix("Bearer ")
        refreshed = client.post("/api/v1/portal/auth/refresh")
        assert refreshed.status_code == 200
        new_access = refreshed.json()["access_token"]
        assert new_access != old_access
        assert client.get("/api/v1/portal/messages", headers=portal).status_code == 401
        new_headers = {"Authorization": f"Bearer {new_access}"}
        assert client.get("/api/v1/portal/messages", headers=new_headers).status_code == 200
        assert client.post("/api/v1/portal/auth/logout", headers=new_headers).status_code == 204
        assert client.get("/api/v1/portal/messages", headers=new_headers).status_code == 401
