import json
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import tenant_table_args


ENTITY_CHECK = "entity_type IN ('companies', 'contacts', 'leads', 'deals', 'tasks')"
FIELD_TYPE_CHECK = (
    "field_type IN ('text', 'number', 'date', 'datetime', 'boolean', 'select', 'multi_select')"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CustomFieldDefinition(Base):
    __tablename__ = "custom_field_definitions"
    __table_args__ = tenant_table_args(
        "custom_field_definitions",
        membership_columns=("created_by_id", "updated_by_id"),
        extra=(
            UniqueConstraint(
                "tenant_id", "entity_type", "code", name="uq_custom_field_definitions_code"
            ),
            CheckConstraint(ENTITY_CHECK, name="ck_custom_field_definitions_entity"),
            CheckConstraint(FIELD_TYPE_CHECK, name="ck_custom_field_definitions_type"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    field_type: Mapped[str] = mapped_column(String(30), nullable=False)
    options_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_filterable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_reportable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    created_by_id: Mapped[UUID] = mapped_column(nullable=False)
    updated_by_id: Mapped[UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __mapper_args__ = {"version_id_col": version}

    @property
    def options(self) -> list[str]:
        try:
            value = json.loads(self.options_json)
        except (TypeError, json.JSONDecodeError):
            return []
        return [str(item) for item in value] if isinstance(value, list) else []


class CustomFieldValue(Base):
    __tablename__ = "custom_field_values"
    __table_args__ = tenant_table_args(
        "custom_field_values",
        relations=(("field_id", "custom_field_definitions"),),
        membership_columns=("updated_by_id",),
        extra=(
            UniqueConstraint(
                "tenant_id", "field_id", "entity_id", name="uq_custom_field_values_entity"
            ),
            CheckConstraint(ENTITY_CHECK, name="ck_custom_field_values_entity_type"),
            Index(
                "ix_custom_field_values_text_lookup",
                "tenant_id",
                "field_id",
                "text_value",
            ),
            Index(
                "ix_custom_field_values_number_lookup",
                "tenant_id",
                "field_id",
                "number_value",
            ),
            Index(
                "ix_custom_field_values_date_lookup",
                "tenant_id",
                "field_id",
                "date_value",
            ),
            Index(
                "ix_custom_field_values_boolean_lookup",
                "tenant_id",
                "field_id",
                "boolean_value",
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    field_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    text_value: Mapped[str | None] = mapped_column(Text)
    number_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    date_value: Mapped[date | None] = mapped_column(Date)
    datetime_value: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    json_value: Mapped[str | None] = mapped_column(Text)
    updated_by_id: Mapped[UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __mapper_args__ = {"version_id_col": version}
