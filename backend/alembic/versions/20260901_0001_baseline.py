"""OpenRM historical baseline schema.

This revision is intentionally self-contained. Never import live application
metadata here: doing so makes a clean replay create tables and foreign keys that
belong to later revisions.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260901_0001"
down_revision = None
branch_labels = None
depends_on = None

metadata=sa.MetaData()


def col(name,type_,*args,**kwargs):return sa.Column(name,type_,*args,**kwargs)


sa.Table("users",metadata,col("id",sa.Integer,primary_key=True),col("email",sa.String(255),unique=True,index=True,nullable=False),col("password_hash",sa.String(255),nullable=False),col("role",sa.String(30),nullable=False))
sa.Table("patients",metadata,col("id",sa.Integer,primary_key=True),col("uuid",sa.String(36),unique=True,index=True,nullable=False),col("legacy_pid",sa.Integer,unique=True),col("first_name",sa.String(100),nullable=False),col("last_name",sa.String(100),index=True,nullable=False),col("date_of_birth",sa.Date,nullable=False),col("sex",sa.String(30),nullable=False),col("email",sa.String(255)),col("phone",sa.String(50)),col("created_at",sa.DateTime(timezone=True),nullable=False))
sa.Table("audit_events",metadata,col("id",sa.Integer,primary_key=True),col("occurred_at",sa.DateTime(timezone=True),nullable=False),col("actor_id",sa.Integer,sa.ForeignKey("users.id"),nullable=False),col("action",sa.String(50),nullable=False),col("resource_type",sa.String(50),nullable=False),col("resource_id",sa.String(100)),col("detail",sa.Text))
sa.Table("appointments",metadata,col("id",sa.Integer,primary_key=True),col("uuid",sa.String(36),unique=True,index=True,nullable=False),col("legacy_event_id",sa.Integer,unique=True),col("patient_id",sa.Integer,sa.ForeignKey("patients.id"),index=True,nullable=False),col("starts_at",sa.DateTime(timezone=True),index=True,nullable=False),col("ends_at",sa.DateTime(timezone=True),nullable=False),col("status",sa.String(30),nullable=False),col("reason",sa.String(255)),col("provider_name",sa.String(150)))
sa.Table("encounters",metadata,col("id",sa.Integer,primary_key=True),col("uuid",sa.String(36),unique=True,index=True,nullable=False),col("legacy_encounter_id",sa.Integer,unique=True),col("patient_id",sa.Integer,sa.ForeignKey("patients.id"),index=True,nullable=False),col("appointment_id",sa.Integer,sa.ForeignKey("appointments.id")),col("occurred_at",sa.DateTime(timezone=True),index=True,nullable=False),col("type",sa.String(50),nullable=False),col("status",sa.String(30),nullable=False),col("chief_complaint",sa.Text),col("clinical_note",sa.Text))
sa.Table("clinical_items",metadata,col("id",sa.Integer,primary_key=True),col("uuid",sa.String(36),unique=True,index=True,nullable=False),col("legacy_list_id",sa.Integer,unique=True),col("patient_id",sa.Integer,sa.ForeignKey("patients.id"),index=True,nullable=False),col("category",sa.String(30),index=True,nullable=False),col("title",sa.String(255),nullable=False),col("code_system",sa.String(30)),col("code",sa.String(50)),col("status",sa.String(30),nullable=False),col("onset_date",sa.Date),col("end_date",sa.Date),col("severity",sa.String(30)),col("reaction",sa.String(255)),col("dosage",sa.String(255)),col("note",sa.Text),col("created_at",sa.DateTime(timezone=True),nullable=False))
sa.Table("lab_orders",metadata,col("id",sa.Integer,primary_key=True),col("uuid",sa.String(36),unique=True,index=True,nullable=False),col("legacy_order_id",sa.Integer,unique=True),col("patient_id",sa.Integer,sa.ForeignKey("patients.id"),index=True,nullable=False),col("encounter_id",sa.Integer,sa.ForeignKey("encounters.id")),col("ordered_at",sa.DateTime(timezone=True),index=True,nullable=False),col("code",sa.String(64),nullable=False),col("name",sa.String(255),nullable=False),col("priority",sa.String(31),nullable=False),col("status",sa.String(31),nullable=False),col("instructions",sa.Text))
sa.Table("lab_results",metadata,col("id",sa.Integer,primary_key=True),col("uuid",sa.String(36),unique=True,index=True,nullable=False),col("legacy_result_id",sa.Integer,unique=True),col("order_id",sa.Integer,sa.ForeignKey("lab_orders.id"),index=True,nullable=False),col("observed_at",sa.DateTime(timezone=True),nullable=False),col("code",sa.String(64),nullable=False),col("name",sa.String(255),nullable=False),col("value",sa.String(255),nullable=False),col("unit",sa.String(31)),col("reference_range",sa.String(255)),col("interpretation",sa.String(31)),col("status",sa.String(31),nullable=False))
sa.Table("documents",metadata,col("id",sa.Integer,primary_key=True),col("uuid",sa.String(36),unique=True,index=True,nullable=False),col("legacy_document_id",sa.Integer,unique=True),col("patient_id",sa.Integer,sa.ForeignKey("patients.id"),index=True,nullable=False),col("encounter_id",sa.Integer,sa.ForeignKey("encounters.id")),col("name",sa.String(255),nullable=False),col("mime_type",sa.String(100),nullable=False),col("content",sa.LargeBinary,nullable=False),col("sha256",sa.String(64),nullable=False),col("uploaded_at",sa.DateTime(timezone=True),nullable=False))
sa.Table("payers",metadata,col("id",sa.Integer,primary_key=True),col("uuid",sa.String(36),unique=True,index=True,nullable=False),col("legacy_payer_id",sa.Integer,unique=True),col("name",sa.String(255),index=True,nullable=False),col("payer_identifier",sa.String(25)),col("active",sa.Boolean,nullable=False))
sa.Table("coverages",metadata,col("id",sa.Integer,primary_key=True),col("uuid",sa.String(36),unique=True,index=True,nullable=False),col("legacy_insurance_id",sa.Integer,unique=True),col("patient_id",sa.Integer,sa.ForeignKey("patients.id"),index=True,nullable=False),col("payer_id",sa.Integer,sa.ForeignKey("payers.id"),nullable=False),col("priority",sa.String(20),nullable=False),col("plan_name",sa.String(255)),col("policy_number",sa.String(255),nullable=False),col("group_number",sa.String(255)),col("subscriber_name",sa.String(255),nullable=False),col("relationship",sa.String(50),nullable=False),col("starts_on",sa.Date),col("ends_on",sa.Date))
sa.Table("claims",metadata,col("id",sa.Integer,primary_key=True),col("uuid",sa.String(36),unique=True,index=True,nullable=False),col("legacy_claim_key",sa.String(80),unique=True),col("patient_id",sa.Integer,sa.ForeignKey("patients.id"),index=True,nullable=False),col("encounter_id",sa.Integer,sa.ForeignKey("encounters.id"),index=True,nullable=False),col("coverage_id",sa.Integer,sa.ForeignKey("coverages.id")),col("status",sa.String(30),nullable=False),col("total",sa.Numeric(12,2),nullable=False),col("submitted_at",sa.DateTime(timezone=True)),col("created_at",sa.DateTime(timezone=True),nullable=False))
sa.Table("charges",metadata,col("id",sa.Integer,primary_key=True),col("uuid",sa.String(36),unique=True,index=True,nullable=False),col("legacy_billing_id",sa.Integer,unique=True),col("patient_id",sa.Integer,sa.ForeignKey("patients.id"),index=True,nullable=False),col("encounter_id",sa.Integer,sa.ForeignKey("encounters.id"),index=True,nullable=False),col("claim_id",sa.Integer,sa.ForeignKey("claims.id"),index=True),col("code_system",sa.String(15),nullable=False),col("code",sa.String(20),nullable=False),col("description",sa.String(255),nullable=False),col("units",sa.Integer,nullable=False),col("unit_price",sa.Numeric(12,2),nullable=False))
sa.Table("claim_payments",metadata,col("id",sa.Integer,primary_key=True),col("uuid",sa.String(36),unique=True,nullable=False),col("claim_id",sa.Integer,sa.ForeignKey("claims.id"),index=True,nullable=False),col("amount",sa.Numeric(12,2),nullable=False),col("method",sa.String(50),nullable=False),col("reference",sa.String(255)),col("posted_at",sa.DateTime(timezone=True),nullable=False))


def upgrade():metadata.create_all(bind=op.get_bind(),checkfirst=True)


def downgrade():metadata.drop_all(bind=op.get_bind(),checkfirst=True)
