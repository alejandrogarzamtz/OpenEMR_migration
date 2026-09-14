"""Add normalized patient employment history."""
from alembic import op
import sqlalchemy as sa

revision = "20260921_0021"
down_revision = "20260920_0020"
branch_labels = None
depends_on = None


def upgrade():
    from app import models  # noqa: F401
    from app.db import Base
    bind = op.get_bind()
    Base.metadata.tables["patient_employments"].create(bind=bind, checkfirst=True)
    # Prototype databases reached 0005 with a temporarily nullable UUID column;
    # fresh databases use the current non-nullable model. All UUIDs were
    # backfilled by 0005, so converge both upgrade paths on the same invariant.
    user_uuid = next(column for column in sa.inspect(bind).get_columns("users") if column["name"] == "uuid")
    if user_uuid["nullable"]:
        op.alter_column("users", "uuid", existing_type=sa.String(length=36), nullable=False)


def downgrade():
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["patient_employments"].drop(bind=op.get_bind(), checkfirst=True)
