"""Add reproducible report execution snapshots."""

from alembic import op

revision = "20260911_0011"
down_revision = "20260910_0010"
branch_labels = None
depends_on = None


def upgrade():
    from app.db import Base
    from app import models  # noqa: F401
    Base.metadata.tables["report_runs"].create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    from app.db import Base
    from app import models  # noqa: F401
    Base.metadata.tables["report_runs"].drop(bind=op.get_bind(), checkfirst=True)
