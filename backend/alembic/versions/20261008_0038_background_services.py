"""Add managed background-service registry and lease state."""

from alembic import op
import sqlalchemy as sa

revision = "20261008_0038"
down_revision = "20261007_0037"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "background_services",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("name",sa.String(31),nullable=False),sa.Column("title",sa.String(127),nullable=False),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("running_state",sa.Integer(),nullable=False,server_default="-1"),
        sa.Column("next_run",sa.DateTime(timezone=True),nullable=False),
        sa.Column("execute_interval_minutes",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("handler",sa.String(127),nullable=False),sa.Column("legacy_include",sa.String(255),nullable=True),
        sa.Column("sort_order",sa.Integer(),nullable=False,server_default="100"),
        sa.Column("lock_expires_at",sa.DateTime(timezone=True),nullable=True),sa.Column("legacy_payload",sa.JSON(),nullable=True),
    )
    for column in ("name","active","next_run","lock_expires_at"):
        op.create_index(f"ix_background_services_{column}","background_services",[column],unique=column=="name")


def downgrade():
    for column in reversed(("name","active","next_run","lock_expires_at")):
        op.drop_index(f"ix_background_services_{column}",table_name="background_services")
    op.drop_table("background_services")
