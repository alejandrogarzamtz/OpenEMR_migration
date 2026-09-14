"""Preserve complete procedure-order, report and result provenance."""
from alembic import op
import sqlalchemy as sa

revision="20261016_0046";down_revision="20261015_0045";branch_labels=None;depends_on=None


def upgrade():
    for name, type_, nullable in (
        ("collected_at",sa.DateTime(timezone=True),True),("transmitted_at",sa.DateTime(timezone=True),True),
        ("control_id",sa.String(255),True),("activity",sa.Boolean(),False),
        ("provider_legacy_id",sa.Integer(),True),("lab_legacy_id",sa.Integer(),True),
        ("specimen_type",sa.String(31),True),("specimen_location",sa.String(31),True),
        ("specimen_volume",sa.String(30),True),("clinical_history",sa.String(255),True),
        ("external_id",sa.String(20),True),("order_diagnosis",sa.String(255),True),
        ("procedure_order_type",sa.String(32),True),("legacy_payload",sa.JSON(),True),
    ):
        kwargs={"nullable":nullable}
        if name=="activity": kwargs["server_default"]=sa.true()
        op.add_column("lab_orders",sa.Column(name,type_,**kwargs))
    op.alter_column("lab_orders","ordered_at",existing_type=sa.DateTime(timezone=True),nullable=True)
    op.create_index("ix_lab_orders_activity","lab_orders",["activity"])

    op.create_table("procedure_order_lines",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),
        sa.Column("order_id",sa.Integer(),sa.ForeignKey("lab_orders.id"),nullable=False),
        sa.Column("sequence",sa.Integer(),nullable=False),sa.Column("code",sa.String(64),nullable=False),
        sa.Column("name",sa.String(255),nullable=False),sa.Column("source",sa.String(1)),
        sa.Column("diagnoses",sa.Text()),sa.Column("do_not_send",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("title",sa.String(255)),sa.Column("procedure_type",sa.String(31)),sa.Column("transport",sa.String(31)),
        sa.Column("date_end",sa.DateTime(timezone=True)),sa.Column("reason_code",sa.String(31)),
        sa.Column("reason_description",sa.Text()),sa.Column("reason_date_low",sa.DateTime(timezone=True)),
        sa.Column("reason_date_high",sa.DateTime(timezone=True)),sa.Column("reason_status",sa.String(31)),
        sa.Column("legacy_payload",sa.JSON()),sa.UniqueConstraint("order_id","sequence",name="uq_procedure_order_line_sequence"))
    op.create_index("ix_procedure_order_lines_uuid","procedure_order_lines",["uuid"],unique=True)
    op.create_index("ix_procedure_order_lines_order_id","procedure_order_lines",["order_id"])

    op.create_table("procedure_reports",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),
        sa.Column("legacy_report_id",sa.Integer(),unique=True),sa.Column("order_id",sa.Integer(),sa.ForeignKey("lab_orders.id")),
        sa.Column("legacy_order_id",sa.Integer()),sa.Column("order_sequence",sa.Integer(),nullable=False,server_default="1"),
        sa.Column("collected_at",sa.DateTime(timezone=True)),sa.Column("collected_timezone",sa.String(5)),
        sa.Column("reported_at",sa.DateTime(timezone=True)),sa.Column("reported_timezone",sa.String(5)),
        sa.Column("source_legacy_user_id",sa.Integer()),sa.Column("specimen_number",sa.String(63)),
        sa.Column("status",sa.String(31)),sa.Column("review_status",sa.String(31)),sa.Column("notes",sa.Text()),
        sa.Column("legacy_payload",sa.JSON()))
    for column,unique in (("uuid",True),("order_id",False),("legacy_order_id",False)):
        op.create_index(f"ix_procedure_reports_{column}","procedure_reports",[column],unique=unique)

    op.add_column("lab_results",sa.Column("report_id",sa.Integer(),sa.ForeignKey("procedure_reports.id")))
    op.add_column("lab_results",sa.Column("data_type",sa.String(1)))
    op.add_column("lab_results",sa.Column("facility",sa.String(255)))
    op.add_column("lab_results",sa.Column("comments",sa.Text()))
    op.add_column("lab_results",sa.Column("legacy_document_id",sa.Integer()))
    op.add_column("lab_results",sa.Column("ended_at",sa.DateTime(timezone=True)))
    op.add_column("lab_results",sa.Column("legacy_payload",sa.JSON()))
    op.create_index("ix_lab_results_report_id","lab_results",["report_id"])
    op.alter_column("lab_results","order_id",existing_type=sa.Integer(),nullable=True)
    op.alter_column("lab_results","observed_at",existing_type=sa.DateTime(timezone=True),nullable=True)


def downgrade():
    op.alter_column("lab_results","observed_at",existing_type=sa.DateTime(timezone=True),nullable=False)
    op.alter_column("lab_results","order_id",existing_type=sa.Integer(),nullable=False)
    op.drop_index("ix_lab_results_report_id",table_name="lab_results")
    for name in ("legacy_payload","ended_at","legacy_document_id","comments","facility","data_type","report_id"):
        op.drop_column("lab_results",name)
    op.drop_table("procedure_reports");op.drop_table("procedure_order_lines")
    op.drop_index("ix_lab_orders_activity",table_name="lab_orders")
    op.alter_column("lab_orders","ordered_at",existing_type=sa.DateTime(timezone=True),nullable=False)
    for name in ("legacy_payload","procedure_order_type","order_diagnosis","external_id","clinical_history","specimen_volume","specimen_location","specimen_type","lab_legacy_id","provider_legacy_id","activity","control_id","transmitted_at","collected_at"):
        op.drop_column("lab_orders",name)
