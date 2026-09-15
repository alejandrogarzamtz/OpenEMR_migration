"""Add lossless ONC real-world-testing metric evidence."""
from alembic import op
import sqlalchemy as sa

revision="20261027_0057";down_revision="20261026_0056";branch_labels=None;depends_on=None


def upgrade():
    op.create_table("regulatory_metric_events",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("source_key",sa.String(160),nullable=False),
        sa.Column("metric_type",sa.String(40),nullable=False),sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False),sa.Column("success",sa.Boolean()),
        sa.Column("actor_kind",sa.String(20)),sa.Column("resource",sa.String(255)),sa.Column("legacy_payload",sa.JSON()))
    for name in ("uuid","source_key","metric_type","occurred_at","success","actor_kind","resource"):
        op.create_index(f"ix_regulatory_metric_events_{name}","regulatory_metric_events",[name],unique=name in {"uuid","source_key"})


def downgrade():op.drop_table("regulatory_metric_events")
