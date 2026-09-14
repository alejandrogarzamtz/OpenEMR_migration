"""Add inventory products, lots, and immutable stock transactions."""

from alembic import op

revision = "20260909_0009"
down_revision = "20260908_0008"
branch_labels = None
depends_on = None

TABLES = ("inventory_products", "inventory_lots", "inventory_transactions")


def upgrade():
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
