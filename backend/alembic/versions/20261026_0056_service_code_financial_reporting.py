"""Preserve the service-code financial reporting indicator."""
from alembic import op
import sqlalchemy as sa

revision="20261026_0056";down_revision="20261025_0055";branch_labels=None;depends_on=None


def upgrade():
    op.add_column("service_codes",sa.Column("financial_reporting",sa.Boolean(),nullable=False,server_default=sa.false()))
    op.create_index("ix_service_codes_financial_reporting","service_codes",["financial_reporting"])


def downgrade():
    op.drop_index("ix_service_codes_financial_reporting",table_name="service_codes")
    op.drop_column("service_codes","financial_reporting")
