from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
import secrets
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..mfa import encrypt_secret
from ..models import AuditEvent, ExtensionPackage, IntegrationEvent, User, WebhookDelivery, WebhookSubscription
from ..security import administration_user, administration_write_user
from ..services.extensions import EVENT_NAME, process_webhook_deliveries, publish_event, validate_webhook_url

router = APIRouter(prefix="/api/v1", tags=["extensions"])
event_name = re.compile(EVENT_NAME)


class ExtensionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z][a-z0-9-]*$", max_length=120)
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$", max_length=50)
    api_version: str = Field(default="v1", pattern="^v1$")
    description: str | None = Field(default=None, max_length=1000)
    homepage_url: str | None = Field(default=None, max_length=1000)
    capabilities: list[str] = Field(default_factory=list, max_length=20)
    events: list[str] = Field(default_factory=list, max_length=100)
    @field_validator("capabilities")
    @classmethod
    def known_capabilities(cls, value):
        if any(item not in {"events:publish"} for item in value): raise ValueError("Unsupported extension capability")
        return sorted(set(value))
    @field_validator("events")
    @classmethod
    def valid_events(cls, value):
        if any(not event_name.fullmatch(item) for item in value): raise ValueError("Invalid event name")
        return sorted(set(value))
    @field_validator("homepage_url")
    @classmethod
    def valid_homepage(cls,value):
        if value is not None and (urlparse(value).scheme not in {"http","https"} or not urlparse(value).hostname):raise ValueError("Homepage must be an HTTP(S) URL")
        return value
    @model_validator(mode="after")
    def namespaced_events(self):
        prefix=f"extension.{self.key}."
        if any(not item.startswith(prefix) for item in self.events):raise ValueError(f"Declared events must use the {prefix} namespace")
        return self


class ExtensionState(BaseModel): status: str = Field(pattern="^(enabled|disabled)$")


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    endpoint_url: str = Field(max_length=1000)
    event_types: list[str] = Field(min_length=1, max_length=100)
    extension_uuid: str | None = None
    max_attempts: int = Field(default=8, ge=1, le=20)
    @field_validator("endpoint_url")
    @classmethod
    def secure_url(cls, value):
        try:return validate_webhook_url(value)
        except ValueError as exc:raise ValueError(str(exc)) from exc
    @field_validator("event_types")
    @classmethod
    def valid_types(cls, value):
        unique=sorted(set(value))
        if any(item!="*" and not (event_name.fullmatch(item) or item.endswith(".*") and event_name.fullmatch(item[:-2]+".event")) for item in unique):raise ValueError("Invalid event subscription pattern")
        return unique


class EventPublish(BaseModel):
    event_type: str = Field(max_length=160)
    resource_type: str | None = Field(default=None,max_length=80)
    resource_id: str | None = Field(default=None,max_length=100)
    data: dict = Field(default_factory=dict)


def extension_out(item:ExtensionPackage):
    return {key:getattr(item,key) for key in ("uuid","key","name","version","api_version","description","homepage_url","manifest","status","installed_at","updated_at","legacy_module_id")}


def subscription_out(item:WebhookSubscription,extension:ExtensionPackage|None=None):
    return {"uuid":item.uuid,"extension_uuid":extension.uuid if extension else None,"name":item.name,"endpoint_url":item.endpoint_url,"event_types":item.event_types,"active":item.active,"max_attempts":item.max_attempts,"created_at":item.created_at}


def issue_credential(item:ExtensionPackage)->str:
    raw=secrets.token_urlsafe(40);item.credential_hash=hashlib.sha256(raw.encode()).hexdigest();return f"ext.{item.uuid}.{raw}"


def current_extension(x_openrm_extension_key:str|None=Header(default=None),db:Session=Depends(get_db))->ExtensionPackage:
    if not x_openrm_extension_key:raise HTTPException(status_code=401,detail="Invalid extension credential")
    try:prefix,uuid,raw=x_openrm_extension_key.split(".",2)
    except ValueError:raise HTTPException(status_code=401,detail="Invalid extension credential")
    if prefix!="ext":raise HTTPException(status_code=401,detail="Invalid extension credential")
    item=db.scalar(select(ExtensionPackage).where(ExtensionPackage.uuid==uuid,ExtensionPackage.status=="enabled"))
    digest=hashlib.sha256(raw.encode()).hexdigest()
    if not item or not item.credential_hash or not hmac.compare_digest(item.credential_hash,digest):raise HTTPException(status_code=401,detail="Invalid extension credential")
    return item


@router.get("/extensions/sdk")
def sdk_contract():
    return {"api_version":"v1","authentication":{"header":"X-OpenRM-Extension-Key","format":"ext.{extension_uuid}.{secret}"},"event_envelope":{"id":"uuid","type":"namespaced.event","schema_version":"1","occurred_at":"RFC3339","resource":{"type":"optional","id":"optional"},"data":{}},"webhook_signature":{"algorithm":"HMAC-SHA256","headers":["OpenRM-Webhook-Id","OpenRM-Webhook-Timestamp","OpenRM-Webhook-Signature"],"signed_content":"{delivery_id}.{unix_timestamp}.{raw_body}"},"limits":{"event_body_bytes":65536}}


@router.get("/extensions/me")
def extension_identity(extension:ExtensionPackage=Depends(current_extension)):return extension_out(extension)


@router.post("/extensions/events",status_code=status.HTTP_202_ACCEPTED)
def publish_extension_event(body:EventPublish,db:Session=Depends(get_db),extension:ExtensionPackage=Depends(current_extension)):
    if "events:publish" not in extension.manifest.get("capabilities",[]):raise HTTPException(status_code=403,detail="Extension cannot publish events")
    prefix=f"extension.{extension.key}."
    if not body.event_type.startswith(prefix) or not event_name.fullmatch(body.event_type):raise HTTPException(status_code=422,detail=f"Event type must use the {prefix} namespace")
    if body.event_type not in extension.manifest.get("events",[]):raise HTTPException(status_code=403,detail="Event is not declared by the extension manifest")
    if len(json.dumps(body.data,ensure_ascii=False).encode())>65536:raise HTTPException(status_code=413,detail="Event data exceeds 64 KiB")
    item=publish_event(db,body.event_type,body.data,source_extension_id=extension.id,resource_type=body.resource_type,resource_id=body.resource_id);db.commit();return {"id":item.uuid,"accepted":True}


@router.get("/admin/extensions/overview")
def extension_overview(db:Session=Depends(get_db),actor:User=Depends(administration_user)):
    packages=list(db.scalars(select(ExtensionPackage).order_by(ExtensionPackage.name)));subscriptions=list(db.scalars(select(WebhookSubscription).order_by(WebhookSubscription.created_at.desc())));deliveries=list(db.scalars(select(WebhookDelivery).order_by(WebhookDelivery.id.desc()).limit(100)))
    return {"extensions":[extension_out(item) for item in packages],"subscriptions":[subscription_out(item,db.get(ExtensionPackage,item.extension_id) if item.extension_id else None) for item in subscriptions],"deliveries":[{"uuid":item.uuid,"subscription_uuid":db.get(WebhookSubscription,item.subscription_id).uuid,"event_type":db.get(IntegrationEvent,item.event_id).event_type,"status":item.status,"attempts":item.attempts,"next_attempt_at":item.next_attempt_at,"response_status":item.response_status,"error_message":item.error_message} for item in deliveries]}


@router.post("/admin/extensions",status_code=status.HTTP_201_CREATED)
def install_extension(body:ExtensionManifest,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    manifest=body.model_dump();item=ExtensionPackage(key=body.key,name=body.name,version=body.version,api_version=body.api_version,description=body.description,homepage_url=body.homepage_url,manifest=manifest,status="enabled",installed_by_id=actor.id);db.add(item)
    try:db.flush();credential=issue_credential(item)
    except IntegrityError:db.rollback();raise HTTPException(status_code=409,detail="Extension key already exists")
    db.add(AuditEvent(actor_id=actor.id,action="install",resource_type="extension",resource_id=item.uuid));db.commit();db.refresh(item);return {**extension_out(item),"credential":credential}


@router.put("/admin/extensions/{extension_uuid}")
def update_extension(extension_uuid:str,body:ExtensionManifest,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    item=db.scalar(select(ExtensionPackage).where(ExtensionPackage.uuid==extension_uuid))
    if not item:raise HTTPException(status_code=404,detail="Extension not found")
    if body.key!=item.key:raise HTTPException(status_code=422,detail="Extension key is immutable")
    item.name=body.name;item.version=body.version;item.api_version=body.api_version;item.description=body.description;item.homepage_url=body.homepage_url;item.manifest=body.model_dump();item.updated_at=datetime.now(timezone.utc)
    db.add(AuditEvent(actor_id=actor.id,action="update",resource_type="extension",resource_id=item.uuid,detail=f"version={body.version}"));db.commit();return extension_out(item)


@router.patch("/admin/extensions/{extension_uuid}")
def change_extension_state(extension_uuid:str,body:ExtensionState,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    item=db.scalar(select(ExtensionPackage).where(ExtensionPackage.uuid==extension_uuid));
    if not item:raise HTTPException(status_code=404,detail="Extension not found")
    item.status=body.status;item.updated_at=datetime.now(timezone.utc);db.add(AuditEvent(actor_id=actor.id,action=body.status,resource_type="extension",resource_id=item.uuid));db.commit();return extension_out(item)


@router.post("/admin/extensions/{extension_uuid}/rotate-credential")
def rotate_credential(extension_uuid:str,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    item=db.scalar(select(ExtensionPackage).where(ExtensionPackage.uuid==extension_uuid));
    if not item:raise HTTPException(status_code=404,detail="Extension not found")
    credential=issue_credential(item);db.add(AuditEvent(actor_id=actor.id,action="rotate-credential",resource_type="extension",resource_id=item.uuid));db.commit();return {"credential":credential}


@router.post("/admin/webhooks",status_code=status.HTTP_201_CREATED)
def create_subscription(body:SubscriptionCreate,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    extension=db.scalar(select(ExtensionPackage).where(ExtensionPackage.uuid==body.extension_uuid)) if body.extension_uuid else None
    if body.extension_uuid and not extension:raise HTTPException(status_code=404,detail="Extension not found")
    secret=secrets.token_urlsafe(40);item=WebhookSubscription(extension_id=extension.id if extension else None,name=body.name,endpoint_url=body.endpoint_url,event_types=body.event_types,encrypted_secret=encrypt_secret(secret),max_attempts=body.max_attempts,created_by_id=actor.id);db.add(item);db.flush();db.add(AuditEvent(actor_id=actor.id,action="create",resource_type="webhook_subscription",resource_id=item.uuid));db.commit();db.refresh(item);return {**subscription_out(item,extension),"secret":secret}


@router.patch("/admin/webhooks/{subscription_uuid}")
def set_subscription_state(subscription_uuid:str,active:bool,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    item=db.scalar(select(WebhookSubscription).where(WebhookSubscription.uuid==subscription_uuid));
    if not item:raise HTTPException(status_code=404,detail="Webhook subscription not found")
    item.active=active;db.add(AuditEvent(actor_id=actor.id,action="enable" if active else "disable",resource_type="webhook_subscription",resource_id=item.uuid));db.commit();return subscription_out(item,db.get(ExtensionPackage,item.extension_id) if item.extension_id else None)


@router.post("/admin/webhooks/{subscription_uuid}/rotate-secret")
def rotate_webhook_secret(subscription_uuid:str,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    item=db.scalar(select(WebhookSubscription).where(WebhookSubscription.uuid==subscription_uuid));
    if not item:raise HTTPException(status_code=404,detail="Webhook subscription not found")
    secret=secrets.token_urlsafe(40);item.encrypted_secret=encrypt_secret(secret);db.add(AuditEvent(actor_id=actor.id,action="rotate-secret",resource_type="webhook_subscription",resource_id=item.uuid));db.commit();return {"secret":secret}


@router.post("/admin/webhooks/process")
def process_webhooks(limit:int=Query(default=100,ge=1,le=1000),db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    result=process_webhook_deliveries(db,limit);db.add(AuditEvent(actor_id=actor.id,action="process",resource_type="webhook_delivery",detail=str(result)));db.commit();return result


@router.post("/admin/webhook-deliveries/{delivery_uuid}/replay")
def replay_delivery(delivery_uuid:str,db:Session=Depends(get_db),actor:User=Depends(administration_write_user)):
    item=db.scalar(select(WebhookDelivery).where(WebhookDelivery.uuid==delivery_uuid));
    if not item:raise HTTPException(status_code=404,detail="Webhook delivery not found")
    item.status="pending";item.attempts=0;item.next_attempt_at=datetime.now(timezone.utc);item.error_message=None;item.response_status=None;db.add(AuditEvent(actor_id=actor.id,action="replay",resource_type="webhook_delivery",resource_id=item.uuid));db.commit();return {"uuid":item.uuid,"status":item.status}
