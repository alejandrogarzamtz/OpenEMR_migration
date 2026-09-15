"""Add safe settings, localization catalogs and versioned templates."""
from alembic import op
import sqlalchemy as sa

revision="20261109_0070";down_revision="20261108_0069";branch_labels=None;depends_on=None


def upgrade():
    tables=set(sa.inspect(op.get_bind()).get_table_names())
    if "system_settings" not in tables:
        op.create_table("system_settings",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("key",sa.String(120),nullable=False),sa.Column("category",sa.String(40),nullable=False),sa.Column("value_type",sa.String(20),nullable=False),sa.Column("value",sa.JSON(),nullable=False),sa.Column("description",sa.String(500),nullable=False),sa.Column("version",sa.Integer(),nullable=False),sa.Column("updated_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.Column("legacy_name",sa.String(63),nullable=True),sa.Column("legacy_index",sa.Integer(),nullable=True),sa.Column("legacy_payload",sa.JSON(),nullable=True))
        for column in ("uuid","key","category","legacy_name"):op.create_index(f"ix_system_settings_{column}","system_settings",[column],unique=column in {"uuid","key"})
    if "locale_catalogs" not in tables:
        op.create_table("locale_catalogs",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("code",sa.String(16),nullable=False),sa.Column("name",sa.String(100),nullable=False),sa.Column("rtl",sa.Boolean(),nullable=False),sa.Column("active",sa.Boolean(),nullable=False),sa.Column("legacy_language_id",sa.Integer(),nullable=True,unique=True),sa.Column("legacy_payload",sa.JSON(),nullable=True))
        for column in ("uuid","code","active"):op.create_index(f"ix_locale_catalogs_{column}","locale_catalogs",[column],unique=column in {"uuid","code"})
    if "translations" not in tables:
        op.create_table("translations",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("locale_id",sa.Integer(),sa.ForeignKey("locale_catalogs.id"),nullable=False),sa.Column("key",sa.String(500),nullable=False),sa.Column("value",sa.Text(),nullable=False),sa.Column("customized",sa.Boolean(),nullable=False),sa.Column("updated_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.Column("legacy_definition_id",sa.Integer(),nullable=True,unique=True),sa.Column("legacy_payload",sa.JSON(),nullable=True),sa.UniqueConstraint("locale_id","key",name="uq_translation_locale_key"))
        for column in ("uuid","locale_id","key","customized"):op.create_index(f"ix_translations_{column}","translations",[column],unique=column=="uuid")
    if "content_templates" not in tables:
        op.create_table("content_templates",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("key",sa.String(120),nullable=False),sa.Column("locale_code",sa.String(16),nullable=False),sa.Column("version",sa.Integer(),nullable=False),sa.Column("name",sa.String(255),nullable=False),sa.Column("category",sa.String(40),nullable=False),sa.Column("subject",sa.String(255),nullable=True),sa.Column("content",sa.Text(),nullable=False),sa.Column("content_type",sa.String(50),nullable=False),sa.Column("allowed_variables",sa.JSON(),nullable=False),sa.Column("active",sa.Boolean(),nullable=False),sa.Column("created_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("supersedes_id",sa.Integer(),sa.ForeignKey("content_templates.id"),nullable=True),sa.Column("legacy_template_id",sa.Integer(),nullable=True,unique=True),sa.Column("legacy_payload",sa.JSON(),nullable=True),sa.UniqueConstraint("key","locale_code","version",name="uq_content_template_version"))
        for column in ("uuid","key","locale_code","category","active"):op.create_index(f"ix_content_templates_{column}","content_templates",[column],unique=column=="uuid")


def downgrade():
    for table in ("content_templates","translations","locale_catalogs","system_settings"):op.drop_table(table)
