"""Preserve AMC tracking evidence."""
from alembic import op
import sqlalchemy as sa

revision="20261101_0062";down_revision="20261031_0061";branch_labels=None;depends_on=None


def upgrade():
    op.create_table("amc_tracking_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("rule_id",sa.String(31),nullable=False),sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=False),sa.Column("object_category",sa.String(255),nullable=False,server_default=""),sa.Column("legacy_object_id",sa.Integer(),nullable=False,server_default="0"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("completed_at",sa.DateTime(timezone=True),nullable=True),sa.Column("summary_provided_at",sa.DateTime(timezone=True),nullable=True),sa.Column("actor_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),sa.Column("legacy_payload",sa.JSON(),nullable=True))
    for name,column in (("ix_amc_tracking_events_uuid","uuid"),("ix_amc_tracking_events_rule_id","rule_id"),("ix_amc_tracking_events_patient_id","patient_id"),("ix_amc_tracking_events_object_category","object_category"),("ix_amc_tracking_events_legacy_object_id","legacy_object_id"),("ix_amc_tracking_events_created_at","created_at"),("ix_amc_tracking_events_completed_at","completed_at"),("ix_amc_tracking_events_actor_id","actor_id")):op.create_index(name,"amc_tracking_events",[column],unique=column=="uuid")


def downgrade():op.drop_table("amc_tracking_events")
