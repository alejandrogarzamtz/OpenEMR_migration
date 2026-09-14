from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from .config import settings
from .db import Base, SessionLocal, engine
from .models import QuestionnaireDefinition, User
from .security import password_hash

QUESTIONNAIRES = {
    "PHQ-9": {"title": "Patient Health Questionnaire-9", "count": 9},
    "GAD-7": {"title": "Generalized Anxiety Disorder-7", "count": 7},
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Unit tests use an isolated in-memory database. Deployed databases are
    # changed exclusively through Alembic before the API process starts.
    if settings.database_url == "sqlite://":
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
            if not db.scalar(select(User).where(User.email == settings.bootstrap_admin_email)):
                db.add(
                    User(
                        email=settings.bootstrap_admin_email,
                        password_hash=password_hash.hash(
                            settings.bootstrap_admin_password.get_secret_value()
                        ),
                        role="admin",
                        active=True,
                        permissions=["*:*:*"],
                    )
                )
        for code, definition in QUESTIONNAIRES.items():
            exists = db.scalar(
                select(QuestionnaireDefinition).where(
                    QuestionnaireDefinition.code == code,
                    QuestionnaireDefinition.version == "1",
                )
            )
            if not exists:
                db.add(
                    QuestionnaireDefinition(
                        code=code,
                        version="1",
                        title=definition["title"],
                        questions=[
                            {"id": f"q{x}", "text": f"{code} item {x}", "min": 0, "max": 3}
                            for x in range(1, definition["count"] + 1)
                        ],
                    )
                )
        db.commit()
    yield

