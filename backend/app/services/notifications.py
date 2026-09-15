from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CommunicationDelivery, NotificationPreference, Patient, PortalAccessGrant, PortalAccount, PortalNotification


def now_utc():return datetime.now(timezone.utc)


def preference_for(db:Session,account:PortalAccount,patient:Patient)->NotificationPreference:
    item=db.scalar(select(NotificationPreference).where(NotificationPreference.portal_account_id==account.id,NotificationPreference.patient_id==patient.id))
    if item:return item
    item=NotificationPreference(portal_account_id=account.id,patient_id=patient.id,email_enabled=bool(account.email and patient.allow_email),sms_enabled=False,in_app_enabled=True);db.add(item);db.flush();return item


def eligible_accounts(db:Session,patient:Patient,event_type:str)->list[tuple[PortalAccount,NotificationPreference]]:
    accounts=[];owner=db.scalar(select(PortalAccount).where(PortalAccount.patient_id==patient.id,PortalAccount.active.is_(True)))
    if owner:accounts.append(owner)
    now=now_utc();representatives=db.execute(select(PortalAccount,PortalAccessGrant).join(PortalAccessGrant,PortalAccessGrant.grantee_portal_account_id==PortalAccount.id).where(PortalAccessGrant.patient_id==patient.id,PortalAccessGrant.revoked_at.is_(None),PortalAccessGrant.starts_at<=now,(PortalAccessGrant.expires_at.is_(None)|(PortalAccessGrant.expires_at>now)),PortalAccount.active.is_(True))).all()
    accounts.extend(account for account,grant in representatives if "notifications" in grant.scopes)
    flag={"message":"message_events","appointment":"appointment_events","result":"result_events","questionnaire":"questionnaire_events"}.get(event_type)
    result=[]
    for account in {item.id:item for item in accounts}.values():
        preference=preference_for(db,account,patient)
        if flag is None or getattr(preference,flag):result.append((account,preference))
    return result


def notify_patient(db:Session,patient:Patient,event_type:str,title:str,body:str,action_url:str|None=None,message_id:int|None=None)->None:
    for account,preference in eligible_accounts(db,patient,event_type):
        if preference.in_app_enabled:db.add(PortalNotification(portal_account_id=account.id,patient_id=patient.id,event_type=event_type,title=title,body=body,action_url=action_url))
        if preference.email_enabled and account.email:db.add(CommunicationDelivery(patient_id=patient.id,message_id=message_id,channel="email",recipient=account.email,subject=title,body=body,template_name=f"portal-{event_type}"))
        if preference.sms_enabled and patient.phone:db.add(CommunicationDelivery(patient_id=patient.id,message_id=message_id,channel="sms",recipient=patient.phone,subject=title,body=body,template_name=f"portal-{event_type}"))
