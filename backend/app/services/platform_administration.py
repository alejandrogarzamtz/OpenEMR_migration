from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LocaleCatalog, SystemSetting, Translation


SETTING_DEFINITIONS = {
    "organization.name": ("organization", "string", "OpenRM", "Name shown in the application"),
    "organization.timezone": ("organization", "timezone", "UTC", "Default IANA timezone"),
    "localization.default_locale": ("localization", "locale", "en", "Default interface locale"),
    "localization.date_format": ("localization", "choice", "YYYY-MM-DD", "Default display date format"),
    "ui.default_page_size": ("interface", "integer", 50, "Default number of rows per page"),
}

DATE_FORMATS = {"YYYY-MM-DD", "MM/DD/YYYY", "DD/MM/YYYY"}

CORE_TRANSLATIONS = {
    "en": {
        "nav.patients": "Patients", "nav.appointments": "Appointments", "nav.flow": "Patient flow",
        "nav.inventory": "Inventory", "nav.messages": "Messages", "nav.education": "Education",
        "nav.reports": "Reports", "nav.administration": "Administration", "nav.security": "Security",
        "action.logout": "Sign out", "action.new_patient": "New patient", "header.clinical_care": "CLINICAL CARE",
    },
    "es": {
        "nav.patients": "Pacientes", "nav.appointments": "Agenda", "nav.flow": "Flujo de pacientes",
        "nav.inventory": "Inventario", "nav.messages": "Mensajes", "nav.education": "Educación",
        "nav.reports": "Reportes", "nav.administration": "Administración", "nav.security": "Seguridad",
        "action.logout": "Salir", "action.new_patient": "Nuevo paciente", "header.clinical_care": "ATENCIÓN CLÍNICA",
    },
}


def seed_platform_administration(db: Session) -> None:
    locales = {}
    for code, name in (("en", "English"), ("es", "Español")):
        item = db.scalar(select(LocaleCatalog).where(LocaleCatalog.code == code))
        if not item:
            item = LocaleCatalog(code=code, name=name)
            db.add(item)
            db.flush()
        locales[code] = item
    for code, values in CORE_TRANSLATIONS.items():
        for key, value in values.items():
            if not db.scalar(select(Translation).where(Translation.locale_id == locales[code].id, Translation.key == key)):
                db.add(Translation(locale_id=locales[code].id, key=key, value=value))
    for key, (category, value_type, default, description) in SETTING_DEFINITIONS.items():
        if not db.scalar(select(SystemSetting).where(SystemSetting.key == key)):
            db.add(SystemSetting(key=key, category=category, value_type=value_type, value=default, description=description))


def validate_setting(db: Session, key: str, value: object) -> object:
    definition = SETTING_DEFINITIONS.get(key)
    if not definition:
        raise ValueError("Setting is not managed by OpenRM")
    value_type = definition[1]
    if value_type == "string":
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 120:
            raise ValueError("Value must be a non-empty string of at most 120 characters")
        return value.strip()
    if value_type == "timezone":
        if not isinstance(value, str):
            raise ValueError("Timezone must be an IANA timezone name")
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Timezone must be an IANA timezone name") from exc
        return value
    if value_type == "locale":
        if not isinstance(value, str) or not db.scalar(select(LocaleCatalog).where(LocaleCatalog.code == value, LocaleCatalog.active.is_(True))):
            raise ValueError("Default locale must reference an active locale")
        return value
    if value_type == "choice":
        if value not in DATE_FORMATS:
            raise ValueError("Unsupported date format")
        return value
    if value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int) or not 10 <= value <= 200:
            raise ValueError("Page size must be an integer between 10 and 200")
        return value
    raise ValueError("Unsupported setting type")


def setting_value(db: Session, key: str) -> object:
    item = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    return item.value if item else SETTING_DEFINITIONS[key][2]


def touch_setting(item: SystemSetting, actor_id: int, value: object) -> None:
    item.value = value
    item.version += 1
    item.updated_by_id = actor_id
    item.updated_at = datetime.now(timezone.utc)
