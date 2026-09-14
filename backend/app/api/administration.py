from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, Facility, IpLoginTracker, Practitioner, User, UserFacilityAccess, Warehouse
from ..schemas import FacilityCreate, FacilityOut, IpTrackerUpdate, PractitionerCreate, PractitionerOut, UserFacilityAccessCreate, UserFacilityAccessOut, WarehouseCreate, WarehouseOut
from ..security import administration_user, administration_write_user

router = APIRouter(prefix="/api/v1/admin", tags=["administration"])


@router.patch("/ip-trackers/{tracker_id}")
def update_ip_tracker(tracker_id:int,body:IpTrackerUpdate,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    item=db.get(IpLoginTracker,tracker_id)
    if not item:raise HTTPException(status_code=404,detail="IP tracker not found")
    if body.force_block is not None:item.force_block=body.force_block
    if body.skip_timing_protection is not None:item.skip_timing_protection=body.skip_timing_protection
    if body.reset_applicable_failures:item.applicable_failed_logins=0;item.last_failed_login=None
    db.add(AuditEvent(actor_id=actor.id,action="update",resource_type="ip_tracker",resource_id=str(item.id),detail=f"ip={item.ip_string}"));db.commit()
    return {"id":item.id,"ip_address":item.ip_string,"force_block":item.force_block,"skip_timing_protection":item.skip_timing_protection,"applicable_failed_logins":item.applicable_failed_logins}


def facility_by_uuid(db: Session, value: str) -> Facility:
    item = db.scalar(select(Facility).where(Facility.uuid == value))
    if not item:
        raise HTTPException(status_code=404, detail="Facility not found")
    return item


def warehouse_out(db: Session, item: Warehouse) -> WarehouseOut:
    facility = db.get(Facility, item.facility_id) if item.facility_id else None
    return WarehouseOut(facility_uuid=facility.uuid if facility else None, **{key:getattr(item,key) for key in ("uuid","code","name","sequence","active")})


def practitioner_out(db: Session, item: Practitioner) -> PractitionerOut:
    facility = db.get(Facility, item.primary_facility_id) if item.primary_facility_id else None
    return PractitionerOut(primary_facility_uuid=facility.uuid if facility else None, **{key:getattr(item,key) for key in ("uuid","username","first_name","middle_name","last_name","title","specialty","npi","taxonomy","email","phone","calendar_enabled","active")})


@router.get("/facilities", response_model=list[FacilityOut])
def list_facilities(include_inactive: bool = False, db: Session = Depends(get_db), user: User = Depends(administration_user)):
    query = select(Facility)
    if not include_inactive: query = query.where(Facility.active.is_(True))
    rows=list(db.scalars(query.order_by(Facility.name))); db.add(AuditEvent(actor_id=user.id,action="search",resource_type="facility")); db.commit(); return rows


@router.post("/facilities", response_model=FacilityOut, status_code=status.HTTP_201_CREATED)
def create_facility(body: FacilityCreate, db: Session = Depends(get_db), user: User = Depends(administration_write_user)):
    item=Facility(**body.model_dump()); db.add(item); db.flush(); db.add(AuditEvent(actor_id=user.id,action="create",resource_type="facility",resource_id=item.uuid)); db.commit(); db.refresh(item); return item


@router.patch("/facilities/{facility_uuid}", response_model=FacilityOut)
def update_facility(facility_uuid: str, body: FacilityCreate, db: Session = Depends(get_db), user: User = Depends(administration_write_user)):
    item=facility_by_uuid(db,facility_uuid)
    for key,value in body.model_dump().items(): setattr(item,key,value)
    db.add(AuditEvent(actor_id=user.id,action="update",resource_type="facility",resource_id=item.uuid)); db.commit(); db.refresh(item); return item


@router.get("/warehouses", response_model=list[WarehouseOut])
def list_warehouses(db: Session = Depends(get_db), user: User = Depends(administration_user)):
    rows=list(db.scalars(select(Warehouse).order_by(Warehouse.sequence,Warehouse.name))); db.add(AuditEvent(actor_id=user.id,action="search",resource_type="warehouse")); db.commit(); return [warehouse_out(db,item) for item in rows]


@router.post("/warehouses", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
def create_warehouse(body: WarehouseCreate, db: Session = Depends(get_db), user: User = Depends(administration_write_user)):
    facility=facility_by_uuid(db,body.facility_uuid) if body.facility_uuid else None; item=Warehouse(facility_id=facility.id if facility else None,**body.model_dump(exclude={"facility_uuid"})); db.add(item)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(status_code=409,detail="Warehouse code already exists")
    db.add(AuditEvent(actor_id=user.id,action="create",resource_type="warehouse",resource_id=item.uuid)); db.commit(); db.refresh(item); return warehouse_out(db,item)


@router.get("/practitioners", response_model=list[PractitionerOut])
def list_practitioners(db: Session = Depends(get_db), user: User = Depends(administration_user)):
    rows=list(db.scalars(select(Practitioner).order_by(Practitioner.last_name,Practitioner.first_name))); db.add(AuditEvent(actor_id=user.id,action="search",resource_type="practitioner")); db.commit(); return [practitioner_out(db,item) for item in rows]


@router.post("/practitioners", response_model=PractitionerOut, status_code=status.HTTP_201_CREATED)
def create_practitioner(body: PractitionerCreate, db: Session = Depends(get_db), user: User = Depends(administration_write_user)):
    facility=facility_by_uuid(db,body.primary_facility_uuid) if body.primary_facility_uuid else None; item=Practitioner(primary_facility_id=facility.id if facility else None,**body.model_dump(exclude={"primary_facility_uuid"})); db.add(item); db.flush(); db.add(AuditEvent(actor_id=user.id,action="create",resource_type="practitioner",resource_id=item.uuid)); db.commit(); db.refresh(item); return practitioner_out(db,item)


@router.get("/users/{user_uuid}/facility-access", response_model=list[UserFacilityAccessOut])
def list_access(user_uuid: str, db: Session = Depends(get_db), actor: User = Depends(administration_user)):
    target=db.scalar(select(User).where(User.uuid==user_uuid))
    if not target: raise HTTPException(status_code=404,detail="User not found")
    rows=db.execute(select(UserFacilityAccess,Facility,Warehouse).join(Facility,UserFacilityAccess.facility_id==Facility.id).outerjoin(Warehouse,UserFacilityAccess.warehouse_id==Warehouse.id).where(UserFacilityAccess.user_id==target.id)).all()
    db.add(AuditEvent(actor_id=actor.id,action="read",resource_type="user_facility_access",resource_id=target.uuid)); db.commit(); return [UserFacilityAccessOut(uuid=item.uuid,facility_uuid=facility.uuid,facility_name=facility.name,warehouse_uuid=warehouse.uuid if warehouse else None,warehouse_name=warehouse.name if warehouse else None) for item,facility,warehouse in rows]


@router.post("/users/{user_uuid}/facility-access", response_model=UserFacilityAccessOut, status_code=status.HTTP_201_CREATED)
def grant_access(user_uuid: str, body: UserFacilityAccessCreate, db: Session = Depends(get_db), actor: User = Depends(administration_write_user)):
    target=db.scalar(select(User).where(User.uuid==user_uuid)); facility=facility_by_uuid(db,body.facility_uuid)
    if not target: raise HTTPException(status_code=404,detail="User not found")
    warehouse=db.scalar(select(Warehouse).where(Warehouse.uuid==body.warehouse_uuid,Warehouse.facility_id==facility.id)) if body.warehouse_uuid else None
    if body.warehouse_uuid and not warehouse: raise HTTPException(status_code=404,detail="Warehouse not found for facility")
    item=UserFacilityAccess(user_id=target.id,facility_id=facility.id,warehouse_id=warehouse.id if warehouse else None); db.add(item)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(status_code=409,detail="Access already granted")
    db.add(AuditEvent(actor_id=actor.id,action="grant",resource_type="user_facility_access",resource_id=target.uuid)); db.commit(); db.refresh(item); return UserFacilityAccessOut(uuid=item.uuid,facility_uuid=facility.uuid,facility_name=facility.name,warehouse_uuid=warehouse.uuid if warehouse else None,warehouse_name=warehouse.name if warehouse else None)
