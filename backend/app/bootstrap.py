from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from .config import settings
from .db import Base, SessionLocal, engine
from .models import QuestionnaireDefinition, User
from .security import password_hash
from .services.platform_administration import seed_platform_administration

QUESTIONNAIRES = {
    "PHQ-9": {
        "title": "Patient Health Questionnaire-9",
        "questions": [
            "Little interest or pleasure in doing things",
            "Feeling down, depressed, or hopeless",
            "Trouble falling or staying asleep, or sleeping too much",
            "Feeling tired or having little energy",
            "Poor appetite or overeating",
            "Feeling bad about yourself - or that you are a failure or have let yourself or your family down",
            "Trouble concentrating on things, such as reading an article or watching videos",
            "Moving or speaking slowly noted by others or fidgety or restless more than usual",
            "Thoughts that you would be better off dead, or of hurting yourself",
        ],
    },
    "GAD-7": {
        "title": "Generalized Anxiety Disorder-7",
        "questions": [
            "Feeling nervous, anxious, or on edge",
            "Not being able to stop or control worrying",
            "Worrying too much about different things",
            "Trouble relaxing",
            "Being so restless that it's hard to sit still",
            "Becoming easily annoyed or irritable",
            "Feeling afraid as if something awful might happen",
        ],
    },
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Unit tests use an isolated in-memory database. Deployed databases are
    # changed exclusively through Alembic before the API process starts.
    if settings.database_url == "sqlite://":
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_platform_administration(db)
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
                            {"id": f"q{x}", "text": text, "min": 0, "max": 3}
                            for x, text in enumerate(definition["questions"], start=1)
                        ],
                    )
                )
        db.commit()
    yield
