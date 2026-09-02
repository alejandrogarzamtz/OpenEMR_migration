"""Add normalized, signable clinical forms."""
from alembic import op
from app.db import Base
from app import models  # noqa: F401

revision = "20260903_0003"
down_revision = "20260902_0002"
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.tables["clinical_forms"].create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    Base.metadata.tables["clinical_forms"].drop(bind=op.get_bind(), checkfirst=True)
