"""Add lossless clinical decision rule evaluation logs."""
from alembic import op
import sqlalchemy as sa
revision="20261014_0044";down_revision="20261013_0043";branch_labels=None;depends_on=None
def upgrade():
    op.create_table("clinical_rule_logs",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("legacy_log_id",sa.Integer(),nullable=True,unique=True),sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=True),sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=True),sa.Column("actor_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),sa.Column("facility_id",sa.Integer(),sa.ForeignKey("facilities.id"),nullable=True),sa.Column("legacy_patient_id",sa.Integer(),nullable=False,server_default="0"),sa.Column("legacy_user_id",sa.Integer(),nullable=False,server_default="0"),sa.Column("legacy_facility_id",sa.Integer(),nullable=False,server_default="0"),sa.Column("category",sa.String(255),nullable=False),sa.Column("value",sa.Text(),nullable=True),sa.Column("new_value",sa.Text(),nullable=True),sa.Column("legacy_payload",sa.JSON(),nullable=True))
    for column in ("uuid","occurred_at","patient_id","actor_id","facility_id","category"):op.create_index(f"ix_clinical_rule_logs_{column}","clinical_rule_logs",[column],unique=column=="uuid")
def downgrade():op.drop_table("clinical_rule_logs")
