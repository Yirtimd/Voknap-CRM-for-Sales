import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentTenant
from app.core.rbac import require_object_owner
from app.modules.custom_fields.models import CustomFieldDefinition, CustomFieldValue
from app.modules.custom_fields.schemas import (
    CustomFieldFilter,
    FieldDefinitionResponse,
    FieldValueResponse,
    FieldValuesUpdate,
)
from app.modules.sales.models import Company, Contact, Deal, Lead, Task


ENTITY_MODELS = {
    "companies": Company,
    "contacts": Contact,
    "leads": Lead,
    "deals": Deal,
    "tasks": Task,
}
OWNER_FIELDS = {
    "companies": "owner_id",
    "contacts": "owner_id",
    "leads": "owner_id",
    "deals": "owner_id",
    "tasks": "assigned_to_id",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def definition_response(row: CustomFieldDefinition) -> FieldDefinitionResponse:
    return FieldDefinitionResponse(
        id=row.id,
        entity_type=row.entity_type,
        code=row.code,
        label=row.label,
        description=row.description,
        field_type=row.field_type,
        options=row.options,
        is_required=row.is_required,
        is_filterable=row.is_filterable,
        is_reportable=row.is_reportable,
        is_active=row.is_active,
        sort_order=row.sort_order,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class CustomFieldService:
    def __init__(self, db: Session):
        self.db = db

    def definitions(
        self, tenant_id: UUID, entity_type: str, *, include_inactive: bool = False
    ) -> list[CustomFieldDefinition]:
        query = self.db.query(CustomFieldDefinition).filter(
            CustomFieldDefinition.tenant_id == tenant_id,
            CustomFieldDefinition.entity_type == entity_type,
        )
        if not include_inactive:
            query = query.filter(CustomFieldDefinition.is_active.is_(True))
        return query.order_by(CustomFieldDefinition.sort_order, CustomFieldDefinition.label).all()

    def definition(
        self, tenant_id: UUID, field_id: UUID, entity_type: str | None = None
    ) -> CustomFieldDefinition:
        query = self.db.query(CustomFieldDefinition).filter(
            CustomFieldDefinition.tenant_id == tenant_id,
            CustomFieldDefinition.id == field_id,
        )
        if entity_type is not None:
            query = query.filter(CustomFieldDefinition.entity_type == entity_type)
        row = query.one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Custom field not found")
        return row

    def entity(self, tenant_id: UUID, entity_type: str, entity_id: UUID):
        model = ENTITY_MODELS[entity_type]
        row = (
            self.db.query(model)
            .filter(model.tenant_id == tenant_id, model.id == entity_id)
            .execution_options(include_deleted=True, include_archived=True)
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="CRM object not found")
        return row

    def require_write(self, tenant: CurrentTenant, entity_type: str, entity: Any) -> None:
        require_object_owner(
            tenant.role,
            tenant.user_id,
            getattr(entity, OWNER_FIELDS[entity_type]),
        )

    def values(
        self, tenant_id: UUID, entity_type: str, entity_id: UUID
    ) -> list[FieldValueResponse]:
        self.entity(tenant_id, entity_type, entity_id)
        definitions = self.definitions(tenant_id, entity_type)
        rows = (
            self.db.query(CustomFieldValue)
            .filter(
                CustomFieldValue.tenant_id == tenant_id,
                CustomFieldValue.entity_type == entity_type,
                CustomFieldValue.entity_id == entity_id,
            )
            .all()
        )
        by_field = {row.field_id: row for row in rows}
        return [self._value_response(field, by_field.get(field.id)) for field in definitions]

    def update_values(
        self,
        tenant: CurrentTenant,
        entity_type: str,
        entity_id: UUID,
        payload: FieldValuesUpdate,
    ) -> list[FieldValueResponse]:
        entity = self.entity(tenant.id, entity_type, entity_id)
        self.require_write(tenant, entity_type, entity)
        definitions = self.definitions(tenant.id, entity_type)
        by_id = {field.id: field for field in definitions}
        if len({item.field_id for item in payload.values}) != len(payload.values):
            raise HTTPException(status_code=422, detail="A field can be submitted only once")

        existing = (
            self.db.query(CustomFieldValue)
            .filter(
                CustomFieldValue.tenant_id == tenant.id,
                CustomFieldValue.entity_type == entity_type,
                CustomFieldValue.entity_id == entity_id,
            )
            .all()
        )
        values_by_field = {row.field_id: row for row in existing}
        for item in payload.values:
            field = by_id.get(item.field_id)
            if field is None:
                raise HTTPException(status_code=404, detail="Active custom field not found")
            row = values_by_field.get(item.field_id)
            current_version = row.version if row else 0
            if item.version != current_version:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"message": "Version conflict", "current_version": current_version},
                )
            normalized = self._normalize(field, item.value)
            if row is None:
                row = CustomFieldValue(
                    tenant_id=tenant.id,
                    field_id=field.id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    updated_by_id=tenant.user_id,
                )
                self.db.add(row)
                values_by_field[field.id] = row
            self._assign(row, field.field_type, normalized)
            row.updated_by_id = tenant.user_id
            row.updated_at = utc_now()

        for field in definitions:
            if field.is_required:
                row = values_by_field.get(field.id)
                if row is None or self._read_value(field, row) in (None, "", []):
                    raise HTTPException(
                        status_code=422,
                        detail=f"Required custom field is empty: {field.label}",
                    )
        self.db.commit()
        return self.values(tenant.id, entity_type, entity_id)

    def matching_ids(
        self, tenant_id: UUID, entity_type: str, filters: list[CustomFieldFilter]
    ) -> list[UUID]:
        definitions = {field.id: field for field in self.definitions(tenant_id, entity_type)}
        candidates: set[UUID] | None = None
        for item in filters:
            field = definitions.get(item.field_id)
            if field is None or not field.is_filterable:
                raise HTTPException(status_code=404, detail="Filterable custom field not found")
            expected = None if item.operator == "is_empty" else self._normalize(field, item.value)
            rows = (
                self.db.query(CustomFieldValue)
                .filter(
                    CustomFieldValue.tenant_id == tenant_id,
                    CustomFieldValue.field_id == field.id,
                    CustomFieldValue.entity_type == entity_type,
                )
                .all()
            )
            matched = {
                row.entity_id
                for row in rows
                if self._matches(self._read_value(field, row), item.operator, expected)
            }
            if item.operator == "is_empty":
                model = ENTITY_MODELS[entity_type]
                all_ids = {item[0] for item in self.db.query(model.id).filter(model.tenant_id == tenant_id)}
                matched |= all_ids - {row.entity_id for row in rows}
            candidates = matched if candidates is None else candidates & matched
        return sorted(candidates or set(), key=str)

    def report(
        self, tenant_id: UUID, entity_type: str, field_id: UUID, metric: str, measure: str | None
    ) -> tuple[CustomFieldDefinition, list[dict[str, Any]]]:
        field = self.definition(tenant_id, field_id, entity_type)
        if not field.is_reportable:
            raise HTTPException(status_code=422, detail="Custom field is not reportable")
        model = ENTITY_MODELS[entity_type]
        entities = self.db.query(model).filter(model.tenant_id == tenant_id).all()
        rows = (
            self.db.query(CustomFieldValue)
            .filter(
                CustomFieldValue.tenant_id == tenant_id,
                CustomFieldValue.field_id == field.id,
                CustomFieldValue.entity_type == entity_type,
            )
            .all()
        )
        value_by_entity = {row.entity_id: self._read_value(field, row) for row in rows}
        buckets: dict[str, dict[str, Any]] = {}
        for entity in entities:
            value = value_by_entity.get(entity.id)
            keys = value if field.field_type == "multi_select" and value else [value]
            if not isinstance(keys, list):
                keys = [keys]
            for raw_key in keys or [None]:
                key = "Не заполнено" if raw_key in (None, "") else str(raw_key)
                bucket = buckets.setdefault(key, {"label": key, "value": 0.0, "count": 0})
                amount = 1.0
                if metric in {"sum", "avg"}:
                    amount = float(getattr(entity, measure or "", 0) or 0)
                bucket["value"] += amount
                bucket["count"] += 1
        result = []
        for bucket in buckets.values():
            if metric == "avg":
                bucket["value"] = round(bucket["value"] / bucket["count"], 2)
            elif metric == "count":
                bucket["value"] = bucket["count"]
            result.append(bucket)
        return field, sorted(result, key=lambda item: (-item["value"], item["label"]))

    def _value_response(
        self, field: CustomFieldDefinition, row: CustomFieldValue | None
    ) -> FieldValueResponse:
        return FieldValueResponse(
            field=definition_response(field),
            value=self._read_value(field, row) if row else None,
            version=row.version if row else 0,
            updated_at=row.updated_at if row else None,
        )

    def _normalize(self, field: CustomFieldDefinition, value: Any) -> Any:
        if value is None or value == "":
            if field.is_required:
                raise HTTPException(status_code=422, detail=f"{field.label} is required")
            return None
        try:
            if field.field_type == "text":
                value = str(value).strip()
                if len(value) > 10_000:
                    raise ValueError
                return value
            if field.field_type == "number":
                number = Decimal(str(value))
                if not math.isfinite(float(number)):
                    raise ValueError
                return number
            if field.field_type == "date":
                return value if isinstance(value, date) else date.fromisoformat(str(value))
            if field.field_type == "datetime":
                if isinstance(value, datetime):
                    return value
                return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if field.field_type == "boolean":
                if not isinstance(value, bool):
                    raise ValueError
                return value
            if field.field_type == "select":
                if not isinstance(value, str) or value not in field.options:
                    raise ValueError
                return value
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError
            normalized = list(dict.fromkeys(value))
            if len(normalized) > 100 or any(item not in field.options for item in normalized):
                raise ValueError
            return normalized
        except (ValueError, TypeError, InvalidOperation) as error:
            raise HTTPException(status_code=422, detail=f"Invalid value for {field.label}") from error

    @staticmethod
    def _assign(row: CustomFieldValue, field_type: str, value: Any) -> None:
        for name in ("text_value", "number_value", "date_value", "datetime_value", "boolean_value", "json_value"):
            setattr(row, name, None)
        column = {
            "text": "text_value",
            "number": "number_value",
            "date": "date_value",
            "datetime": "datetime_value",
            "boolean": "boolean_value",
            "select": "text_value",
            "multi_select": "json_value",
        }[field_type]
        setattr(row, column, json.dumps(value, ensure_ascii=False) if field_type == "multi_select" else value)

    @staticmethod
    def _read_value(field: CustomFieldDefinition, row: CustomFieldValue) -> Any:
        if field.field_type in {"text", "select"}:
            return row.text_value
        if field.field_type == "number":
            return float(row.number_value) if row.number_value is not None else None
        if field.field_type == "date":
            return row.date_value
        if field.field_type == "datetime":
            return row.datetime_value
        if field.field_type == "boolean":
            return row.boolean_value
        return json.loads(row.json_value) if row.json_value else []

    @staticmethod
    def _matches(actual: Any, operator: str, expected: Any) -> bool:
        if operator == "is_empty":
            return actual in (None, "", [])
        if operator == "contains":
            if isinstance(actual, list):
                return expected in actual
            return str(expected).casefold() in str(actual or "").casefold()
        if operator == "eq":
            return actual == expected
        if operator == "neq":
            return actual != expected
        if actual is None:
            return False
        return {
            "gt": actual > expected,
            "gte": actual >= expected,
            "lt": actual < expected,
            "lte": actual <= expected,
        }[operator]
