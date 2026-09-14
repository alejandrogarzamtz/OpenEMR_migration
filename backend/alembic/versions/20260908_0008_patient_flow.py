"""Add patient flow episodes and immutable status/room events."""

from alembic import op
import sqlalchemy as sa

revision = "20260908_0008"
down_revision = "20260907_0007"
branch_labels = None
depends_on = None

TABLES = ("patient_flow_episodes", "patient_flow_events")


def upgrade():
    # Bridge the prototype's metadata-based baseline while keeping this feature
    # safe for both existing and freshly-created databases.
    from app.db import Base
    from app import models  # noqa: F401
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    from app.db import Base
    from app import models  # noqa: F401
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
