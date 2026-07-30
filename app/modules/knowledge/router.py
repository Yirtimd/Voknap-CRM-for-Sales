from uuid import UUID
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import CurrentTenant, get_current_tenant
from app.core.rbac import Permission, require_permission
from app.modules.knowledge.files import KnowledgeFileError
from app.modules.knowledge.models import KnowledgeDocument
from app.modules.knowledge.schemas import (
    AskRequest,
    AskResponse,
    CitationResponse,
    DocumentCreate,
    DocumentResponse,
    KnowledgeScope,
    QueryFeedbackRequest,
    QueryFeedbackResponse,
    SearchRequest,
    SearchResultResponse,
)
from app.modules.knowledge.service import KnowledgeService
from app.modules.knowledge.storage import open_knowledge_file
from app.modules.sales.authorization import require_company_write_access
from app.modules.sales.models import CompanyFile


router = APIRouter()


@router.post("/documents/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=255),
    scope: KnowledgeScope = Form(default="global"),
    company_id: UUID | None = Form(default=None),
    deal_id: UUID | None = Form(default=None),
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
) -> DocumentResponse:
    if company_id is not None:
        require_company_write_access(db, tenant, company_id)
    data = await file.read(settings.knowledge_max_upload_bytes + 1)
    await file.close()
    service = KnowledgeService(db)
    try:
        document = service.create_document_from_upload(
            tenant_id=tenant.id,
            user_id=tenant.user_id,
            filename=file.filename or "document",
            content_type=file.content_type,
            data=data,
            title=title,
            scope=scope,
            company_id=company_id,
            deal_id=deal_id,
        )
    except (KnowledgeFileError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return _document_response(document)


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
) -> DocumentResponse:
    if payload.company_id is not None:
        require_company_write_access(db, tenant, payload.company_id)
    service = KnowledgeService(db)
    try:
        document = service.create_document(
            tenant_id=tenant.id,
            title=payload.title,
            text=payload.text,
            source_type=payload.source_type,
            company_id=payload.company_id,
            deal_id=payload.deal_id,
            file_id=payload.file_id,
            visibility=payload.visibility,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return _document_response(document)


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(
    scope: KnowledgeScope = "global",
    company_id: UUID | None = None,
    deal_id: UUID | None = None,
    include_global: bool = False,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[DocumentResponse]:
    service = KnowledgeService(db)
    try:
        documents = service.list_documents(
            tenant.id,
            scope=scope,
            company_id=company_id,
            deal_id=deal_id,
            include_global=include_global,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return [_document_response(document) for document in documents]


@router.post("/companies/{company_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_company_document(
    company_id: UUID,
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.KNOWLEDGE_WRITE)),
) -> DocumentResponse:
    require_company_write_access(db, tenant, company_id)
    service = KnowledgeService(db)
    try:
        document = service.create_document(
            tenant_id=tenant.id,
            title=payload.title,
            text=payload.text,
            source_type=payload.source_type,
            company_id=company_id,
            deal_id=payload.deal_id,
            file_id=payload.file_id,
            visibility="deal" if payload.deal_id else "company",
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return _document_response(document)


@router.get("/companies/{company_id}/documents", response_model=list[DocumentResponse])
def list_company_documents(
    company_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[DocumentResponse]:
    service = KnowledgeService(db)
    try:
        documents = service.list_documents(tenant.id, scope="company", company_id=company_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return [_document_response(document) for document in documents]


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
):
    document = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.id == document_id, KnowledgeDocument.tenant_id == tenant.id)
        .one_or_none()
    )
    if document is None or document.file_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found")
    stored_file = (
        db.query(CompanyFile)
        .filter(CompanyFile.id == document.file_id, CompanyFile.tenant_id == tenant.id)
        .one_or_none()
    )
    if stored_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found")
    try:
        stored_object = open_knowledge_file(stored_file.storage_backend, stored_file.storage_key)
    except KnowledgeFileError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if stored_object.path is not None:
        return FileResponse(
            stored_object.path,
            media_type=stored_file.mime_type,
            filename=stored_file.name,
        )
    return StreamingResponse(
        stored_object.stream,
        media_type=stored_object.content_type or stored_file.mime_type,
        headers={
            "Content-Length": str(stored_object.content_length),
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(stored_file.name)}",
        },
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> DocumentResponse:
    document = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.id == document_id, KnowledgeDocument.tenant_id == tenant.id)
        .one_or_none()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _document_response(document)


@router.post("/search", response_model=list[SearchResultResponse])
def search(
    payload: SearchRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> list[SearchResultResponse]:
    service = KnowledgeService(db)
    try:
        results = service.search(
            tenant_id=tenant.id,
            query=payload.query,
            limit=payload.limit,
            scope=payload.scope,
            company_id=payload.company_id,
            deal_id=payload.deal_id,
            document_id=payload.document_id,
            include_global=payload.include_global,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return [
        SearchResultResponse(
            chunk_id=item.chunk.id,
            document_id=item.document.id,
            document_title=item.document.title,
            document_scope=item.document.visibility,
            company_id=item.document.company_id,
            deal_id=item.document.deal_id,
            page_number=item.chunk.page_number,
            text=item.chunk.text,
            score=item.score,
            chunk_index=item.chunk.chunk_index,
            retrieval_method=item.retrieval_method,
        )
        for item in results
    ]


@router.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.AI_USE)),
) -> AskResponse:
    service = KnowledgeService(db)
    try:
        result = service.answer(
            tenant_id=tenant.id,
            user_id=tenant.user_id,
            question=payload.question,
            limit=payload.limit,
            scope=payload.scope,
            company_id=payload.company_id,
            deal_id=payload.deal_id,
            document_id=payload.document_id,
            include_global=payload.include_global,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return AskResponse(
        query_id=result.query.id,
        answer=result.answer,
        citations=[
            CitationResponse(
                chunk_id=item.chunk.id,
                document_id=item.document.id,
                document_title=item.document.title,
                document_scope=item.document.visibility,
                company_id=item.document.company_id,
                deal_id=item.document.deal_id,
                chunk_index=item.chunk.chunk_index,
                page_number=item.chunk.page_number,
                text=item.chunk.text,
                score=item.score,
                retrieval_method=item.retrieval_method,
            )
            for item in result.chunks
        ],
        scope=payload.scope,
        company_id=payload.company_id,
        deal_id=payload.deal_id,
        document_id=payload.document_id,
        include_global=payload.include_global,
        retrieval_mode=result.query.retrieval_mode,
    )


@router.post(
    "/queries/{query_id}/feedback",
    response_model=QueryFeedbackResponse,
)
def save_query_feedback(
    query_id: UUID,
    payload: QueryFeedbackRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.AI_USE)),
) -> QueryFeedbackResponse:
    query_row = KnowledgeService(db).save_feedback(
        tenant.id,
        tenant.user_id,
        query_id,
        payload.rating,
        payload.comment,
    )
    if query_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge query not found")
    return QueryFeedbackResponse(
        query_id=query_row.id,
        rating=query_row.feedback_rating,
        comment=query_row.feedback_comment,
    )


def _document_response(document: KnowledgeDocument) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        company_id=document.company_id,
        deal_id=document.deal_id,
        file_id=document.file_id,
        title=document.title,
        source_type=document.source_type,
        visibility=document.visibility,
        status=document.status,
        created_at=document.created_at,
        chunks_count=len(document.chunks),
        download_url=f"/knowledge/documents/{document.id}/download" if document.file_id else None,
        extraction_method=document.extraction_method,
        source_pages=document.source_pages,
    )
