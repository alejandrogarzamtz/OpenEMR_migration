"""Add versioned questionnaires and scored responses."""
from alembic import op
from app.db import Base
from app import models  # noqa: F401

revision = "20260904_0004"
down_revision = "20260903_0003"
branch_labels = None
depends_on = None

TABLES = ("questionnaire_definitions", "questionnaire_responses")


def upgrade():
    bind = op.get_bind()
    for name in TABLES: Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES): Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
