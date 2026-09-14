from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import IpLoginTracker


def now_utc(): return datetime.now(timezone.utc)


def tracker(db: Session, ip: str, lock: bool = False) -> IpLoginTracker | None:
    query=select(IpLoginTracker).where(IpLoginTracker.ip_string==ip)
    if lock: query=query.with_for_update()
    return db.scalar(query)


def normalize(item: IpLoginTracker, now: datetime) -> None:
    last=item.last_failed_login
    if last and not last.tzinfo: last=last.replace(tzinfo=timezone.utc)
    if last and now-last>=timedelta(minutes=settings.ip_failure_window_minutes): item.applicable_failed_logins=0


def blocked(db: Session, ip: str) -> bool:
    item=tracker(db,ip,True)
    if not item: return False
    normalize(item,now_utc())
    return item.force_block or item.applicable_failed_logins>=settings.ip_max_failed_logins


def record_failure(db: Session, ip: str) -> IpLoginTracker:
    item=tracker(db,ip,True)
    if not item: item=IpLoginTracker(ip_string=ip);db.add(item);db.flush()
    current=now_utc();normalize(item,current)
    item.total_failed_logins+=1;item.applicable_failed_logins+=1;item.last_failed_login=current
    return item


def record_success(db: Session, ip: str) -> None:
    item=tracker(db,ip,True)
    if item: item.applicable_failed_logins=0
