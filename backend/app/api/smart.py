"""SMART App Launch 2.2 authorization for backend and interactive clients."""
import base64
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import AuditEvent, AuthSession, Encounter, Patient, PortalAccount, Practitioner, SmartAssertionReplay, SmartAuthorizationCode, SmartAuthorizationRequest, SmartClient, SmartLaunchContext, User
from ..schemas import SmartAuthorizationApproval, SmartClientCreate, SmartClientOut, SmartLaunchCreate
from ..security import administration_user, administration_write_user, authenticated_session, token_digest, user_has_permission
from ..services.portal_access import active_grants
from ..services.smart_oidc import encode_id_token, public_jwk

router=APIRouter(tags=["SMART on FHIR"]);bearer=HTTPBearer()
ASSERTION_TYPE="urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
SMART_RESOURCES={"Patient","Condition","AllergyIntolerance","MedicationStatement","Observation","Immunization","MedicationRequest","Coverage","DocumentReference","Binary","ServiceRequest","DiagnosticReport","Questionnaire","QuestionnaireResponse","RelatedPerson","Appointment","Encounter","CarePlan","Goal","CareTeam","Organization","Location","Practitioner","Person"}
PATIENT_RESOURCES=SMART_RESOURCES-{"Organization","Location","Practitioner","Questionnaire","Person"}
CONTEXT_SCOPES={"openid","fhirUser","profile","launch","launch/patient","launch/encounter"}
PKCE_RE=re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


def now()->datetime:return datetime.now(timezone.utc)
def aware(value:datetime)->datetime:return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def oauth_error(error:str,description:str,status_code:int=400):
    return JSONResponse(status_code=status_code,content={"error":error,"error_description":description},headers={"Cache-Control":"no-store","Pragma":"no-cache"})


def redirect_with(uri:str,**params)->str:
    parts=urlsplit(uri);query=parse_qsl(parts.query,keep_blank_values=True);query.extend((key,value) for key,value in params.items() if value is not None);return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query),parts.fragment))


def valid_url(value:str)->bool:
    try:parts=urlsplit(value)
    except ValueError:return False
    if parts.fragment or not parts.scheme or not parts.netloc or parts.username or parts.password:return False
    return parts.scheme=="https" or (parts.scheme=="http" and parts.hostname in {"localhost","127.0.0.1","::1"})


def split_data_scope(scope:str)->tuple[str,str,str]|None:
    if "/" not in scope or "." not in scope:return None
    context,tail=scope.split("/",1);resource,operations=tail.rsplit(".",1)
    if context not in {"system","user","patient"} or (resource!="*" and resource not in SMART_RESOURCES) or operations not in {"r","s","rs"}:return None
    if context=="patient" and resource not in PATIENT_RESOURCES and resource!="*":return None
    return context,resource,operations


def scope_covers(grant:str,requested:str)->bool:
    if grant==requested:return True
    granted=split_data_scope(grant);needed=split_data_scope(requested)
    return bool(granted and needed and granted[0]==needed[0] and granted[1] in {"*",needed[1]} and set(needed[2])<=set(granted[2]))


def validate_jwks(jwks:dict|None):
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


def validate_registration(body:SmartClientCreate):
    scopes=list(dict.fromkeys(body.allowed_scopes));launch_types=set(body.launch_types)
    if body.client_kind=="backend":
        validate_jwks(body.jwks)
        if body.redirect_uris or body.launch_uri or launch_types:raise HTTPException(status_code=422,detail="Backend clients cannot register interactive launch settings")
        if any(not (parts:=split_data_scope(scope)) or parts[0]!="system" for scope in scopes):raise HTTPException(status_code=422,detail="Backend clients support SMART system read/search scopes only")
        return
    if body.jwks:raise HTTPException(status_code=422,detail="Interactive public clients do not register private-key authentication material")
    if not body.redirect_uris or any(not valid_url(uri) for uri in body.redirect_uris):raise HTTPException(status_code=422,detail="Interactive clients require HTTPS redirect URIs; loopback HTTP is allowed")
    if not launch_types or not launch_types<={"standalone","ehr","patient"}:raise HTTPException(status_code=422,detail="Interactive clients require standalone, ehr, or patient launch types")
    if launch_types&{"ehr","patient"} and (not body.launch_uri or not valid_url(body.launch_uri)):raise HTTPException(status_code=422,detail="EHR and patient launches require a valid launch URI")
    if any(scope not in CONTEXT_SCOPES and (not (parts:=split_data_scope(scope)) or parts[0] not in {"user","patient"}) for scope in scopes):raise HTTPException(status_code=422,detail="Interactive clients support user/patient read/search and launch identity scopes only")


def out(client:SmartClient)->SmartClientOut:
    keys=("uuid","client_id","name","client_kind","redirect_uris","launch_uri","launch_types","allowed_scopes","active","created_at");return SmartClientOut(**{key:getattr(client,key) for key in keys})


@router.get("/fhir/.well-known/smart-configuration")
def smart_configuration():
    base=settings.api_public_url.rstrip("/");issuer=f"{base}/fhir";supported=[*[f"system/{resource}.rs" for resource in sorted(SMART_RESOURCES)],*[f"user/{resource}.rs" for resource in sorted(SMART_RESOURCES)],*[f"patient/{resource}.rs" for resource in sorted(PATIENT_RESOURCES)],*sorted(CONTEXT_SCOPES)]
    return {"issuer":issuer,"authorization_endpoint":f"{base}/oauth2/default/authorize","token_endpoint":f"{base}/oauth2/default/token","revocation_endpoint":f"{base}/oauth2/default/revoke","introspection_endpoint":f"{base}/oauth2/default/introspect","jwks_uri":f"{base}/oauth2/default/jwks","token_endpoint_auth_methods_supported":["none","private_key_jwt"],"grant_types_supported":["authorization_code","client_credentials"],"response_types_supported":["code"],"code_challenge_methods_supported":["S256"],"scopes_supported":supported,"capabilities":["launch-ehr","launch-standalone","client-public","client-confidential-asymmetric","sso-openid-connect","context-ehr-patient","context-ehr-encounter","context-standalone-patient","permission-patient","permission-user","permission-v2"]}


@router.get("/.well-known/openid-configuration/fhir")
@router.get("/fhir/.well-known/openid-configuration")
def oidc_configuration():
    base=settings.api_public_url.rstrip("/");issuer=f"{base}/fhir"
    return {"issuer":issuer,"authorization_endpoint":f"{base}/oauth2/default/authorize","token_endpoint":f"{base}/oauth2/default/token","jwks_uri":f"{base}/oauth2/default/jwks","response_types_supported":["code"],"subject_types_supported":["public"],"id_token_signing_alg_values_supported":["RS256"],"scopes_supported":["openid","fhirUser","profile"],"claims_supported":["sub","aud","iss","exp","iat","auth_time","nonce","fhirUser","patient","name","email"]}


@router.get("/oauth2/default/jwks")
def oidc_jwks():return {"keys":[public_jwk()]}


@router.post("/api/v1/admin/smart-clients",response_model=SmartClientOut,status_code=status.HTTP_201_CREATED)
def register_client(body:SmartClientCreate,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    validate_registration(body);client_id=body.client_id or str(uuid4())
    if db.scalar(select(SmartClient.id).where(SmartClient.client_id==client_id)):raise HTTPException(status_code=409,detail="SMART client_id already exists")
    item=SmartClient(client_id=client_id,name=body.name,client_kind=body.client_kind,jwks=body.jwks,redirect_uris=list(dict.fromkeys(body.redirect_uris)),launch_uri=body.launch_uri,launch_types=sorted(set(body.launch_types)),allowed_scopes=sorted(set(body.allowed_scopes)),owner_user_id=actor.id);db.add(item);db.flush();db.add(AuditEvent(actor_id=actor.id,action="create",resource_type="smart_client",resource_id=item.uuid,detail=f"{client_id}:{body.client_kind}"));db.commit();db.refresh(item);return out(item)


@router.get("/api/v1/admin/smart-clients",response_model=list[SmartClientOut])
def list_clients(db:Session=Depends(get_db),actor:User=Depends(administration_user)):
    items=list(db.scalars(select(SmartClient).order_by(SmartClient.name,SmartClient.client_id)));db.add(AuditEvent(actor_id=actor.id,action="search",resource_type="smart_client"));db.commit();return [out(item) for item in items]


@router.delete("/api/v1/admin/smart-clients/{client_uuid}",status_code=204)
def revoke_client(client_uuid:str,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    item=db.scalar(select(SmartClient).where(SmartClient.uuid==client_uuid))
    if not item:raise HTTPException(status_code=404,detail="SMART client not found")
    current=now();item.active=False;item.revoked_at=current
    for session in db.scalars(select(AuthSession).where(AuthSession.smart_client_id==item.id,AuthSession.revoked_at.is_(None))):session.revoked_at=current;session.revoke_reason="client-revoked"
    db.add(AuditEvent(actor_id=actor.id,action="revoke",resource_type="smart_client",resource_id=item.uuid));db.commit()


def interactive_identity(credentials:HTTPAuthorizationCredentials=Depends(bearer),db:Session=Depends(get_db)):
    try:kind=jwt.decode(credentials.credentials,options={"verify_signature":False}).get("kind")
    except jwt.PyJWTError:raise HTTPException(status_code=401,detail="Invalid credentials")
    if kind not in {"staff","portal"}:raise HTTPException(status_code=401,detail="Invalid credentials")
    session,_=authenticated_session(credentials,db,kind)
    if session.smart_client_id is not None:raise HTTPException(status_code=403,detail="A SMART token cannot approve another authorization")
    identity=db.get(User,session.user_id) if kind=="staff" else db.get(PortalAccount,session.portal_account_id)
    if not identity or not identity.active or (kind=="portal" and identity.force_password_reset):raise HTTPException(status_code=401,detail="Inactive identity")
    return kind,identity,session


def authorization_request(db:Session,raw:str,lock:bool=False)->SmartAuthorizationRequest:
    query=select(SmartAuthorizationRequest).where(SmartAuthorizationRequest.request_hash==token_digest(raw));item=db.scalar(query.with_for_update() if lock else query)
    if not item or item.consumed_at is not None or aware(item.expires_at)<=now():raise HTTPException(status_code=404,detail="Authorization request is invalid or expired")
    return item


@router.get("/oauth2/default/authorize")
def authorize(response_type:str,client_id:str,redirect_uri:str,scope:str,state:str,aud:str,code_challenge:str,code_challenge_method:str,nonce:str|None=None,launch:str|None=None,db:Session=Depends(get_db)):
    client=db.scalar(select(SmartClient).where(SmartClient.client_id==client_id,SmartClient.client_kind=="interactive",SmartClient.active.is_(True),SmartClient.revoked_at.is_(None)))
    if not client or redirect_uri not in client.redirect_uris:return oauth_error("invalid_request","Unknown client or redirect URI")
    if response_type!="code":return RedirectResponse(redirect_with(redirect_uri,error="unsupported_response_type",state=state),status_code=303)
    requested=list(dict.fromkeys(scope.split()));base=settings.api_public_url.rstrip("/");invalid=not requested or any(not any(scope_covers(grant,item) for grant in client.allowed_scopes) for item in requested)
    invalid_identity_scope=bool({"fhirUser","profile"}&set(requested)) and "openid" not in requested
    if invalid or invalid_identity_scope or aud!=f"{base}/fhir" or code_challenge_method!="S256" or not PKCE_RE.fullmatch(code_challenge) or ("openid" in requested and not nonce):return RedirectResponse(redirect_with(redirect_uri,error="invalid_request",error_description="Invalid scopes, audience, nonce, or PKCE challenge",state=state),status_code=303)
    launch_context=None
    if launch:
        launch_context=db.scalar(select(SmartLaunchContext).where(SmartLaunchContext.token_hash==token_digest(launch),SmartLaunchContext.smart_client_id==client.id).with_for_update());expected="ehr" if launch_context and launch_context.identity_kind=="staff" else "patient"
        if not launch_context or launch_context.consumed_at is not None or aware(launch_context.expires_at)<=now() or expected not in client.launch_types or "launch" not in requested:return RedirectResponse(redirect_with(redirect_uri,error="invalid_request",error_description="Launch context is invalid or expired",state=state),status_code=303)
        launch_context.consumed_at=now()
    elif "standalone" not in client.launch_types or "launch" in requested:return RedirectResponse(redirect_with(redirect_uri,error="invalid_request",error_description="Launch context is required",state=state),status_code=303)
    raw=secrets.token_urlsafe(48);item=SmartAuthorizationRequest(request_hash=token_digest(raw),smart_client_id=client.id,launch_context_id=launch_context.id if launch_context else None,redirect_uri=redirect_uri,scopes=requested,state=state,audience=aud,nonce=nonce,code_challenge=code_challenge,expires_at=now()+timedelta(minutes=5));db.add(item);db.commit();return RedirectResponse(f"{settings.public_web_url.rstrip('/')}/smart/authorize?request={raw}",status_code=303,headers={"Cache-Control":"no-store","Pragma":"no-cache"})


@router.get("/oauth2/default/authorize/requests/{request_token}")
def authorization_details(request_token:str,db:Session=Depends(get_db)):
    item=authorization_request(db,request_token);client=db.get(SmartClient,item.smart_client_id);launch=db.get(SmartLaunchContext,item.launch_context_id) if item.launch_context_id else None
    return {"client_name":client.name,"client_id":client.client_id,"scopes":item.scopes,"identity_kind":launch.identity_kind if launch else None,"patient_context_required":"launch/patient" in item.scopes or any(scope.startswith("patient/") for scope in item.scopes),"expires_at":item.expires_at}


def portal_patients(db:Session,account:PortalAccount)->list[Patient]:
    rows=[]
    if account.patient_id:
        patient=db.get(Patient,account.patient_id)
        if patient and patient.portal_allowed and patient.merged_into_id is None:rows.append(patient)
    rows.extend(patient for _,patient in active_grants(db,account) if patient.portal_allowed and patient.merged_into_id is None);return list({item.id:item for item in rows}.values())


@router.get("/oauth2/default/authorize/requests/{request_token}/context")
def authorization_context(request_token:str,identity=Depends(interactive_identity),db:Session=Depends(get_db)):
    item=authorization_request(db,request_token);kind,actor,_=identity;launch=db.get(SmartLaunchContext,item.launch_context_id) if item.launch_context_id else None
    if launch and launch.identity_kind!=kind:raise HTTPException(status_code=403,detail="This launch requires a different identity type")
    if kind=="portal" and any(scope.startswith("user/") for scope in item.scopes):raise HTTPException(status_code=403,detail="Patient identities cannot authorize user scopes")
    if kind=="staff":
        if not user_has_permission(actor,"patients","demo"):raise HTTPException(status_code=403,detail="Patient access is not permitted")
        patients=list(db.scalars(select(Patient).where(Patient.merged_into_id.is_(None)).order_by(Patient.last_name,Patient.first_name).limit(100)))
    else:patients=portal_patients(db,actor)
    if launch and launch.patient_id:patients=[patient for patient in patients if patient.id==launch.patient_id]
    return {"identity_kind":kind,"patients":[{"uuid":patient.uuid,"name":f"{patient.first_name} {patient.last_name}"} for patient in patients],"fixed_patient":bool(launch and launch.patient_id)}


def practitioner_for_user(db:Session,user:User)->Practitioner|None:
    conditions=[]
    if user.legacy_user_id is not None:conditions.append(Practitioner.legacy_user_id==user.legacy_user_id)
    if user.username:conditions.append(Practitioner.username==user.username)
    conditions.append(Practitioner.email==user.email);return db.scalar(select(Practitioner).where(or_(*conditions),Practitioner.active.is_(True)))


@router.post("/oauth2/default/authorize/requests/{request_token}/approve")
def approve_authorization(request_token:str,body:SmartAuthorizationApproval,identity=Depends(interactive_identity),db:Session=Depends(get_db)):
    item=authorization_request(db,request_token,True);client=db.get(SmartClient,item.smart_client_id);kind,actor,_=identity;launch=db.get(SmartLaunchContext,item.launch_context_id) if item.launch_context_id else None
    if launch and launch.identity_kind!=kind:raise HTTPException(status_code=403,detail="This launch requires a different identity type")
    if kind=="portal" and any(scope.startswith("user/") for scope in item.scopes):raise HTTPException(status_code=403,detail="Patient identities cannot authorize user scopes")
    candidates=list(db.scalars(select(Patient).where(Patient.merged_into_id.is_(None)))) if kind=="staff" else portal_patients(db,actor);allowed={patient.uuid:patient for patient in candidates};patient=db.get(Patient,launch.patient_id) if launch and launch.patient_id else allowed.get(body.patient_uuid or "");needs_patient="launch/patient" in item.scopes or any(scope.startswith("patient/") for scope in item.scopes) or (kind=="portal" and "fhirUser" in item.scopes)
    if needs_patient and (not patient or patient.uuid not in allowed):raise HTTPException(status_code=422,detail="An authorized patient context is required")
    if "fhirUser" in item.scopes and kind=="staff" and not practitioner_for_user(db,actor):raise HTTPException(status_code=422,detail="The staff identity is not linked to an active Practitioner")
    raw_code=secrets.token_urlsafe(48);code=SmartAuthorizationCode(code_hash=token_digest(raw_code),smart_client_id=client.id,authorization_request_id=item.id,user_id=actor.id if kind=="staff" else None,portal_account_id=actor.id if kind=="portal" else None,patient_id=patient.id if patient else None,encounter_id=launch.encounter_id if launch else None,redirect_uri=item.redirect_uri,scopes=item.scopes,nonce=item.nonce,code_challenge=item.code_challenge,expires_at=now()+timedelta(minutes=5));db.add(code);item.consumed_at=now();db.add(AuditEvent(actor_id=actor.id if kind=="staff" else client.owner_user_id,action="authorize",resource_type="smart_client",resource_id=client.uuid,detail=" ".join(item.scopes)));db.commit();return {"redirect_to":redirect_with(item.redirect_uri,code=raw_code,state=item.state)}


@router.post("/oauth2/default/authorize/requests/{request_token}/deny")
def deny_authorization(request_token:str,identity=Depends(interactive_identity),db:Session=Depends(get_db)):
    item=authorization_request(db,request_token,True);item.consumed_at=now();db.commit();return {"redirect_to":redirect_with(item.redirect_uri,error="access_denied",state=item.state)}


@router.post("/api/v1/smart/launches")
def create_launch(body:SmartLaunchCreate,identity=Depends(interactive_identity),db:Session=Depends(get_db)):
    kind,actor,_=identity
    if body.identity_kind!=kind:raise HTTPException(status_code=403,detail="Launch identity does not match the authenticated identity")
    client=db.scalar(select(SmartClient).where(SmartClient.client_id==body.client_id,SmartClient.client_kind=="interactive",SmartClient.active.is_(True)));launch_type="ehr" if kind=="staff" else "patient"
    if not client or launch_type not in client.launch_types or not client.launch_uri:raise HTTPException(status_code=404,detail="Compatible SMART client not found")
    patients=list(db.scalars(select(Patient).where(Patient.merged_into_id.is_(None)))) if kind=="staff" else portal_patients(db,actor);allowed={item.uuid:item for item in patients};patient=allowed.get(body.patient_uuid or "")
    if body.patient_uuid and not patient:raise HTTPException(status_code=403,detail="Patient context is not authorized")
    encounter=db.scalar(select(Encounter).where(Encounter.uuid==body.encounter_uuid,Encounter.patient_id==patient.id)) if body.encounter_uuid and patient else None
    if body.encounter_uuid and not encounter:raise HTTPException(status_code=422,detail="Encounter does not belong to the launch patient")
    raw=secrets.token_urlsafe(48);item=SmartLaunchContext(token_hash=token_digest(raw),smart_client_id=client.id,identity_kind=kind,patient_id=patient.id if patient else None,encounter_id=encounter.id if encounter else None,created_by_user_id=actor.id if kind=="staff" else None,created_by_portal_account_id=actor.id if kind=="portal" else None,expires_at=now()+timedelta(minutes=5));db.add(item);db.commit();iss=f"{settings.api_public_url.rstrip('/')}/fhir";return {"launch":raw,"iss":iss,"launch_url":redirect_with(client.launch_uri,iss=iss,launch=raw)}


def authenticate_backend_client(db:Session,client_assertion_type:str|None,assertion:str|None)->SmartClient|None:
    if client_assertion_type!=ASSERTION_TYPE or not assertion:return None
    try:
        header=jwt.get_unverified_header(assertion);unverified=jwt.decode(assertion,options={"verify_signature":False});client_id=unverified.get("iss");client=db.scalar(select(SmartClient).where(SmartClient.client_id==client_id,SmartClient.client_kind=="backend",SmartClient.active.is_(True),SmartClient.revoked_at.is_(None)))
        if not client or unverified.get("sub")!=client_id:return None
        key_data=next((key for key in (client.jwks or {}).get("keys",[]) if key.get("kid")==header.get("kid")),None);alg=header.get("alg")
        if not key_data or alg not in {"RS384","ES384"} or key_data.get("alg") not in {None,alg}:return None
        payload=jwt.decode(assertion,jwt.PyJWK.from_dict(key_data).key,algorithms=[alg],audience=f"{settings.api_public_url.rstrip('/')}/oauth2/default/token",options={"require":["iss","sub","aud","iat","exp","jti"]});expires=datetime.fromtimestamp(payload["exp"],timezone.utc)
        if expires>now()+timedelta(minutes=5) or db.scalar(select(SmartAssertionReplay.id).where(SmartAssertionReplay.smart_client_id==client.id,SmartAssertionReplay.jti==str(payload["jti"]))):return None
        db.add(SmartAssertionReplay(smart_client_id=client.id,jti=str(payload["jti"]),expires_at=expires));db.flush();return client
    except (jwt.PyJWTError,KeyError,TypeError,ValueError):return None


def issue_access_token(db:Session,client:SmartClient,scopes:list[str],user_id:int,portal_account_id:int|None=None,patient_id:int|None=None,encounter_id:int|None=None,token_use:str="smart_interactive"):
    current=now();expires=current+timedelta(minutes=min(settings.access_token_minutes,5));session=AuthSession(identity_kind="staff",user_id=user_id,portal_account_id=portal_account_id,smart_client_id=client.id,smart_scopes=scopes,smart_patient_id=patient_id,smart_encounter_id=encounter_id,access_jti=str(uuid4()),refresh_token_hash=token_digest(secrets.token_urlsafe(48)),refresh_expires_at=expires);db.add(session);db.flush();claims={"sub":str(user_id),"kind":"staff","jti":session.access_jti,"sid":session.uuid,"iss":settings.jwt_issuer,"aud":settings.jwt_audience,"iat":current,"nbf":current,"exp":expires,"client_id":client.client_id,"scope":" ".join(scopes),"token_use":token_use,**({"patient_id":patient_id} if patient_id else {})};return jwt.encode(claims,settings.jwt_secret.get_secret_value(),algorithm="HS256"),session,current,expires


@router.post("/oauth2/default/token")
def token(grant_type:str=Form(),scope:str|None=Form(default=None),client_id:str|None=Form(default=None),code:str|None=Form(default=None),redirect_uri:str|None=Form(default=None),code_verifier:str|None=Form(default=None),client_assertion_type:str|None=Form(default=None),client_assertion:str|None=Form(default=None),db:Session=Depends(get_db)):
    if grant_type=="client_credentials":
        client=authenticate_backend_client(db,client_assertion_type,client_assertion)
        if not client:db.rollback();return oauth_error("invalid_client","Client assertion is invalid",401)
        requested=list(dict.fromkeys((scope or "").split()))
        if not requested or any(not (parts:=split_data_scope(item)) or parts[0]!="system" or not any(scope_covers(grant,item) for grant in client.allowed_scopes) for item in requested):db.commit();return oauth_error("invalid_scope","Requested scope exceeds the client registration")
        access,_,current,expires=issue_access_token(db,client,requested,client.owner_user_id,token_use="smart_backend");db.add(AuditEvent(actor_id=client.owner_user_id,action="token",resource_type="smart_client",resource_id=client.uuid,detail=" ".join(requested)));db.commit();return JSONResponse(content={"access_token":access,"token_type":"Bearer","expires_in":int((expires-current).total_seconds()),"scope":" ".join(requested)},headers={"Cache-Control":"no-store","Pragma":"no-cache"})
    if grant_type!="authorization_code":return oauth_error("unsupported_grant_type","Supported grants are authorization_code and client_credentials")
    if not all((client_id,code,redirect_uri,code_verifier)) or not PKCE_RE.fullmatch(code_verifier):return oauth_error("invalid_request","Code, client_id, redirect_uri, and PKCE verifier are required")
    client=db.scalar(select(SmartClient).where(SmartClient.client_id==client_id,SmartClient.client_kind=="interactive",SmartClient.active.is_(True)));auth_code=db.scalar(select(SmartAuthorizationCode).where(SmartAuthorizationCode.code_hash==token_digest(code)).with_for_update());challenge=base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
    if not client or not auth_code or auth_code.smart_client_id!=client.id or auth_code.redirect_uri!=redirect_uri or auth_code.consumed_at is not None or aware(auth_code.expires_at)<=now() or not secrets.compare_digest(challenge,auth_code.code_challenge):db.rollback();return oauth_error("invalid_grant","Authorization code is invalid, expired, or already used")
    auth_code.consumed_at=now();user_id=auth_code.user_id or client.owner_user_id;access,_,current,expires=issue_access_token(db,client,auth_code.scopes,user_id,auth_code.portal_account_id,auth_code.patient_id,auth_code.encounter_id);response={"access_token":access,"token_type":"Bearer","expires_in":int((expires-current).total_seconds()),"scope":" ".join(auth_code.scopes)};patient=db.get(Patient,auth_code.patient_id) if auth_code.patient_id else None
    if patient:response["patient"]=patient.uuid
    encounter=db.get(Encounter,auth_code.encounter_id) if auth_code.encounter_id else None
    if encounter:response["encounter"]=encounter.uuid
    if "openid" in auth_code.scopes:
        if auth_code.portal_account_id:
            portal=db.get(PortalAccount,auth_code.portal_account_id);fhir_user=f"{settings.api_public_url.rstrip('/')}/fhir/Patient/{patient.uuid}" if patient else None;subject=f"portal:{portal.uuid}";profile_claims={"name":portal.display_name or portal.username,**({"email":portal.email} if portal.email else {})}
        else:
            user=db.get(User,auth_code.user_id);practitioner=practitioner_for_user(db,user);fhir_user=f"{settings.api_public_url.rstrip('/')}/fhir/Practitioner/{practitioner.uuid}" if practitioner else None;subject=f"staff:{user.uuid}";profile_claims={"name":user.email,"email":user.email}
        claims={"iss":f"{settings.api_public_url.rstrip('/')}/fhir","sub":subject,"aud":client.client_id,"iat":current,"exp":expires,"auth_time":int(current.timestamp()),**({"nonce":auth_code.nonce} if auth_code.nonce else {}),**({"fhirUser":fhir_user} if fhir_user and "fhirUser" in auth_code.scopes else {}),**(profile_claims if "profile" in auth_code.scopes else {}),**({"patient":patient.uuid} if patient else {})};response["id_token"]=encode_id_token(claims)
    db.add(AuditEvent(actor_id=user_id,action="token",resource_type="smart_client",resource_id=client.uuid,detail=" ".join(auth_code.scopes)));db.commit();return JSONResponse(content=response,headers={"Cache-Control":"no-store","Pragma":"no-cache"})


def token_client(db:Session,token_value:str,client_id:str|None,client_assertion_type:str|None,client_assertion:str|None):
    backend=authenticate_backend_client(db,client_assertion_type,client_assertion)
    try:payload=jwt.decode(token_value,settings.jwt_secret.get_secret_value(),algorithms=["HS256"],audience=settings.jwt_audience,issuer=settings.jwt_issuer);session=db.scalar(select(AuthSession).where(AuthSession.uuid==payload.get("sid")));client=db.get(SmartClient,session.smart_client_id) if session else None
    except jwt.PyJWTError:return None,None,{}
    if not client or (backend and backend.id!=client.id) or (not backend and (client.client_kind!="interactive" or client.client_id!=client_id)):return None,None,{}
    return client,session,payload


@router.post("/oauth2/default/revoke",status_code=200)
def revoke_token(token_value:str=Form(alias="token"),client_id:str|None=Form(default=None),client_assertion_type:str|None=Form(default=None),client_assertion:str|None=Form(default=None),db:Session=Depends(get_db)):
    client,session,_=token_client(db,token_value,client_id,client_assertion_type,client_assertion)
    if not client:db.rollback();return oauth_error("invalid_client","Client authentication is invalid",401)
    if session and session.revoked_at is None:session.revoked_at=now();session.revoke_reason="oauth-revocation"
    db.commit();return JSONResponse(content={},headers={"Cache-Control":"no-store","Pragma":"no-cache"})


@router.post("/oauth2/default/introspect")
def introspect_token(token_value:str=Form(alias="token"),client_assertion_type:str=Form(),client_assertion:str=Form(),db:Session=Depends(get_db)):
    client,session,payload=token_client(db,token_value,None,client_assertion_type,client_assertion)
    if not client:db.rollback();return oauth_error("invalid_client","Client assertion is invalid",401)
    db.commit()
    if not session or session.revoked_at is not None:return {"active":False}
    return {"active":True,"client_id":client.client_id,"scope":" ".join(session.smart_scopes or []),"token_type":"Bearer","exp":payload.get("exp"),"sub":payload.get("sub")}
