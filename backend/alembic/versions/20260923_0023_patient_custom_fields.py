"""Add layout-driven patient demographic field definitions and values."""
from alembic import op

revision = "20260923_0023"
down_revision = "20260922_0022"
branch_labels = None
depends_on = None

TABLES = ("patient_custom_field_definitions", "patient_custom_field_values")


def upgrade():
    from app import models  # noqa: F401
    from app.db import Base
    bind = op.get_bind()
    for name in TABLES: Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    from app import models  # noqa: F401
    from app.db import Base
    bind = op.get_bind()
    for name in reversed(TABLES): Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
