"""Add revocable identity sessions and password reset tokens."""

from alembic import op

revision = "20260913_0013"
down_revision = "20260912_0012"
branch_labels = None
depends_on = None

TABLES = ("auth_sessions", "password_reset_tokens")


def upgrade():
    from app import models  # noqa: F401
    from app.db import Base

    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade():
    from app import models  # noqa: F401
    from app.db import Base

    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
