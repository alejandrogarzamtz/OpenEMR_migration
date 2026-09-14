from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Facility, User, UserFacilityAccess, Warehouse


def facility_scope(db: Session, user: User) -> set[int] | None:
    rows = set(db.scalars(select(UserFacilityAccess.facility_id).where(UserFacilityAccess.user_id == user.id)))
    return rows or None


def require_facility_access(db: Session, user: User, facility_id: int | None) -> None:
    scope = facility_scope(db, user)
    if scope is not None and facility_id not in scope:
        raise HTTPException(status_code=403, detail="Facility access denied")


def warehouse_scope(db: Session, user: User) -> set[str] | None:
    grants = list(db.scalars(select(UserFacilityAccess).where(UserFacilityAccess.user_id == user.id)))
    if not grants:
        return None
    result: set[str] = set()
    for grant in grants:
        if grant.warehouse_id:
            warehouse = db.get(Warehouse, grant.warehouse_id)
            if warehouse and warehouse.active:
                result.add(warehouse.code)
        else:
            result.update(db.scalars(select(Warehouse.code).where(Warehouse.facility_id == grant.facility_id, Warehouse.active.is_(True))))
    return result


def require_warehouse_access(db: Session, user: User, warehouse_code: str) -> None:
    scope = warehouse_scope(db, user)
    if scope is not None and warehouse_code not in scope:
        raise HTTPException(status_code=403, detail="Warehouse access denied")
