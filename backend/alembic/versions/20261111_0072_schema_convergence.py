"""Converge deployments created before the engagement migration was finalized.

Revision ID: 20261111_0072
Revises: 20261110_0071
"""
from alembic import op
import sqlalchemy as sa


revision = "20261111_0072"
down_revision = "20261110_0071"
branch_labels = None
depends_on = None


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _unique_columns(inspector: sa.Inspector, table: str) -> set[tuple[str, ...]]:
    return {tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints(table)}


def upgrade() -> None:
    """Repair older databases while remaining a no-op for fresh installations."""
    bind = op.get_bind()

    columns = _columns(sa.inspect(bind), "communication_deliveries")
    if "legacy_notification_id" not in columns:
        op.add_column("communication_deliveries", sa.Column("legacy_notification_id", sa.Integer(), nullable=True))
    if ("legacy_notification_id",) not in _unique_columns(sa.inspect(bind), "communication_deliveries"):
        op.create_unique_constraint("uq_communication_deliveries_legacy_notification_id", "communication_deliveries", ["legacy_notification_id"])

    columns = _columns(sa.inspect(bind), "questionnaire_definitions")
    if "legacy_questionnaire_id" not in columns:
        op.add_column("questionnaire_definitions", sa.Column("legacy_questionnaire_id", sa.Integer(), nullable=True))
    if "legacy_payload" not in columns:
        op.add_column("questionnaire_definitions", sa.Column("legacy_payload", sa.JSON(), nullable=True))
    if ("legacy_questionnaire_id",) not in _unique_columns(sa.inspect(bind), "questionnaire_definitions"):
        op.create_unique_constraint("uq_questionnaire_definitions_legacy_questionnaire_id", "questionnaire_definitions", ["legacy_questionnaire_id"])

    columns = _columns(sa.inspect(bind), "questionnaire_responses")
    if "legacy_response_id" not in columns:
        op.add_column("questionnaire_responses", sa.Column("legacy_response_id", sa.Integer(), nullable=True))
    if "status" not in columns:
        op.add_column("questionnaire_responses", sa.Column("status", sa.String(20), nullable=False, server_default="completed"))
    if "legacy_payload" not in columns:
        op.add_column("questionnaire_responses", sa.Column("legacy_payload", sa.JSON(), nullable=True))
    inspector = sa.inspect(bind)
    if ("legacy_response_id",) not in _unique_columns(inspector, "questionnaire_responses"):
        op.create_unique_constraint("uq_questionnaire_responses_legacy_response_id", "questionnaire_responses", ["legacy_response_id"])
    if "ix_questionnaire_responses_status" not in {index["name"] for index in inspector.get_indexes("questionnaire_responses")}:
        op.create_index("ix_questionnaire_responses_status", "questionnaire_responses", ["status"])

    columns = _columns(sa.inspect(bind), "notification_preferences")
    if "quiet_hours_start" in columns:
        op.drop_column("notification_preferences", "quiet_hours_start")
    if "quiet_hours_end" in columns:
        op.drop_column("notification_preferences", "quiet_hours_end")


def downgrade() -> None:
    # Revision 0069 already declares the converged schema. This repair revision
    # records that convergence for databases upgraded before 0069 was finalized.
    pass
