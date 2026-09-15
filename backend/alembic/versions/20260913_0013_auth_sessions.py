"""Add revocable identity sessions and password reset tokens."""

from alembic import op
import sqlalchemy as sa

revision = "20260913_0013"
down_revision = "20260912_0012"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=False),
        sa.Column("identity_kind", sa.String(20), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("portal_account_id", sa.Integer(), sa.ForeignKey("portal_accounts.id"), nullable=True),
        sa.Column("access_jti", sa.String(36), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False),
        sa.Column("previous_refresh_token_hash", sa.String(64), nullable=True),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(100), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
    )
    for column in ("uuid", "identity_kind", "user_id", "portal_account_id", "access_jti", "refresh_token_hash", "previous_refresh_token_hash", "refresh_expires_at", "revoked_at"):
        op.create_index(f"ix_auth_sessions_{column}", "auth_sessions", [column], unique=column in {"uuid", "access_jti", "refresh_token_hash"})
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("uuid", "user_id", "token_hash", "expires_at"):
        op.create_index(f"ix_password_reset_tokens_{column}", "password_reset_tokens", [column], unique=column in {"uuid", "token_hash"})


def downgrade():
    op.drop_table("password_reset_tokens")
    op.drop_table("auth_sessions")
