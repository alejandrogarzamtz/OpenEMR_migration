"""Persist FHIR bulk export jobs."""
from alembic import op
import sqlalchemy as sa

revision="20261107_0068";down_revision="20261106_0067";branch_labels=None;depends_on=None


def upgrade():
    if "bulk_export_jobs" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table("bulk_export_jobs",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("requested_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("scope",sa.String(20),nullable=False),sa.Column("scope_id",sa.String(36),nullable=True),sa.Column("status",sa.String(20),nullable=False,server_default="complete"),sa.Column("output",sa.JSON(),nullable=False),sa.Column("error",sa.JSON(),nullable=False),sa.Column("transaction_time",sa.DateTime(timezone=True),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("deleted_at",sa.DateTime(timezone=True),nullable=True))
        for column in ("uuid","requested_by_id","scope","status","expires_at","deleted_at"):op.create_index(f"ix_bulk_export_jobs_{column}","bulk_export_jobs",[column],unique=column=="uuid")


def downgrade():
    op.drop_table("bulk_export_jobs")
