"""Add versioned patient consent and directive records."""
from alembic import op

revision = "20260922_0022"
down_revision = "20260921_0021"
branch_labels = None
depends_on = None


def upgrade():
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["patient_consents"].create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["patient_consents"].drop(bind=op.get_bind(), checkfirst=True)
