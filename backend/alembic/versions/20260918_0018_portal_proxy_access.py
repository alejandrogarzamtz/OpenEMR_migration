"""Add explicit, scoped patient portal representative access."""

import sqlalchemy as sa
from alembic import op

revision = "20260918_0018"
down_revision = "20260917_0017"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns("portal_accounts")}
    indexes = {index["name"] for index in inspector.get_indexes("portal_accounts")}
    with op.batch_alter_table("portal_accounts") as batch:
        if "email" not in columns:
            batch.add_column(sa.Column("email", sa.String(length=255), nullable=True))
        if "display_name" not in columns:
            batch.add_column(sa.Column("display_name", sa.String(length=255), nullable=True))
        if "identity_type" not in columns:
            batch.add_column(sa.Column("identity_type", sa.String(length=30), nullable=False, server_default="patient"))
        if not columns["patient_id"]["nullable"]:
            batch.alter_column("patient_id", existing_type=sa.Integer(), nullable=True)
        if "ix_portal_accounts_email" not in indexes:
            batch.create_index("ix_portal_accounts_email", ["email"])
        if "ix_portal_accounts_identity_type" not in indexes:
            batch.create_index("ix_portal_accounts_identity_type", ["identity_type"])
    op.execute("UPDATE portal_accounts SET email = (SELECT email FROM patients WHERE patients.id = portal_accounts.patient_id)")
    op.execute("UPDATE portal_accounts SET display_name = (SELECT first_name || ' ' || last_name FROM patients WHERE patients.id = portal_accounts.patient_id)")
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["portal_access_grants"].create(bind=bind, checkfirst=True)


def downgrade():
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["portal_access_grants"].drop(bind=op.get_bind(), checkfirst=True)
    # Representative identities cannot be represented by the prior schema.
    op.execute("DELETE FROM identity_audit_events WHERE portal_account_id IN (SELECT id FROM portal_accounts WHERE patient_id IS NULL)")
    op.execute("DELETE FROM auth_sessions WHERE portal_account_id IN (SELECT id FROM portal_accounts WHERE patient_id IS NULL)")
    op.execute("DELETE FROM portal_password_reset_tokens WHERE portal_account_id IN (SELECT id FROM portal_accounts WHERE patient_id IS NULL)")
    op.execute("DELETE FROM portal_mfa_challenges WHERE portal_account_id IN (SELECT id FROM portal_accounts WHERE patient_id IS NULL)")
    op.execute("DELETE FROM portal_mfa_registrations WHERE portal_account_id IN (SELECT id FROM portal_accounts WHERE patient_id IS NULL)")
    op.execute("DELETE FROM portal_accounts WHERE patient_id IS NULL")
    with op.batch_alter_table("portal_accounts") as batch:
        batch.drop_index("ix_portal_accounts_identity_type")
        batch.drop_index("ix_portal_accounts_email")
        batch.alter_column("patient_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("identity_type")
        batch.drop_column("display_name")
        batch.drop_column("email")
