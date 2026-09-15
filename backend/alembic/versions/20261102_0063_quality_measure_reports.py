"""Preserve saved CQM and AMC report evidence."""
from alembic import op
import sqlalchemy as sa

revision="20261102_0063";down_revision="20261101_0062";branch_labels=None;depends_on=None


def upgrade():
    op.add_column("amc_tracking_events",sa.Column("legacy_sequence",sa.Integer(),nullable=True))
    op.create_index("ix_amc_tracking_events_legacy_sequence","amc_tracking_events",["legacy_sequence"])
    op.create_table("quality_measure_reports",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("legacy_report_id",sa.BigInteger(),nullable=False),sa.Column("report_type",sa.String(31),nullable=False),sa.Column("status",sa.String(31),nullable=True),sa.Column("provider",sa.String(64),nullable=True),sa.Column("plan",sa.String(64),nullable=True),sa.Column("organize_mode",sa.String(31),nullable=True),sa.Column("patient_provider_relationship",sa.String(31),nullable=True),sa.Column("labs_manual",sa.String(31),nullable=True),sa.Column("reported_at",sa.DateTime(timezone=True),nullable=True),sa.Column("period_start",sa.DateTime(timezone=True),nullable=True),sa.Column("period_end",sa.DateTime(timezone=True),nullable=True),sa.Column("data",sa.JSON(),nullable=False),sa.Column("legacy_fields",sa.JSON(),nullable=False))
    for column in ("uuid","legacy_report_id","report_type","status","provider","reported_at"):op.create_index(f"ix_quality_measure_reports_{column}","quality_measure_reports",[column],unique=column in {"uuid","legacy_report_id"})
    op.create_table("quality_measure_items",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("report_id",sa.Integer(),sa.ForeignKey("quality_measure_reports.id"),nullable=False),sa.Column("sequence",sa.Integer(),nullable=False),sa.Column("itemized_test_id",sa.Integer(),nullable=False),sa.Column("numerator_label",sa.String(25),nullable=False,server_default=""),sa.Column("pass_status",sa.Integer(),nullable=False),sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=True),sa.Column("legacy_patient_id",sa.BigInteger(),nullable=False),sa.Column("rule_id",sa.String(31),nullable=True),sa.Column("item_details",sa.JSON(),nullable=True),sa.Column("legacy_payload",sa.JSON(),nullable=False),sa.UniqueConstraint("report_id","sequence",name="uq_quality_measure_item_report_sequence"))
    for column in ("report_id","itemized_test_id","pass_status","patient_id","legacy_patient_id","rule_id"):op.create_index(f"ix_quality_measure_items_{column}","quality_measure_items",[column])


def downgrade():
    op.drop_table("quality_measure_items");op.drop_table("quality_measure_reports");op.drop_index("ix_amc_tracking_events_legacy_sequence",table_name="amc_tracking_events");op.drop_column("amc_tracking_events","legacy_sequence")
