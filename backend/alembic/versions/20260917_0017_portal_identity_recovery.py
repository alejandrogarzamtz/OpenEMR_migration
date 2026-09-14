"""Add isolated portal password recovery and encrypted TOTP MFA."""

from alembic import op

revision = "20260917_0017"
down_revision = "20260916_0016"
branch_labels = None
depends_on = None

TABLES = ("portal_password_reset_tokens", "portal_mfa_registrations", "portal_mfa_challenges")


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
