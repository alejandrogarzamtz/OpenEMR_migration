"""Add portal accounts, secure messaging, tasks, and delivery outbox."""

from alembic import op

revision = "20260912_0012"
down_revision = "20260911_0011"
branch_labels = None
depends_on = None

TABLES=("portal_accounts","message_threads","secure_messages","clinical_tasks","communication_deliveries")


def upgrade():
    from app.db import Base
    from app import models  # noqa: F401
    bind=op.get_bind()
    for name in TABLES: Base.metadata.tables[name].create(bind=bind,checkfirst=True)


def downgrade():
    from app.db import Base
    from app import models  # noqa: F401
    bind=op.get_bind()
    for name in reversed(TABLES): Base.metadata.tables[name].drop(bind=bind,checkfirst=True)
