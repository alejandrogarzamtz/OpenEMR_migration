"""SMART App Launch 2.2 Backend Services authorization surface."""
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import AuditEvent, AuthSession, SmartAssertionReplay, SmartClient, User
from ..schemas import SmartClientCreate, SmartClientOut
from ..security import administration_user, administration_write_user, token_digest

router=APIRouter(tags=["SMART on FHIR"])
ASSERTION_TYPE="urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
SMART_RESOURCES={"Patient","Condition","AllergyIntolerance","MedicationStatement","Observation","Immunization","MedicationRequest","Coverage","DocumentReference","Binary","ServiceRequest","DiagnosticReport","Questionnaire","QuestionnaireResponse","RelatedPerson","Appointment","Encounter","CarePlan","Goal","CareTeam","Organization","Location","Practitioner","Person"}


def oauth_error(error:str,description:str,status_code:int=400):
    return JSONResponse(status_code=status_code,content={"error":error,"error_description":description},headers={"Cache-Control":"no-store","Pragma":"no-cache"})


def valid_scope(scope:str)->bool:
    if not scope.startswith("system/") or "." not in scope:return False
    resource,operations=scope[7:].rsplit(".",1)
    return (resource=="*" or resource in SMART_RESOURCES) and operations in {"r","s","rs"}


def covers(grant:str,request:str)->bool:
    granted_resource,granted_ops=grant[7:].rsplit(".",1);requested_resource,requested_ops=request[7:].rsplit(".",1)
    return granted_resource in {"*",requested_resource} and set(requested_ops)<=set(granted_ops)


def validate_jwks(jwks:dict):
    keys=jwks.get("keys") if isinstance(jwks,dict) else None
    if not isinstance(keys,list) or not keys:raise HTTPException(status_code=422,detail="jwks.keys must contain at least one public key")
    kids=set()
    for key in keys:
        if not isinstance(key,dict) or key.get("kty") not in {"RSA","EC"} or not key.get("kid"):raise HTTPException(status_code=422,detail="Each JWK requires kty RSA/EC and a kid")
        if set(key)&{"d","p","q","dp","dq","qi","oth"}:raise HTTPException(status_code=422,detail="JWKS registration accepts public keys only")
        if key["kid"] in kids:raise HTTPException(status_code=422,detail="JWK kid values must be unique")
        if key.get("alg") not in {None,"RS384","ES384"}:raise HTTPException(status_code=422,detail="JWK alg must be RS384 or ES384")
        try:jwt.PyJWK.from_dict(key)
        except Exception as exc:raise HTTPException(status_code=422,detail="Invalid public JWK") from exc
        kids.add(key["kid"])


def out(client:SmartClient)->SmartClientOut:
    return SmartClientOut(**{key:getattr(client,key) for key in ("uuid","client_id","name","allowed_scopes","active","created_at")})


@router.get("/fhir/.well-known/smart-configuration")
def smart_configuration():
    base=settings.api_public_url.rstrip("/")
    return {"issuer":f"{base}/fhir","token_endpoint":f"{base}/oauth2/default/token","revocation_endpoint":f"{base}/oauth2/default/revoke","introspection_endpoint":f"{base}/oauth2/default/introspect","token_endpoint_auth_methods_supported":["private_key_jwt"],"scopes_supported":["system/*.rs",*[f"system/{resource}.rs" for resource in sorted(SMART_RESOURCES)]],"capabilities":["client-confidential-asymmetric","permission-v2"]}


@router.post("/api/v1/admin/smart-clients",response_model=SmartClientOut,status_code=status.HTTP_201_CREATED)
def register_client(body:SmartClientCreate,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    validate_jwks(body.jwks)
    if any(not valid_scope(scope) for scope in body.allowed_scopes):raise HTTPException(status_code=422,detail="Only valid SMART system read/search scopes are supported")
    client_id=body.client_id or str(uuid4())
    if db.scalar(select(SmartClient.id).where(SmartClient.client_id==client_id)):raise HTTPException(status_code=409,detail="SMART client_id already exists")
    item=SmartClient(client_id=client_id,name=body.name,jwks=body.jwks,allowed_scopes=sorted(set(body.allowed_scopes)),owner_user_id=actor.id);db.add(item);db.flush();db.add(AuditEvent(actor_id=actor.id,action="create",resource_type="smart_client",resource_id=item.uuid,detail=client_id));db.commit();db.refresh(item);return out(item)


@router.get("/api/v1/admin/smart-clients",response_model=list[SmartClientOut])
def list_clients(db:Session=Depends(get_db),actor:User=Depends(administration_user)):
    items=list(db.scalars(select(SmartClient).order_by(SmartClient.name,SmartClient.client_id)));db.add(AuditEvent(actor_id=actor.id,action="search",resource_type="smart_client"));db.commit();return [out(item) for item in items]


@router.delete("/api/v1/admin/smart-clients/{client_uuid}",status_code=204)
def revoke_client(client_uuid:str,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    item=db.scalar(select(SmartClient).where(SmartClient.uuid==client_uuid))
    if not item:raise HTTPException(status_code=404,detail="SMART client not found")
    now=datetime.now(timezone.utc);item.active=False;item.revoked_at=now
    for session in db.scalars(select(AuthSession).where(AuthSession.smart_client_id==item.id,AuthSession.revoked_at.is_(None))):session.revoked_at=now;session.revoke_reason="client-revoked"
    db.add(AuditEvent(actor_id=actor.id,action="revoke",resource_type="smart_client",resource_id=item.uuid));db.commit()


def authenticate_client(db:Session,client_assertion_type:str,assertion:str)->tuple[SmartClient,dict]|None:
    if client_assertion_type!=ASSERTION_TYPE:return None
    try:
        header=jwt.get_unverified_header(assertion);unverified=jwt.decode(assertion,options={"verify_signature":False});client_id=unverified.get("iss")
        client=db.scalar(select(SmartClient).where(SmartClient.client_id==client_id,SmartClient.active.is_(True),SmartClient.revoked_at.is_(None)))
        if not client or unverified.get("sub")!=client_id:return None
        key_data=next((key for key in client.jwks["keys"] if key.get("kid")==header.get("kid")),None);alg=header.get("alg")
        if not key_data or alg not in {"RS384","ES384"} or key_data.get("alg") not in {None,alg}:return None
        payload=jwt.decode(assertion,jwt.PyJWK.from_dict(key_data).key,algorithms=[alg],audience=f"{settings.api_public_url.rstrip('/')}/oauth2/default/token",options={"require":["iss","sub","aud","iat","exp","jti"]})
        exp=datetime.fromtimestamp(payload["exp"],timezone.utc)
        if exp>datetime.now(timezone.utc)+timedelta(minutes=5) or db.scalar(select(SmartAssertionReplay.id).where(SmartAssertionReplay.smart_client_id==client.id,SmartAssertionReplay.jti==str(payload["jti"]))):return None
        db.add(SmartAssertionReplay(smart_client_id=client.id,jti=str(payload["jti"]),expires_at=exp));db.flush();return client,payload
    except (jwt.PyJWTError,KeyError,StopIteration,TypeError,ValueError):return None


@router.post("/oauth2/default/token")
def token(grant_type:str=Form(),scope:str=Form(),client_assertion_type:str=Form(),client_assertion:str=Form(),db:Session=Depends(get_db)):
    if grant_type!="client_credentials":return oauth_error("unsupported_grant_type","Only client_credentials is supported")
    authenticated=authenticate_client(db,client_assertion_type,client_assertion)
    if not authenticated:db.rollback();return oauth_error("invalid_client","Client assertion is invalid",401)
    client,_=authenticated;requested=list(dict.fromkeys(scope.split()))
    if not requested or any(not valid_scope(item) or not any(covers(grant,item) for grant in client.allowed_scopes) for item in requested):db.commit();return oauth_error("invalid_scope","Requested scope exceeds the client registration")
    now=datetime.now(timezone.utc);expires=now+timedelta(minutes=min(settings.access_token_minutes,5));session=AuthSession(identity_kind="staff",user_id=client.owner_user_id,smart_client_id=client.id,smart_scopes=requested,access_jti=str(uuid4()),refresh_token_hash=token_digest(secrets.token_urlsafe(48)),refresh_expires_at=expires);db.add(session);db.flush()
    claims={"sub":str(client.owner_user_id),"kind":"staff","jti":session.access_jti,"sid":session.uuid,"iss":settings.jwt_issuer,"aud":settings.jwt_audience,"iat":now,"nbf":now,"exp":expires,"client_id":client.client_id,"scope":" ".join(requested),"token_use":"smart_backend"};access_token=jwt.encode(claims,settings.jwt_secret.get_secret_value(),algorithm="HS256")
    db.add(AuditEvent(actor_id=client.owner_user_id,action="token",resource_type="smart_client",resource_id=client.uuid,detail=" ".join(requested)));db.commit();return JSONResponse(content={"access_token":access_token,"token_type":"Bearer","expires_in":int((expires-now).total_seconds()),"scope":" ".join(requested)},headers={"Cache-Control":"no-store","Pragma":"no-cache"})


@router.post("/oauth2/default/revoke",status_code=200)
def revoke_token(token_value:str=Form(alias="token"),client_assertion_type:str=Form(),client_assertion:str=Form(),db:Session=Depends(get_db)):
    authenticated=authenticate_client(db,client_assertion_type,client_assertion)
    if not authenticated:db.rollback();return oauth_error("invalid_client","Client assertion is invalid",401)
    client,_=authenticated
    try:payload=jwt.decode(token_value,settings.jwt_secret.get_secret_value(),algorithms=["HS256"],audience=settings.jwt_audience,issuer=settings.jwt_issuer);session=db.scalar(select(AuthSession).where(AuthSession.uuid==payload.get("sid"),AuthSession.smart_client_id==client.id))
    except jwt.PyJWTError:session=None
    if session and session.revoked_at is None:session.revoked_at=datetime.now(timezone.utc);session.revoke_reason="oauth-revocation"
    db.commit();return {}


@router.post("/oauth2/default/introspect")
def introspect_token(token_value:str=Form(alias="token"),client_assertion_type:str=Form(),client_assertion:str=Form(),db:Session=Depends(get_db)):
    authenticated=authenticate_client(db,client_assertion_type,client_assertion)
    if not authenticated:db.rollback();return oauth_error("invalid_client","Client assertion is invalid",401)
    client,_=authenticated
    try:
        payload=jwt.decode(token_value,settings.jwt_secret.get_secret_value(),algorithms=["HS256"],audience=settings.jwt_audience,issuer=settings.jwt_issuer);session=db.scalar(select(AuthSession).where(AuthSession.uuid==payload.get("sid"),AuthSession.smart_client_id==client.id,AuthSession.revoked_at.is_(None)))
    except jwt.PyJWTError:session=None;payload={}
    db.commit()
    if not session:return {"active":False}
    return {"active":True,"client_id":client.client_id,"scope":" ".join(session.smart_scopes or []),"token_type":"Bearer","exp":payload.get("exp"),"sub":payload.get("sub")}
