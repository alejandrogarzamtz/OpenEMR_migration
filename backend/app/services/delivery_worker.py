from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import CommunicationDelivery


def process_outbox(db:Session,limit:int=100)->dict:
    rows=list(db.scalars(select(CommunicationDelivery).where(CommunicationDelivery.status=="pending").order_by(CommunicationDelivery.queued_at).limit(limit)))
    result={"processed":0,"sent":0,"failed":0,"deferred":0}
    for item in rows:
        if settings.notification_delivery_mode=="disabled":result["deferred"]+=1;continue
        item.attempts+=1;result["processed"]+=1
        if settings.notification_delivery_mode=="test":item.status="sent";item.sent_at=datetime.now(timezone.utc);item.error_message=None;result["sent"]+=1
        else:item.status="failed";item.failed_at=datetime.now(timezone.utc);item.error_message="No delivery adapter configured";result["failed"]+=1
    db.commit();return result
