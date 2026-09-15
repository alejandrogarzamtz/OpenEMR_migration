"""Align syndromic uniqueness with indexed ORM columns."""
from alembic import op

revision="20261030_0060";down_revision="20261029_0059";branch_labels=None;depends_on=None


def upgrade():
    op.drop_constraint("syndromic_submissions_uuid_key","syndromic_submissions",type_="unique")
    op.drop_constraint("syndromic_submissions_clinical_item_id_key","syndromic_submissions",type_="unique")
    op.drop_index("ix_syndromic_submissions_uuid",table_name="syndromic_submissions")
    op.drop_index("ix_syndromic_submissions_clinical_item_id",table_name="syndromic_submissions")
    op.create_index("ix_syndromic_submissions_uuid","syndromic_submissions",["uuid"],unique=True)
    op.create_index("ix_syndromic_submissions_clinical_item_id","syndromic_submissions",["clinical_item_id"],unique=True)


def downgrade():
    op.drop_index("ix_syndromic_submissions_clinical_item_id",table_name="syndromic_submissions")
    op.drop_index("ix_syndromic_submissions_uuid",table_name="syndromic_submissions")
    op.create_index("ix_syndromic_submissions_clinical_item_id","syndromic_submissions",["clinical_item_id"])
    op.create_index("ix_syndromic_submissions_uuid","syndromic_submissions",["uuid"])
    op.create_unique_constraint("syndromic_submissions_clinical_item_id_key","syndromic_submissions",["clinical_item_id"])
    op.create_unique_constraint("syndromic_submissions_uuid_key","syndromic_submissions",["uuid"])
