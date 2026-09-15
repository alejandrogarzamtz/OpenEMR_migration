"""Add extension registry and durable signed webhook events."""
from alembic import op
import sqlalchemy as sa

revision="20261110_0071";down_revision="20261109_0070";branch_labels=None;depends_on=None


def upgrade():
    tables=set(sa.inspect(op.get_bind()).get_table_names())
    if "extension_packages" not in tables:
        op.create_table("extension_packages",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("key",sa.String(120),nullable=False),sa.Column("name",sa.String(255),nullable=False),sa.Column("version",sa.String(50),nullable=False),sa.Column("api_version",sa.String(20),nullable=False),sa.Column("description",sa.String(1000),nullable=True),sa.Column("homepage_url",sa.String(1000),nullable=True),sa.Column("manifest",sa.JSON(),nullable=False),sa.Column("status",sa.String(20),nullable=False),sa.Column("installed_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),sa.Column("installed_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.Column("credential_hash",sa.String(64),nullable=True),sa.Column("legacy_module_id",sa.Integer(),nullable=True,unique=True),sa.Column("legacy_payload",sa.JSON(),nullable=True))
        for column in ("uuid","key","status","credential_hash"):op.create_index(f"ix_extension_packages_{column}","extension_packages",[column],unique=column in {"uuid","key"})
    if "integration_events" not in tables:
        op.create_table("integration_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("event_type",sa.String(160),nullable=False),sa.Column("schema_version",sa.String(20),nullable=False),sa.Column("source_extension_id",sa.Integer(),sa.ForeignKey("extension_packages.id"),nullable=True),sa.Column("resource_type",sa.String(80),nullable=True),sa.Column("resource_id",sa.String(100),nullable=True),sa.Column("payload",sa.JSON(),nullable=False),sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False))
        for column in ("uuid","event_type","source_extension_id","occurred_at"):op.create_index(f"ix_integration_events_{column}","integration_events",[column],unique=column=="uuid")
    if "webhook_subscriptions" not in tables:
        op.create_table("webhook_subscriptions",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("extension_id",sa.Integer(),sa.ForeignKey("extension_packages.id"),nullable=True),sa.Column("name",sa.String(255),nullable=False),sa.Column("endpoint_url",sa.String(1000),nullable=False),sa.Column("event_types",sa.JSON(),nullable=False),sa.Column("encrypted_secret",sa.LargeBinary(),nullable=False),sa.Column("active",sa.Boolean(),nullable=False),sa.Column("max_attempts",sa.Integer(),nullable=False),sa.Column("created_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
        for column in ("uuid","extension_id","active"):op.create_index(f"ix_webhook_subscriptions_{column}","webhook_subscriptions",[column],unique=column=="uuid")
    if "webhook_deliveries" not in tables:
        op.create_table("webhook_deliveries",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("subscription_id",sa.Integer(),sa.ForeignKey("webhook_subscriptions.id"),nullable=False),sa.Column("event_id",sa.Integer(),sa.ForeignKey("integration_events.id"),nullable=False),sa.Column("status",sa.String(20),nullable=False),sa.Column("attempts",sa.Integer(),nullable=False),sa.Column("next_attempt_at",sa.DateTime(timezone=True),nullable=False),sa.Column("last_attempt_at",sa.DateTime(timezone=True),nullable=True),sa.Column("delivered_at",sa.DateTime(timezone=True),nullable=True),sa.Column("response_status",sa.Integer(),nullable=True),sa.Column("error_message",sa.String(1000),nullable=True),sa.UniqueConstraint("subscription_id","event_id",name="uq_webhook_delivery_subscription_event"))
        for column in ("uuid","subscription_id","event_id","status","next_attempt_at"):op.create_index(f"ix_webhook_deliveries_{column}","webhook_deliveries",[column],unique=column=="uuid")


def downgrade():
    for table in ("webhook_deliveries","webhook_subscriptions","integration_events","extension_packages"):op.drop_table(table)
