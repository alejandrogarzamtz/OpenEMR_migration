from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from .config import settings
from .db import engine


def readiness_report() -> dict:
    checks={"database":False,"schema":False,"signing_key":False};details={}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"));checks["database"]=True
            if settings.deployment_environment=="production":
                current=MigrationContext.configure(connection).get_current_revision();head=ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
                details["schema_revision"]=current;details["schema_head"]=head;checks["schema"]=bool(current and current==head)
            else:checks["schema"]=True
    except Exception as exc:details["database_error"]=type(exc).__name__
    if settings.deployment_environment=="production":
        key=Path(settings.smart_oidc_private_key_path or "")
        try:
            from .services.smart_oidc import public_jwk
            checks["signing_key"]=key.is_file() and key.stat().st_mode&0o022==0 and bool(public_jwk().get("n"))
        except Exception as exc:details["signing_key_error"]=type(exc).__name__
    else:checks["signing_key"]=True
    return {"status":"ready" if all(checks.values()) else "not-ready","release":settings.release,"checks":checks,**details}
