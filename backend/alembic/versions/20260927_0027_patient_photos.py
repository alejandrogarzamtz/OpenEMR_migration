"""Add private, versioned patient photographs."""
from alembic import op

revision = "20260927_0027"
down_revision = "20260926_0026"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["patient_photos"].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["patient_photos"].drop(bind=bind, checkfirst=True)
