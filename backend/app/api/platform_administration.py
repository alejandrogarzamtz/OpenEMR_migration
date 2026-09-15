from datetime import datetime, timedelta, timezone
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings as runtime_settings
from ..db import get_db
from ..models import AuditEvent, AuthSession, CommunicationDelivery, ContentTemplate, LocaleCatalog, PasswordResetToken, SystemSetting, Translation, User
from ..security import administration_user, administration_write_user, password_hash, token_digest
from ..services.content_templates import render_template, validate_template
from ..services.platform_administration import setting_value, touch_setting, validate_setting

router = APIRouter(prefix="/api/v1", tags=["platform-administration"])
PERMISSION_PATTERN = re.compile(r"^(?:\*|[a-z][a-z0-9_-]*):(?:\*|[a-z][a-z0-9_-]*):(?:\*|[a-z][a-z0-9_-]*)$")
ROLES = {"admin", "billing", "clinician", "receptionist"}


class SettingUpdate(BaseModel):
    value: object


class LocaleCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$", max_length=16)
    name: str = Field(min_length=1, max_length=100)
    rtl: bool = False
    active: bool = True


class LocaleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    rtl: bool | None = None
    active: bool | None = None


class TranslationUpdate(BaseModel):
    value: str = Field(max_length=10000)


class TemplateBody(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9.-]*$", max_length=120)
    locale_code: str = Field(default="en", max_length=16)
    name: str = Field(min_length=1, max_length=255)
    category: str
    subject: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1, max_length=1_000_000)
    content_type: str = "text/plain"
    allowed_variables: list[str] = Field(default_factory=list, max_length=100)


class TemplatePreview(BaseModel):
    variables: dict[str, object] = Field(default_factory=dict)


class UserInvite(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    username: str | None = Field(default=None, min_length=1, max_length=255)
    role: str = "clinician"
    permissions: list[str] = Field(default_factory=list, max_length=100)


class UserUpdate(BaseModel):
    role: str | None = None
    active: bool | None = None
    permissions: list[str] | None = Field(default=None, max_length=100)


def locale_out(item: LocaleCatalog) -> dict:
    return {"uuid": item.uuid, "code": item.code, "name": item.name, "rtl": item.rtl, "active": item.active}


def template_out(item: ContentTemplate) -> dict:
    return {key: getattr(item, key) for key in ("uuid", "key", "locale_code", "version", "name", "category", "subject", "content", "content_type", "allowed_variables", "active", "created_at")}


def user_out(item: User) -> dict:
    return {"uuid": item.uuid, "username": item.username, "email": item.email, "role": item.role, "active": item.active, "permissions": item.permissions}


@router.get("/localization/bootstrap")
def localization_bootstrap(locale: str | None = Query(default=None, max_length=16), db: Session = Depends(get_db)):
    default_locale = str(setting_value(db, "localization.default_locale"))
    requested = locale or default_locale
    selected = db.scalar(select(LocaleCatalog).where(LocaleCatalog.code == requested, LocaleCatalog.active.is_(True)))
    if not selected:
        selected = db.scalar(select(LocaleCatalog).where(LocaleCatalog.code == default_locale, LocaleCatalog.active.is_(True)))
    if not selected:
        raise HTTPException(status_code=503, detail="No active locale is configured")
    translations = {item.key: item.value for item in db.scalars(select(Translation).where(Translation.locale_id == selected.id))}
    locales = list(db.scalars(select(LocaleCatalog).where(LocaleCatalog.active.is_(True)).order_by(LocaleCatalog.name)))
    return {"organization_name": setting_value(db, "organization.name"), "default_locale": default_locale, "locale": locale_out(selected), "locales": [locale_out(item) for item in locales], "translations": translations}


@router.get("/admin/settings")
def list_settings(db: Session = Depends(get_db), actor: User = Depends(administration_user)):
    rows = list(db.scalars(select(SystemSetting).order_by(SystemSetting.category, SystemSetting.key)))
    db.add(AuditEvent(actor_id=actor.id, action="search", resource_type="system_setting")); db.commit()
    return [{key: getattr(item, key) for key in ("uuid", "key", "category", "value_type", "value", "description", "version", "updated_at")} for item in rows]


@router.put("/admin/settings/{key}")
def update_setting(key: str, body: SettingUpdate, db: Session = Depends(get_db), actor: User = Depends(administration_write_user)):
    item = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if not item:
        raise HTTPException(status_code=404, detail="Setting is not managed by OpenRM")
    try:
        value = validate_setting(db, key, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    touch_setting(item, actor.id, value)
    db.add(AuditEvent(actor_id=actor.id, action="update", resource_type="system_setting", resource_id=item.uuid, detail=f"key={key};version={item.version}")); db.commit(); db.refresh(item)
    return {key: getattr(item, key) for key in ("uuid", "key", "category", "value_type", "value", "description", "version", "updated_at")}


@router.get("/admin/locales")
def list_locales(db: Session = Depends(get_db), actor: User = Depends(administration_user)):
    return [locale_out(item) for item in db.scalars(select(LocaleCatalog).order_by(LocaleCatalog.name))]


@router.post("/admin/locales", status_code=status.HTTP_201_CREATED)
def create_locale(body: LocaleCreate, db: Session = Depends(get_db), actor: User = Depends(administration_write_user)):
    item = LocaleCatalog(**body.model_dump()); db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback(); raise HTTPException(status_code=409, detail="Locale code already exists")
    db.add(AuditEvent(actor_id=actor.id, action="create", resource_type="locale", resource_id=item.uuid)); db.commit(); db.refresh(item); return locale_out(item)


@router.patch("/admin/locales/{code}")
def update_locale(code: str, body: LocaleUpdate, db: Session = Depends(get_db), actor: User = Depends(administration_write_user)):
    item = db.scalar(select(LocaleCatalog).where(LocaleCatalog.code == code))
    if not item: raise HTTPException(status_code=404, detail="Locale not found")
    if body.active is False and setting_value(db, "localization.default_locale") == code:
        raise HTTPException(status_code=409, detail="The default locale cannot be disabled")
    for key, value in body.model_dump(exclude_unset=True).items(): setattr(item, key, value)
    db.add(AuditEvent(actor_id=actor.id, action="update", resource_type="locale", resource_id=item.uuid)); db.commit(); db.refresh(item); return locale_out(item)


@router.get("/admin/locales/{code}/translations")
def list_translations(code: str, db: Session = Depends(get_db), actor: User = Depends(administration_user)):
    locale = db.scalar(select(LocaleCatalog).where(LocaleCatalog.code == code))
    if not locale: raise HTTPException(status_code=404, detail="Locale not found")
    return [{"uuid": item.uuid, "key": item.key, "value": item.value, "customized": item.customized, "updated_at": item.updated_at} for item in db.scalars(select(Translation).where(Translation.locale_id == locale.id).order_by(Translation.key))]


@router.put("/admin/locales/{code}/translations/{translation_key:path}")
def put_translation(code: str, translation_key: str, body: TranslationUpdate, db: Session = Depends(get_db), actor: User = Depends(administration_write_user)):
    locale = db.scalar(select(LocaleCatalog).where(LocaleCatalog.code == code))
    if not locale: raise HTTPException(status_code=404, detail="Locale not found")
    item = db.scalar(select(Translation).where(Translation.locale_id == locale.id, Translation.key == translation_key))
    if not item: item = Translation(locale_id=locale.id, key=translation_key, value=body.value, customized=True, updated_by_id=actor.id); db.add(item)
    else: item.value = body.value; item.customized = True; item.updated_by_id = actor.id; item.updated_at = datetime.now(timezone.utc)
    db.flush(); db.add(AuditEvent(actor_id=actor.id, action="update", resource_type="translation", resource_id=item.uuid, detail=f"locale={code};key={translation_key}")); db.commit(); db.refresh(item)
    return {"uuid": item.uuid, "key": item.key, "value": item.value, "customized": item.customized, "updated_at": item.updated_at}


@router.get("/admin/templates")
def list_templates(include_inactive: bool = False, db: Session = Depends(get_db), actor: User = Depends(administration_user)):
    query = select(ContentTemplate)
    if not include_inactive: query = query.where(ContentTemplate.active.is_(True))
    return [template_out(item) for item in db.scalars(query.order_by(ContentTemplate.key, ContentTemplate.locale_code, ContentTemplate.version.desc()))]


def checked_template(db: Session, body: TemplateBody) -> list[str]:
    if not db.scalar(select(LocaleCatalog).where(LocaleCatalog.code == body.locale_code, LocaleCatalog.active.is_(True))):
        raise HTTPException(status_code=422, detail="Template locale must be active")
    try: return validate_template(body.subject, body.content, body.content_type, body.category, body.allowed_variables)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/admin/templates", status_code=status.HTTP_201_CREATED)
def create_template(body: TemplateBody, db: Session = Depends(get_db), actor: User = Depends(administration_write_user)):
    allowed = checked_template(db, body)
    if db.scalar(select(ContentTemplate).where(ContentTemplate.key == body.key, ContentTemplate.locale_code == body.locale_code)):
        raise HTTPException(status_code=409, detail="Template already exists; create a new version through update")
    item = ContentTemplate(**body.model_dump(exclude={"allowed_variables"}), allowed_variables=allowed, created_by_id=actor.id); db.add(item); db.flush()
    db.add(AuditEvent(actor_id=actor.id, action="create", resource_type="content_template", resource_id=item.uuid)); db.commit(); db.refresh(item); return template_out(item)


@router.put("/admin/templates/{template_uuid}")
def version_template(template_uuid: str, body: TemplateBody, db: Session = Depends(get_db), actor: User = Depends(administration_write_user)):
    current = db.scalar(select(ContentTemplate).where(ContentTemplate.uuid == template_uuid))
    if not current: raise HTTPException(status_code=404, detail="Template not found")
    if body.key != current.key or body.locale_code != current.locale_code:
        raise HTTPException(status_code=409, detail="Template key and locale cannot change between versions")
    allowed = checked_template(db, body)
    latest = db.scalar(select(func.max(ContentTemplate.version)).where(ContentTemplate.key == current.key, ContentTemplate.locale_code == current.locale_code)) or current.version
    current.active = False
    item = ContentTemplate(**body.model_dump(exclude={"allowed_variables"}), allowed_variables=allowed, version=latest + 1, supersedes_id=current.id, created_by_id=actor.id); db.add(item); db.flush()
    db.add(AuditEvent(actor_id=actor.id, action="version", resource_type="content_template", resource_id=item.uuid, detail=f"supersedes={current.uuid}")); db.commit(); db.refresh(item); return template_out(item)


@router.post("/admin/templates/{template_uuid}/preview")
def preview_template(template_uuid: str, body: TemplatePreview, db: Session = Depends(get_db), actor: User = Depends(administration_user)):
    item = db.scalar(select(ContentTemplate).where(ContentTemplate.uuid == template_uuid))
    if not item: raise HTTPException(status_code=404, detail="Template not found")
    try: subject, content = render_template(item.subject, item.content, item.content_type, item.allowed_variables, body.variables)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"subject": subject, "content": content, "content_type": item.content_type}


@router.get("/admin/users")
def list_users(db: Session = Depends(get_db), actor: User = Depends(administration_user)):
    return [user_out(item) for item in db.scalars(select(User).order_by(User.email))]


def validate_access(role: str, permissions: list[str]) -> list[str]:
    if role not in ROLES: raise HTTPException(status_code=422, detail="Unsupported user role")
    grants = sorted(set(permissions))
    if any(not PERMISSION_PATTERN.fullmatch(item) for item in grants): raise HTTPException(status_code=422, detail="Invalid permission grant")
    return grants


@router.post("/admin/users/invitations", status_code=status.HTTP_201_CREATED)
def invite_user(body: UserInvite, db: Session = Depends(get_db), actor: User = Depends(administration_write_user)):
    email = body.email.strip().lower()
    if "@" not in email: raise HTTPException(status_code=422, detail="Invalid email address")
    grants = validate_access(body.role, body.permissions)
    user = User(email=email, username=body.username, password_hash=password_hash.hash(secrets.token_urlsafe(48)), role=body.role, permissions=grants, active=True); db.add(user)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(status_code=409, detail="Email or username already exists")
    raw_token = secrets.token_urlsafe(48); now = datetime.now(timezone.utc)
    db.add(PasswordResetToken(user_id=user.id, token_hash=token_digest(raw_token), expires_at=now + timedelta(minutes=runtime_settings.password_reset_minutes)))
    db.add(CommunicationDelivery(channel="email", recipient=user.email, subject="Your OpenRM account", body=f"Set your password using this one-time link: {runtime_settings.public_web_url.rstrip('/')}/reset-password?token={raw_token}", template_name="staff-invitation"))
    db.add(AuditEvent(actor_id=actor.id, action="invite", resource_type="user", resource_id=user.uuid)); db.commit(); db.refresh(user); return user_out(user)


@router.patch("/admin/users/{user_uuid}")
def update_user(user_uuid: str, body: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(administration_write_user)):
    target = db.scalar(select(User).where(User.uuid == user_uuid))
    if not target: raise HTTPException(status_code=404, detail="User not found")
    role = body.role if body.role is not None else target.role
    grants = validate_access(role, body.permissions if body.permissions is not None else target.permissions)
    removing_admin = target.active and target.role == "admin" and (body.active is False or role != "admin")
    if removing_admin and (db.scalar(select(func.count(User.id)).where(User.active.is_(True), User.role == "admin")) or 0) <= 1:
        raise HTTPException(status_code=409, detail="The last active administrator cannot be disabled or demoted")
    if target.id == actor.id and body.active is False: raise HTTPException(status_code=409, detail="You cannot disable your own account")
    target.role = role; target.permissions = grants
    if body.active is not None: target.active = body.active
    if body.active is False:
        now = datetime.now(timezone.utc)
        for session in db.scalars(select(AuthSession).where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None))): session.revoked_at = now; session.revoke_reason = "account-disabled"
    db.add(AuditEvent(actor_id=actor.id, action="update", resource_type="user", resource_id=target.uuid)); db.commit(); db.refresh(target); return user_out(target)
