"""Preserve clinical-item dates and syndromic surveillance submissions."""
from alembic import op
import sqlalchemy as sa

revision="20261029_0059";down_revision="20261028_0058";branch_labels=None;depends_on=None


def upgrade():
    op.add_column("clinical_items",sa.Column("recorded_at",sa.DateTime(timezone=True)))
    op.add_column("clinical_items",sa.Column("legacy_payload",sa.JSON()))
    op.create_index("ix_clinical_items_recorded_at","clinical_items",["recorded_at"])
    op.create_table("syndromic_submissions",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("legacy_submission_id",sa.Integer()),
        sa.Column("clinical_item_id",sa.Integer(),sa.ForeignKey("clinical_items.id"),nullable=False),sa.Column("submitted_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("filename",sa.String(255),nullable=False),sa.Column("facility_id",sa.Integer(),sa.ForeignKey("facilities.id")),sa.Column("actor_id",sa.Integer(),sa.ForeignKey("users.id")),
        sa.Column("message_control_id",sa.String(64)),sa.Column("legacy_payload",sa.JSON()),sa.UniqueConstraint("uuid"),sa.UniqueConstraint("legacy_submission_id"),sa.UniqueConstraint("clinical_item_id"))
    for name in ("uuid","clinical_item_id","submitted_at","facility_id","actor_id","message_control_id"):
        op.create_index(f"ix_syndromic_submissions_{name}","syndromic_submissions",[name])


def downgrade():
    op.drop_table("syndromic_submissions")
    op.drop_index("ix_clinical_items_recorded_at",table_name="clinical_items")
    op.drop_column("clinical_items","legacy_payload");op.drop_column("clinical_items","recorded_at")
