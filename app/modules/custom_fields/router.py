import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant
from app.core.rbac import Permission, has_permission, require_permission
from app.modules.custom_fields.models import CustomFieldDefinition
from app.modules.custom_fields.schemas import (
    CustomFieldReportResponse,
    EntitySearchRequest,
    EntitySearchResponse,
    EntityType,
    FieldDefinitionCreate,
    FieldDefinitionResponse,
    FieldDefinitionUpdate,
    FieldValueResponse,
    FieldValuesUpdate,
)
from app.modules.custom_fields.service import CustomFieldService, definition_response


router = APIRouter()


@router.get("/definitions", response_model=list[FieldDefinitionResponse])
def list_definitions(
    entity_type: EntityType,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
):
    if include_inactive and not has_permission(tenant.role, Permission.CUSTOM_FIELDS_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")
    return [
        definition_response(row)
        for row in CustomFieldService(db).definitions(
            tenant.id, entity_type, include_inactive=include_inactive
        )
    ]


@router.post("/definitions", response_model=FieldDefinitionResponse, status_code=201)
def create_definition(
    payload: FieldDefinitionCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CUSTOM_FIELDS_MANAGE)),
):
    row = CustomFieldDefinition(
        tenant_id=tenant.id,
        created_by_id=tenant.user_id,
        updated_by_id=tenant.user_id,
        options_json=json.dumps(payload.options, ensure_ascii=False),
        **payload.model_dump(exclude={"options"}),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Custom field code already exists") from error
    db.refresh(row)
    return definition_response(row)


@router.patch("/definitions/{field_id}", response_model=FieldDefinitionResponse)
def update_definition(
    field_id: UUID,
    payload: FieldDefinitionUpdate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CUSTOM_FIELDS_MANAGE)),
):
    service = CustomFieldService(db)
    row = service.definition(tenant.id, field_id)
    if row.version != payload.version:
        raise HTTPException(
            status_code=409,
            detail={"message": "Version conflict", "current_version": row.version},
        )
    data = payload.model_dump(exclude_unset=True, exclude={"version"})
    if "options" in data:
        if row.field_type not in {"select", "multi_select"} and data["options"]:
            raise HTTPException(status_code=422, detail="Options are only valid for select fields")
        removed = set(row.options) - set(data.pop("options"))
        if removed:
            values = db.query(service_value_model()).filter(
                service_value_model().tenant_id == tenant.id,
                service_value_model().field_id == row.id,
            ).all()
            if any(_uses_removed_option(row.field_type, value, removed) for value in values):
                raise HTTPException(status_code=422, detail="An option is still used by CRM records")
        row.options_json = json.dumps(payload.options, ensure_ascii=False)
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_by_id = tenant.user_id
    db.commit()
    db.refresh(row)
    return definition_response(row)


@router.get("/values/{entity_type}/{entity_id}", response_model=list[FieldValueResponse])
def get_values(
    entity_type: EntityType,
    entity_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
):
    return CustomFieldService(db).values(tenant.id, entity_type, entity_id)


@router.put("/values/{entity_type}/{entity_id}", response_model=list[FieldValueResponse])
def update_values(
    entity_type: EntityType,
    entity_id: UUID,
    payload: FieldValuesUpdate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
):
    return CustomFieldService(db).update_values(tenant, entity_type, entity_id, payload)


@router.post("/search/{entity_type}", response_model=EntitySearchResponse)
def search_entities(
    entity_type: EntityType,
    payload: EntitySearchRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
):
    ids = CustomFieldService(db).matching_ids(tenant.id, entity_type, payload.filters)
    return EntitySearchResponse(entity_type=entity_type, entity_ids=ids, matched=len(ids))


@router.get("/reports/{entity_type}/{field_id}", response_model=CustomFieldReportResponse)
def custom_field_report(
    entity_type: EntityType,
    field_id: UUID,
    metric: Annotated[str, Query(pattern="^(count|sum|avg)$")] = "count",
    measure: str | None = None,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
):
    if metric != "count" and (entity_type != "deals" or measure != "amount"):
        raise HTTPException(status_code=422, detail="sum/avg support deal amount only")
    field, buckets = CustomFieldService(db).report(
        tenant.id, entity_type, field_id, metric, measure
    )
    return CustomFieldReportResponse(
        entity_type=entity_type,
        group_field=definition_response(field),
        metric=metric,
        measure=measure,
        buckets=buckets,
        generated_at=datetime.now(timezone.utc),
    )


def service_value_model():
    from app.modules.custom_fields.models import CustomFieldValue

    return CustomFieldValue


def _uses_removed_option(field_type: str, row, removed: set[str]) -> bool:
    if field_type == "select":
        return row.text_value in removed
    if field_type == "multi_select":
        return bool(set(json.loads(row.json_value or "[]")) & removed)
    return False
