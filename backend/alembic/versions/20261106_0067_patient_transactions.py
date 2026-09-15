"""Preserve generic patient transactions and message deletion state."""
from alembic import op
import sqlalchemy as sa

revision="20261106_0067";down_revision="20261105_0066";branch_labels=None;depends_on=None


def upgrade():
    bind=op.get_bind();inspector=sa.inspect(bind);tables=set(inspector.get_table_names())
    message_columns={column["name"] for column in inspector.get_columns("secure_messages")}
    if "deleted_at" not in message_columns:op.add_column("secure_messages",sa.Column("deleted_at",sa.DateTime(timezone=True),nullable=True))
    message_indexes={index["name"] for index in sa.inspect(bind).get_indexes("secure_messages")}
    if "ix_secure_messages_deleted_at" not in message_indexes:op.create_index("ix_secure_messages_deleted_at","secure_messages",["deleted_at"])
    if "patient_transactions" not in tables:
        op.create_table("patient_transactions",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("legacy_transaction_id",sa.Integer(),nullable=True,unique=True),sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=False),sa.Column("title",sa.String(255),nullable=False),sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False),sa.Column("body",sa.Text(),nullable=True),sa.Column("status",sa.String(30),nullable=False,server_default="active"),sa.Column("legacy_payload",sa.JSON(),nullable=True))
        for column in ("uuid","patient_id","occurred_at"):op.create_index(f"ix_patient_transactions_{column}","patient_transactions",[column],unique=column=="uuid")


def downgrade():
    op.drop_table("patient_transactions");op.drop_index("ix_secure_messages_deleted_at",table_name="secure_messages");op.drop_column("secure_messages","deleted_at")
