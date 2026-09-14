from urllib.parse import quote

from fastapi import APIRouter,Depends,HTTPException,Query,status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent,PatientEducationResource,User
from ..schemas import PatientEducationResourceCreate,PatientEducationResourceOut,PatientEducationSearchOut
from ..security import administration_user,administration_write_user,patient_demographics_user

router=APIRouter(prefix="/api/v1",tags=["patient-education"])

def resource(db:Session,resource_uuid:str)->PatientEducationResource:
    item=db.scalar(select(PatientEducationResource).where(PatientEducationResource.uuid==resource_uuid))
    if not item:raise HTTPException(404,"Patient education resource not found")
    return item

@router.get("/patient-education/resources",response_model=list[PatientEducationResourceOut])
def list_resources(db:Session=Depends(get_db),user:User=Depends(patient_demographics_user)):
    items=list(db.scalars(select(PatientEducationResource).where(PatientEducationResource.active.is_(True)).order_by(PatientEducationResource.sequence,PatientEducationResource.name)))
    db.add(AuditEvent(actor_id=user.id,action="search",resource_type="patient_education_resource",detail=f"records={len(items)}"));db.commit();return items

@router.get("/patient-education/resources/{resource_uuid}/search",response_model=PatientEducationSearchOut)
def education_search(resource_uuid:str,q:str=Query(min_length=1,max_length=500),db:Session=Depends(get_db),user:User=Depends(patient_demographics_user)):
    item=resource(db,resource_uuid)
    if not item.active:raise HTTPException(409,"Patient education resource is inactive")
    url=item.url_template.replace("[%]",quote(q,safe=""))
    db.add(AuditEvent(actor_id=user.id,action="search",resource_type="patient_education_lookup",resource_id=item.uuid,detail=f"query_length={len(q)}"));db.commit()
    return PatientEducationSearchOut(resource_uuid=item.uuid,resource_name=item.name,url=url)

@router.get("/admin/patient-education/resources",response_model=list[PatientEducationResourceOut])
def admin_resources(db:Session=Depends(get_db),user:User=Depends(administration_user)):
    del user;return list(db.scalars(select(PatientEducationResource).order_by(PatientEducationResource.sequence,PatientEducationResource.name)))

@router.post("/admin/patient-education/resources",response_model=PatientEducationResourceOut,status_code=status.HTTP_201_CREATED)
def create_resource(body:PatientEducationResourceCreate,db:Session=Depends(get_db),user:User=Depends(administration_write_user)):
    item=PatientEducationResource(**body.model_dump());db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="create",resource_type="patient_education_resource",resource_id=item.uuid));db.commit();db.refresh(item);return item

@router.patch("/admin/patient-education/resources/{resource_uuid}",response_model=PatientEducationResourceOut)
def update_resource(resource_uuid:str,body:PatientEducationResourceCreate,db:Session=Depends(get_db),user:User=Depends(administration_write_user)):
    item=resource(db,resource_uuid)
    for key,value in body.model_dump().items():setattr(item,key,value)
    db.add(AuditEvent(actor_id=user.id,action="update",resource_type="patient_education_resource",resource_id=item.uuid));db.commit();db.refresh(item);return item
