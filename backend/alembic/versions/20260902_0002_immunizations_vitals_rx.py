"""Add immunizations, vital signs, pharmacies and prescriptions."""
from alembic import op
from app.db import Base
from app import models  # noqa: F401

revision = "20260902_0002"
down_revision = "20260901_0001"
branch_labels = None
depends_on = None

TABLES = ("immunizations", "vital_sets", "pharmacies", "prescriptions")


def upgrade():
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
