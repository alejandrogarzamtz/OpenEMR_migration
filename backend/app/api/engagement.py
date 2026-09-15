from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import AuditEvent, IdentityAuditEvent, NotificationPreference, Patient, PortalNotification, QuestionnaireAssignment, QuestionnaireDefinition, QuestionnaireResponse, StaffMessage, StaffMessageThread, StaffThreadParticipant, User
from ..security import administration_user, clinical_user, clinical_write_user, communication_user, communication_write_user
from ..services.delivery_worker import process_outbox
from ..services.notifications import notify_patient, preference_for
from ..services.patients import patient_by_uuid
from ..services.portal_access import PortalPatientContext, require_portal_scope

router=APIRouter(prefix="/api/v1",tags=["patient engagement"])


def now():return datetime.now(timezone.utc)


class AssignmentCreate(BaseModel):
    questionnaire_uuid:str
    instructions:str|None=Field(default=None,max_length=4000)
    due_at:datetime|None=None
    @field_validator("due_at")
    @classmethod
    def aware(cls,value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):raise ValueError("due_at must include a timezone")
        return value


class PortalAnswers(BaseModel):answers:dict[str,Any]


class PreferenceUpdate(BaseModel):
    email_enabled:bool=False;sms_enabled:bool=False;in_app_enabled:bool=True
    message_events:bool=True;appointment_events:bool=True;result_events:bool=True;questionnaire_events:bool=True
    timezone_name:str=Field(default="UTC",min_length=1,max_length=64)
    @field_validator("timezone_name")
    @classmethod
    def valid_timezone(cls,value):
        try:ZoneInfo(value)
        except ZoneInfoNotFoundError:raise ValueError("timezone_name must be an IANA time zone")
        return value


class StaffThreadCreate(BaseModel):
    subject:str=Field(min_length=2,max_length=255);body:str=Field(min_length=1,max_length=20000);participant_user_uuids:list[str]=Field(min_length=1,max_length=100)


class Reply(BaseModel):body:str=Field(min_length=1,max_length=20000)


def assignment_out(item,definition,patient):
    return {"uuid":item.uuid,"patient_uuid":patient.uuid,"questionnaire_uuid":definition.uuid,"code":definition.code,"title":definition.title,"questions":definition.questions,"instructions":item.instructions,"status":item.status,"assigned_at":item.assigned_at,"due_at":item.due_at,"completed_at":item.completed_at}


def score_answers(definition:QuestionnaireDefinition,answers:dict)->tuple[int,str]:
    questions={str(item["id"]):item for item in definition.questions}
    if set(answers)!=set(questions):raise HTTPException(status_code=422,detail="Every questionnaire item requires an answer")
    total=0
    for key,question in questions.items():
        value=answers[key];kind=question.get("type","integer")
        if kind=="integer":
            if isinstance(value,bool) or not isinstance(value,int) or value<question.get("min",0) or value>question.get("max",3):raise HTTPException(status_code=422,detail=f"Invalid answer for {key}")
            total+=int(question.get("scores",{}).get(str(value),value))
        elif kind=="boolean":
            if not isinstance(value,bool):raise HTTPException(status_code=422,detail=f"Invalid answer for {key}")
            total+=int(question.get("scores",{}).get(str(value).lower(),0))
        elif kind in {"string","choice"}:
            if not isinstance(value,str) or not value.strip():raise HTTPException(status_code=422,detail=f"Invalid answer for {key}")
            choices=question.get("options") or []
            if kind=="choice" and value not in choices:raise HTTPException(status_code=422,detail=f"Invalid answer for {key}")
            total+=int(question.get("scores",{}).get(value,0))
        else:raise HTTPException(status_code=422,detail=f"Unsupported question type {kind}")
    if definition.code=="PHQ-9":interpretation="minimal" if total<=4 else "mild" if total<=9 else "moderate" if total<=14 else "moderately-severe" if total<=19 else "severe"
    elif definition.code=="GAD-7":interpretation="minimal" if total<=4 else "mild" if total<=9 else "moderate" if total<=14 else "severe"
    else:interpretation="completed"
    return total,interpretation


@router.get("/patients/{patient_uuid}/questionnaire-assignments")
def staff_assignments(patient_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);rows=db.execute(select(QuestionnaireAssignment,QuestionnaireDefinition).join(QuestionnaireDefinition).where(QuestionnaireAssignment.patient_id==patient.id).order_by(QuestionnaireAssignment.assigned_at.desc())).all();return [assignment_out(item,definition,patient) for item,definition in rows]


@router.post("/patients/{patient_uuid}/questionnaire-assignments",status_code=201)
def assign_questionnaire(patient_uuid:str,body:AssignmentCreate,db:Session=Depends(get_db),user:User=Depends(clinical_write_user)):
    patient=patient_by_uuid(db,patient_uuid);definition=db.scalar(select(QuestionnaireDefinition).where(QuestionnaireDefinition.uuid==body.questionnaire_uuid,QuestionnaireDefinition.active.is_(True)))
    if not definition:raise HTTPException(status_code=404,detail="Questionnaire not found")
    duplicate=db.scalar(select(QuestionnaireAssignment.id).where(QuestionnaireAssignment.patient_id==patient.id,QuestionnaireAssignment.questionnaire_id==definition.id,QuestionnaireAssignment.status=="assigned"))
    if duplicate:raise HTTPException(status_code=409,detail="This questionnaire is already assigned")
    item=QuestionnaireAssignment(patient_id=patient.id,questionnaire_id=definition.id,assigned_by_id=user.id,instructions=body.instructions,due_at=body.due_at);db.add(item);db.flush();notify_patient(db,patient,"questionnaire","New questionnaire","A questionnaire is ready to complete.","/portal#questionnaires");db.add(AuditEvent(actor_id=user.id,action="assign",resource_type="questionnaire_assignment",resource_id=item.uuid));db.commit();return assignment_out(item,definition,patient)


@router.post("/patients/{patient_uuid}/questionnaire-assignments/{assignment_uuid}/cancel")
def cancel_assignment(patient_uuid:str,assignment_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_write_user)):
    patient=patient_by_uuid(db,patient_uuid);item=db.scalar(select(QuestionnaireAssignment).where(QuestionnaireAssignment.uuid==assignment_uuid,QuestionnaireAssignment.patient_id==patient.id))
    if not item:raise HTTPException(status_code=404,detail="Questionnaire assignment not found")
    if item.status=="completed":raise HTTPException(status_code=409,detail="Completed questionnaires cannot be cancelled")
    item.status="cancelled";item.cancelled_at=now();db.add(AuditEvent(actor_id=user.id,action="cancel",resource_type="questionnaire_assignment",resource_id=item.uuid));db.commit();return {"uuid":item.uuid,"status":item.status}


@router.get("/portal/questionnaires")
def portal_questionnaires(context:PortalPatientContext=Depends(require_portal_scope("questionnaires")),db:Session=Depends(get_db)):
    if not settings.portal_questionnaires_enabled:raise HTTPException(status_code=404,detail="Portal feature is not enabled")
    rows=db.execute(select(QuestionnaireAssignment,QuestionnaireDefinition).join(QuestionnaireDefinition).where(QuestionnaireAssignment.patient_id==context.patient.id,QuestionnaireAssignment.status.in_(["assigned","completed"])).order_by(QuestionnaireAssignment.assigned_at.desc())).all();db.add(IdentityAuditEvent(identity_kind="portal",portal_account_id=context.account.id,patient_id=context.patient.id,action="search",resource_type="questionnaire_assignment"));db.commit();return [assignment_out(item,definition,context.patient) for item,definition in rows]


@router.post("/portal/questionnaires/{assignment_uuid}/responses",status_code=201)
def answer_questionnaire(assignment_uuid:str,body:PortalAnswers,context:PortalPatientContext=Depends(require_portal_scope("questionnaires")),db:Session=Depends(get_db)):
    if not settings.portal_questionnaires_enabled:raise HTTPException(status_code=404,detail="Portal feature is not enabled")
    row=db.execute(select(QuestionnaireAssignment,QuestionnaireDefinition).join(QuestionnaireDefinition).where(QuestionnaireAssignment.uuid==assignment_uuid,QuestionnaireAssignment.patient_id==context.patient.id).with_for_update()).first()
    if not row:raise HTTPException(status_code=404,detail="Questionnaire assignment not found")
    item,definition=row
    if item.status!="assigned":raise HTTPException(status_code=409,detail="Questionnaire assignment is not open")
    score,interpretation=score_answers(definition,body.answers);response=QuestionnaireResponse(patient_id=context.patient.id,questionnaire_id=definition.id,answers=body.answers,score=score,interpretation=interpretation,author_portal_account_id=context.account.id);db.add(response);db.flush();item.response_id=response.id;item.status="completed";item.completed_at=now();db.add(IdentityAuditEvent(identity_kind="portal",portal_account_id=context.account.id,patient_id=context.patient.id,action="complete",resource_type="questionnaire_assignment",resource_id=item.uuid,detail=f"{definition.code} score={score}"));db.commit();return {"uuid":response.uuid,"assignment_uuid":item.uuid,"questionnaire_uuid":definition.uuid,"code":definition.code,"answers":response.answers,"score":score,"interpretation":interpretation,"authored_at":response.authored_at}


def preference_out(item):return {key:getattr(item,key) for key in ("email_enabled","sms_enabled","in_app_enabled","message_events","appointment_events","result_events","questionnaire_events","timezone_name")}


@router.get("/portal/notification-preferences")
def get_preferences(context:PortalPatientContext=Depends(require_portal_scope("notifications")),db:Session=Depends(get_db)):
    if not settings.portal_notifications_enabled:raise HTTPException(status_code=404,detail="Portal feature is not enabled")
    item=preference_for(db,context.account,context.patient);db.commit();return preference_out(item)


@router.put("/portal/notification-preferences")
def update_preferences(body:PreferenceUpdate,context:PortalPatientContext=Depends(require_portal_scope("notifications")),db:Session=Depends(get_db)):
    if not settings.portal_notifications_enabled:raise HTTPException(status_code=404,detail="Portal feature is not enabled")
    if body.email_enabled and (not context.account.email or not context.patient.allow_email):raise HTTPException(status_code=422,detail="Email delivery is not available for this patient context")
    if body.sms_enabled and (not context.patient.phone or not context.patient.allow_sms):raise HTTPException(status_code=422,detail="SMS delivery is not available for this patient context")
    item=preference_for(db,context.account,context.patient)
    for key,value in body.model_dump().items():setattr(item,key,value)
    db.add(IdentityAuditEvent(identity_kind="portal",portal_account_id=context.account.id,patient_id=context.patient.id,action="update",resource_type="notification_preference",resource_id=item.uuid));db.commit();return preference_out(item)


def notification_out(item):return {"uuid":item.uuid,"event_type":item.event_type,"title":item.title,"body":item.body,"action_url":item.action_url,"created_at":item.created_at,"read_at":item.read_at}


@router.get("/portal/notifications")
def list_notifications(unread:bool=False,context:PortalPatientContext=Depends(require_portal_scope("notifications")),db:Session=Depends(get_db)):
    if not settings.portal_notifications_enabled:raise HTTPException(status_code=404,detail="Portal feature is not enabled")
    query=select(PortalNotification).where(PortalNotification.portal_account_id==context.account.id,PortalNotification.patient_id==context.patient.id,PortalNotification.dismissed_at.is_(None))
    if unread:query=query.where(PortalNotification.read_at.is_(None))
    rows=list(db.scalars(query.order_by(PortalNotification.created_at.desc()).limit(200)));db.add(IdentityAuditEvent(identity_kind="portal",portal_account_id=context.account.id,patient_id=context.patient.id,action="search",resource_type="portal_notification"));db.commit();return [notification_out(item) for item in rows]


@router.post("/portal/notifications/{notification_uuid}/read")
def read_notification(notification_uuid:str,context:PortalPatientContext=Depends(require_portal_scope("notifications")),db:Session=Depends(get_db)):
    if not settings.portal_notifications_enabled:raise HTTPException(status_code=404,detail="Portal feature is not enabled")
    item=db.scalar(select(PortalNotification).where(PortalNotification.uuid==notification_uuid,PortalNotification.portal_account_id==context.account.id,PortalNotification.patient_id==context.patient.id))
    if not item:raise HTTPException(status_code=404,detail="Notification not found")
    item.read_at=item.read_at or now();db.add(IdentityAuditEvent(identity_kind="portal",portal_account_id=context.account.id,patient_id=context.patient.id,action="read",resource_type="portal_notification",resource_id=item.uuid));db.commit();return notification_out(item)


@router.post("/portal/notifications/{notification_uuid}/dismiss")
def dismiss_notification(notification_uuid:str,context:PortalPatientContext=Depends(require_portal_scope("notifications")),db:Session=Depends(get_db)):
    if not settings.portal_notifications_enabled:raise HTTPException(status_code=404,detail="Portal feature is not enabled")
    item=db.scalar(select(PortalNotification).where(PortalNotification.uuid==notification_uuid,PortalNotification.portal_account_id==context.account.id,PortalNotification.patient_id==context.patient.id))
    if not item:raise HTTPException(status_code=404,detail="Notification not found")
    item.dismissed_at=now();db.add(IdentityAuditEvent(identity_kind="portal",portal_account_id=context.account.id,patient_id=context.patient.id,action="dismiss",resource_type="portal_notification",resource_id=item.uuid));db.commit();return {"uuid":item.uuid,"dismissed":True}


def staff_thread_out(db,item):
    participants=db.execute(select(StaffThreadParticipant,User).join(User).where(StaffThreadParticipant.thread_id==item.id)).all();messages=db.execute(select(StaffMessage,User).join(User,StaffMessage.sender_user_id==User.id).where(StaffMessage.thread_id==item.id,StaffMessage.deleted_at.is_(None)).order_by(StaffMessage.created_at)).all();return {"uuid":item.uuid,"subject":item.subject,"status":item.status,"updated_at":item.updated_at,"participants":[{"uuid":user.uuid,"email":user.email,"role":part.role,"read_at":part.read_at} for part,user in participants],"messages":[{"uuid":message.uuid,"sender_uuid":sender.uuid,"sender_name":sender.email,"body":message.body,"created_at":message.created_at} for message,sender in messages]}


def accessible_thread(db,user,uuid):
    item=db.scalar(select(StaffMessageThread).join(StaffThreadParticipant).where(StaffMessageThread.uuid==uuid,StaffThreadParticipant.user_id==user.id))
    if not item:raise HTTPException(status_code=404,detail="Staff message thread not found")
    return item


@router.get("/staff-message-threads")
def list_staff_threads(db:Session=Depends(get_db),user:User=Depends(communication_user)):
    rows=list(db.scalars(select(StaffMessageThread).join(StaffThreadParticipant).where(StaffThreadParticipant.user_id==user.id).order_by(StaffMessageThread.updated_at.desc())));return [staff_thread_out(db,item) for item in rows]


@router.get("/staff-directory")
def staff_directory(db:Session=Depends(get_db),user:User=Depends(communication_user)):
    rows=list(db.scalars(select(User).where(User.active.is_(True)).order_by(User.email)));return [{"uuid":item.uuid,"email":item.email,"role":item.role} for item in rows]


@router.post("/staff-message-threads",status_code=201)
def create_staff_thread(body:StaffThreadCreate,db:Session=Depends(get_db),user:User=Depends(communication_write_user)):
    recipients=list(db.scalars(select(User).where(User.uuid.in_(set(body.participant_user_uuids)),User.active.is_(True))))
    if len(recipients)!=len(set(body.participant_user_uuids)):raise HTTPException(status_code=404,detail="One or more participants were not found")
    item=StaffMessageThread(subject=body.subject,created_by_id=user.id);db.add(item);db.flush();members={member.id:member for member in [user,*recipients]}
    db.add_all([StaffThreadParticipant(thread_id=item.id,user_id=member.id,role="owner" if member.id==user.id else "member",read_at=now() if member.id==user.id else None) for member in members.values()]);db.add(StaffMessage(thread_id=item.id,sender_user_id=user.id,body=body.body));db.add(AuditEvent(actor_id=user.id,action="create",resource_type="staff_message_thread",resource_id=item.uuid));db.commit();return staff_thread_out(db,item)


@router.get("/staff-message-threads/{thread_uuid}")
def get_staff_thread(thread_uuid:str,db:Session=Depends(get_db),user:User=Depends(communication_user)):
    item=accessible_thread(db,user,thread_uuid);participant=db.scalar(select(StaffThreadParticipant).where(StaffThreadParticipant.thread_id==item.id,StaffThreadParticipant.user_id==user.id));participant.read_at=now();db.commit();return staff_thread_out(db,item)


@router.post("/staff-message-threads/{thread_uuid}/replies")
def reply_staff_thread(thread_uuid:str,body:Reply,db:Session=Depends(get_db),user:User=Depends(communication_write_user)):
    item=accessible_thread(db,user,thread_uuid)
    if item.status!="open":raise HTTPException(status_code=409,detail="Staff message thread is closed")
    db.add(StaffMessage(thread_id=item.id,sender_user_id=user.id,body=body.body));item.updated_at=now();db.execute(update(StaffThreadParticipant).where(StaffThreadParticipant.thread_id==item.id,StaffThreadParticipant.user_id!=user.id).values(read_at=None));db.add(AuditEvent(actor_id=user.id,action="reply",resource_type="staff_message_thread",resource_id=item.uuid));db.commit();return staff_thread_out(db,item)


@router.post("/staff-message-threads/{thread_uuid}/close")
def close_staff_thread(thread_uuid:str,db:Session=Depends(get_db),user:User=Depends(communication_write_user)):
    item=accessible_thread(db,user,thread_uuid);item.status="closed";item.updated_at=now();db.add(AuditEvent(actor_id=user.id,action="close",resource_type="staff_message_thread",resource_id=item.uuid));db.commit();return staff_thread_out(db,item)


@router.post("/communications/outbox/process")
def run_outbox(limit:int=Query(default=100,ge=1,le=1000),db:Session=Depends(get_db),user:User=Depends(administration_user)):
    result=process_outbox(db,limit);db.add(AuditEvent(actor_id=user.id,action="process",resource_type="communication_outbox",detail=str(result)));db.commit();return result
