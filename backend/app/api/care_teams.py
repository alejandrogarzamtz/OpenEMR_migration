from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, CareTeam, CareTeamMember, Facility, Practitioner, User
from ..schemas import CareTeamCreate, CareTeamMemberCreate, CareTeamMemberOut, CareTeamMemberUpdate, CareTeamOut, CareTeamUpdate
from ..security import clinical_user
from ..services.patients import patient_by_uuid

router=APIRouter(prefix="/api/v1/patients",tags=["care-teams"])


def team_for_patient(db:Session,patient_id:int,team_uuid:str,lock:bool=False)->CareTeam:
    query=select(CareTeam).where(CareTeam.uuid==team_uuid,CareTeam.patient_id==patient_id);item=db.scalar(query.with_for_update() if lock else query)
    if not item:raise HTTPException(status_code=404,detail="Care team not found")
    return item


def member_out(db:Session,item:CareTeamMember)->CareTeamMemberOut:
    practitioner=db.get(Practitioner,item.practitioner_id) if item.practitioner_id else None;facility=db.get(Facility,item.facility_id) if item.facility_id else None
    return CareTeamMemberOut(uuid=item.uuid,member_type=item.member_type,practitioner_uuid=practitioner.uuid if practitioner else None,facility_uuid=facility.uuid if facility else None,contact_name=item.display_name if item.member_type=="contact" else None,display_name=item.display_name,role=item.role,provider_since=item.provider_since,status=item.status,note=item.note,inactivated_reason=item.inactivated_reason,created_at=item.created_at,updated_at=item.updated_at)


def team_out(db:Session,item:CareTeam)->CareTeamOut:
    members=list(db.scalars(select(CareTeamMember).where(CareTeamMember.care_team_id==item.id).order_by(CareTeamMember.status, CareTeamMember.display_name)))
    return CareTeamOut(uuid=item.uuid,name=item.name,status=item.status,note=item.note,inactivated_reason=item.inactivated_reason,created_at=item.created_at,updated_at=item.updated_at,members=[member_out(db,member) for member in members])


@router.get("/{patient_uuid}/care-team-catalog")
def care_team_catalog(patient_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);practitioners=list(db.scalars(select(Practitioner).where(Practitioner.active.is_(True)).order_by(Practitioner.last_name,Practitioner.first_name)));facilities=list(db.scalars(select(Facility).where(Facility.active.is_(True)).order_by(Facility.name)))
    db.add(AuditEvent(actor_id=user.id,action="read",resource_type="care_team_catalog",resource_id=patient.uuid));db.commit()
    return {"practitioners":[{"uuid":item.uuid,"name":" ".join(filter(None,(item.first_name,item.last_name))),"specialty":item.specialty} for item in practitioners],"facilities":[{"uuid":item.uuid,"name":item.name} for item in facilities]}


@router.get("/{patient_uuid}/care-teams",response_model=list[CareTeamOut])
def list_teams(patient_uuid:str,include_inactive:bool=False,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);query=select(CareTeam).where(CareTeam.patient_id==patient.id)
    if not include_inactive:query=query.where(CareTeam.status.not_in(("inactive","entered-in-error")))
    teams=list(db.scalars(query.order_by(CareTeam.created_at.desc())));result=[team_out(db,item) for item in teams];db.add(AuditEvent(actor_id=user.id,action="search",resource_type="care_team",resource_id=patient.uuid,detail=f"records={len(result)}"));db.commit();return result


@router.post("/{patient_uuid}/care-teams",response_model=CareTeamOut,status_code=201)
def create_team(patient_uuid:str,body:CareTeamCreate,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    if body.status in {"inactive","entered-in-error"}:raise HTTPException(status_code=422,detail="Use reason-required inactivation for a terminal status")
    patient=patient_by_uuid(db,patient_uuid);item=CareTeam(patient_id=patient.id,created_by_id=user.id,updated_by_id=user.id,**body.model_dump());db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="create",resource_type="care_team",resource_id=item.uuid));db.commit();db.refresh(item);return team_out(db,item)


@router.put("/{patient_uuid}/care-teams/{team_uuid}",response_model=CareTeamOut)
def update_team(patient_uuid:str,team_uuid:str,body:CareTeamUpdate,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    if body.status in {"inactive","entered-in-error"}:raise HTTPException(status_code=422,detail="Use reason-required inactivation for a terminal status")
    patient=patient_by_uuid(db,patient_uuid);item=team_for_patient(db,patient.id,team_uuid,True)
    for key,value in body.model_dump().items():setattr(item,key,value)
    item.updated_by_id=user.id;item.updated_at=datetime.now(timezone.utc);db.add(AuditEvent(actor_id=user.id,action="update",resource_type="care_team",resource_id=item.uuid,detail=f"status={item.status}"));db.commit();db.refresh(item);return team_out(db,item)


@router.delete("/{patient_uuid}/care-teams/{team_uuid}",status_code=status.HTTP_204_NO_CONTENT)
def inactivate_team(patient_uuid:str,team_uuid:str,reason:str=Query(min_length=3,max_length=255),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);item=team_for_patient(db,patient.id,team_uuid,True)
    if item.status in {"inactive","entered-in-error"}:raise HTTPException(status_code=409,detail="Care team is already inactive")
    item.status="inactive";item.inactivated_reason=reason;item.updated_by_id=user.id;item.updated_at=datetime.now(timezone.utc);db.add(AuditEvent(actor_id=user.id,action="inactivate",resource_type="care_team",resource_id=item.uuid,detail=f"reason={reason}"));db.commit();return Response(status_code=204)


@router.post("/{patient_uuid}/care-teams/{team_uuid}/members",response_model=CareTeamMemberOut,status_code=201)
def add_member(patient_uuid:str,team_uuid:str,body:CareTeamMemberCreate,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);team=team_for_patient(db,patient.id,team_uuid,True);practitioner=db.scalar(select(Practitioner).where(Practitioner.uuid==body.practitioner_uuid,Practitioner.active.is_(True))) if body.practitioner_uuid else None;facility=db.scalar(select(Facility).where(Facility.uuid==body.facility_uuid,Facility.active.is_(True))) if body.facility_uuid else None
    if team.status in {"inactive","entered-in-error"}:raise HTTPException(status_code=409,detail="Inactive care teams cannot accept members")
    if body.status in {"inactive","entered-in-error"}:raise HTTPException(status_code=422,detail="Use reason-required inactivation for a terminal status")
    if body.practitioner_uuid and not practitioner:raise HTTPException(status_code=404,detail="Practitioner not found")
    if body.facility_uuid and not facility:raise HTTPException(status_code=404,detail="Facility not found")
    display=" ".join(filter(None,(practitioner.first_name,practitioner.last_name))) if practitioner else facility.name if body.member_type=="facility" and facility else (body.contact_name or "").strip()
    duplicate=db.scalar(select(CareTeamMember.id).where(CareTeamMember.care_team_id==team.id,CareTeamMember.member_type==body.member_type,CareTeamMember.practitioner_id==getattr(practitioner,"id",None),CareTeamMember.facility_id==getattr(facility,"id",None),CareTeamMember.display_name==display,CareTeamMember.status.not_in(("inactive","entered-in-error"))))
    if duplicate:raise HTTPException(status_code=409,detail="Care team member already exists")
    item=CareTeamMember(care_team_id=team.id,practitioner_id=practitioner.id if practitioner else None,facility_id=facility.id if facility else None,member_type=body.member_type,display_name=display,role=body.role,provider_since=body.provider_since,status=body.status,note=body.note,created_by_id=user.id,updated_by_id=user.id);db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="create",resource_type="care_team_member",resource_id=item.uuid,detail=f"team={team.uuid}; type={item.member_type}"));db.commit();db.refresh(item);return member_out(db,item)


@router.patch("/{patient_uuid}/care-teams/{team_uuid}/members/{member_uuid}",response_model=CareTeamMemberOut)
def update_member(patient_uuid:str,team_uuid:str,member_uuid:str,body:CareTeamMemberUpdate,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    if body.status in {"inactive","entered-in-error"}:raise HTTPException(status_code=422,detail="Use reason-required inactivation for a terminal status")
    patient=patient_by_uuid(db,patient_uuid);team=team_for_patient(db,patient.id,team_uuid,True);item=db.scalar(select(CareTeamMember).where(CareTeamMember.uuid==member_uuid,CareTeamMember.care_team_id==team.id).with_for_update())
    if not item:raise HTTPException(status_code=404,detail="Care team member not found")
    for key,value in body.model_dump().items():setattr(item,key,value)
    item.inactivated_reason=None if item.status not in {"inactive","entered-in-error"} else item.inactivated_reason;item.updated_by_id=user.id;item.updated_at=datetime.now(timezone.utc);db.add(AuditEvent(actor_id=user.id,action="update",resource_type="care_team_member",resource_id=item.uuid,detail=f"team={team.uuid}; status={item.status}"));db.commit();db.refresh(item);return member_out(db,item)


@router.delete("/{patient_uuid}/care-teams/{team_uuid}/members/{member_uuid}",status_code=status.HTTP_204_NO_CONTENT)
def inactivate_member(patient_uuid:str,team_uuid:str,member_uuid:str,reason:str=Query(min_length=3,max_length=255),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);team=team_for_patient(db,patient.id,team_uuid,True);item=db.scalar(select(CareTeamMember).where(CareTeamMember.uuid==member_uuid,CareTeamMember.care_team_id==team.id).with_for_update())
    if not item:raise HTTPException(status_code=404,detail="Care team member not found")
    if item.status in {"inactive","entered-in-error"}:raise HTTPException(status_code=409,detail="Care team member is already inactive")
    item.status="inactive";item.inactivated_reason=reason;item.updated_by_id=user.id;item.updated_at=datetime.now(timezone.utc);db.add(AuditEvent(actor_id=user.id,action="inactivate",resource_type="care_team_member",resource_id=item.uuid,detail=f"team={team.uuid}; reason={reason}"));db.commit();return Response(status_code=204)
