from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import User
from app.security import password_hash
from tests.test_communications import create_patient, create_portal, staff_headers


def test_portal_questionnaire_notifications_and_preferences():
    with TestClient(app) as client:
        staff=staff_headers(client);patient=create_patient(client,staff,"Engagement");portal=create_portal(client,staff,patient,"engagement-patient")
        definition=client.get("/api/v1/questionnaires",headers=staff).json()[0]
        assigned=client.post(f"/api/v1/patients/{patient['uuid']}/questionnaire-assignments",headers=staff,json={"questionnaire_uuid":definition["uuid"],"instructions":"Complete before the visit"})
        assert assigned.status_code==201
        waiting=client.get("/api/v1/portal/questionnaires",headers=portal).json();assert waiting[0]["uuid"]==assigned.json()["uuid"]
        answers={question["id"]:0 for question in definition["questions"]}
        completed=client.post(f"/api/v1/portal/questionnaires/{assigned.json()['uuid']}/responses",headers=portal,json={"answers":answers})
        assert completed.status_code==201 and completed.json()["score"]==0
        assert client.post(f"/api/v1/portal/questionnaires/{assigned.json()['uuid']}/responses",headers=portal,json={"answers":answers}).status_code==409
        notices=client.get("/api/v1/portal/notifications",headers=portal).json();assert notices[0]["event_type"]=="questionnaire"
        assert client.post(f"/api/v1/portal/notifications/{notices[0]['uuid']}/read",headers=portal).json()["read_at"]
        preferences=client.put("/api/v1/portal/notification-preferences",headers=portal,json={"email_enabled":False,"sms_enabled":False,"in_app_enabled":True,"message_events":True,"appointment_events":True,"result_events":True,"questionnaire_events":False,"timezone_name":"America/Monterrey"})
        assert preferences.status_code==200 and preferences.json()["questionnaire_events"] is False


def test_staff_group_thread_and_test_delivery_worker():
    with TestClient(app) as client:
        staff=staff_headers(client)
        with SessionLocal() as db:
            teammate=User(email="teammate@example.com",password_hash=password_hash.hash("teammate-password-123"),role="admin",active=True);db.add(teammate);db.commit();teammate_uuid=teammate.uuid
        created=client.post("/api/v1/staff-message-threads",headers=staff,json={"subject":"Care coordination","body":"Please review.","participant_user_uuids":[teammate_uuid]})
        assert created.status_code==201 and len(created.json()["participants"])==2
        replied=client.post(f"/api/v1/staff-message-threads/{created.json()['uuid']}/replies",headers=staff,json={"body":"Follow-up added."})
        assert replied.status_code==200 and len(replied.json()["messages"])==2
        assert client.post(f"/api/v1/staff-message-threads/{created.json()['uuid']}/close",headers=staff).json()["status"]=="closed"
        previous=settings.notification_delivery_mode;settings.notification_delivery_mode="test"
        try:
            result=client.post("/api/v1/communications/outbox/process",headers=staff).json();assert result["failed"]==0
        finally:settings.notification_delivery_mode=previous
