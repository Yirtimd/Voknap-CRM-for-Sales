import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.knowledge.files import parse_knowledge_file
from app.modules.knowledge.models import (
    PGVECTOR_DIMENSIONS,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeQuery,
)
from app.modules.knowledge.storage import delete_knowledge_file, store_knowledge_file
from app.modules.sales.models import Company, CompanyFile, Deal


@dataclass
class RankedChunk:
    chunk: KnowledgeChunk
    document: KnowledgeDocument
    score: float
    retrieval_method: str = "hybrid"


@dataclass
class KnowledgeAnswer:
    answer: str
    chunks: list[RankedChunk]
    query: KnowledgeQuery


class EmbeddingService:
    def __init__(self, expected_dimensions: int | None = None):
        self.dimensions = expected_dimensions or settings.embedding_dimensions

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        provider = settings.embedding_provider.lower().strip()
        if provider in {"openai", "openai_compatible"}:
            from openai import OpenAI

            api_key = settings.embedding_api_key or (
                settings.openai_api_key if provider == "openai" else settings.llm_api_key
            )
            if not api_key:
                raise RuntimeError(
                    "Embedding API key is not configured. Set EMBEDDING_API_KEY "
                    "or the provider fallback key in .env."
                )

            base_url = settings.embedding_base_url
            if provider == "openai_compatible" and not base_url:
                base_url = settings.llm_base_url
            if provider == "openai_compatible" and not base_url:
                raise RuntimeError(
                    "Embedding base URL is not configured. Set EMBEDDING_BASE_URL "
                    "or LLM_BASE_URL in .env."
                )
            if base_url:
                base_url = base_url.rstrip("/")
                if base_url.endswith("/embeddings"):
                    base_url = base_url.removesuffix("/embeddings")

            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=20.0,
                max_retries=1,
            )
            response = client.embeddings.create(model=settings.embedding_model, input=texts)
            vectors = [
                item.embedding for item in sorted(response.data, key=lambda item: item.index)
            ]
            self._validate_vectors(vectors)
            return vectors

        if provider == "local":
            return [self._local_embed(text) for text in texts]

        raise RuntimeError(f"Unsupported embedding provider: {settings.embedding_provider}")

    def _validate_vectors(self, vectors: list[list[float]]) -> None:
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise RuntimeError(
                    "Embedding provider returned "
                    f"{len(vector)} dimensions; expected {self.dimensions} for the active "
                    "pgvector schema. Update EMBEDDING_DIMENSIONS and migrate/reindex "
                    "before changing embedding models."
                )
            if not all(math.isfinite(value) for value in vector):
                raise RuntimeError("Embedding provider returned a non-finite vector value")

    def metadata(self, dimensions: int) -> dict[str, str | int]:
        provider = settings.embedding_provider.lower().strip()
        return {
            "embedding_provider": provider,
            "embedding_model": settings.embedding_model if provider != "local" else "local-hash-v1",
            "embedding_version": settings.embedding_version,
            "embedding_dimensions": dimensions,
        }

    def _local_embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        words = re.findall(r"[\wа-яА-ЯёЁ]+", text.lower())
        for word in words:
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class KnowledgeService:
    def __init__(self, db: Session):
        self.db = db
        if settings.embedding_dimensions != PGVECTOR_DIMENSIONS:
            raise RuntimeError(
                f"EMBEDDING_DIMENSIONS={settings.embedding_dimensions} does not match "
                f"the active pgvector schema vector({PGVECTOR_DIMENSIONS}). "
                "Migrate and reindex before changing embedding dimensions."
            )
        self.embedding_service = EmbeddingService(expected_dimensions=PGVECTOR_DIMENSIONS)

    def create_document(
        self,
        tenant_id: UUID,
        title: str,
        text: str,
        source_type: str = "text",
        company_id: UUID | None = None,
        deal_id: UUID | None = None,
        file_id: UUID | None = None,
        visibility: str = "global",
        extraction_method: str = "manual",
        source_pages: int | None = None,
        page_texts: tuple[str, ...] | None = None,
        commit: bool = True,
    ) -> KnowledgeDocument:
        self._validate_scope_context(tenant_id, visibility, company_id, deal_id)
        document = KnowledgeDocument(
            tenant_id=tenant_id,
            company_id=company_id,
            deal_id=deal_id,
            file_id=file_id,
            title=title,
            source_type=source_type,
            visibility=visibility,
            extraction_method=extraction_method,
            source_pages=source_pages,
        )
        self.db.add(document)
        self.db.flush()

        chunk_specs = self._split_source(text, page_texts)
        for offset in range(0, len(chunk_specs), 32):
            chunk_batch = chunk_specs[offset : offset + 32]
            embeddings = self.embedding_service.embed_many([item[0] for item in chunk_batch])
            if len(embeddings) != len(chunk_batch):
                raise RuntimeError("Embedding provider returned an unexpected vector count")
            for index, ((chunk_text, page_number), embedding) in enumerate(
                zip(chunk_batch, embeddings, strict=True),
                start=offset,
            ):
                self.db.add(
                    KnowledgeChunk(
                        tenant_id=tenant_id,
                        document_id=document.id,
                        scope=visibility,
                        company_id=company_id,
                        deal_id=deal_id,
                        chunk_index=index,
                        page_number=page_number,
                        text=chunk_text,
                        embedding_vector=embedding,
                        **self.embedding_service.metadata(len(embedding)),
                        token_estimate=max(1, len(chunk_text) // 4),
                    )
                )

        if commit:
            self.db.commit()
            self.db.refresh(document)
        return document

    def create_document_from_upload(
        self,
        tenant_id: UUID,
        user_id: UUID,
        filename: str,
        content_type: str | None,
        data: bytes,
        title: str | None = None,
        scope: str = "global",
        company_id: UUID | None = None,
        deal_id: UUID | None = None,
    ) -> KnowledgeDocument:
        self._validate_scope_context(tenant_id, scope, company_id, deal_id)
        parsed = parse_knowledge_file(filename, content_type, data)
        storage_backend, storage_key = store_knowledge_file(
            tenant_id,
            parsed.filename,
            data,
            parsed.mime_type,
        )
        try:
            company_file = CompanyFile(
                tenant_id=tenant_id,
                company_id=company_id,
                deal_id=deal_id,
                uploaded_by_id=user_id,
                name=parsed.filename,
                file_type=parsed.extension,
                mime_type=parsed.mime_type,
                file_size=len(data),
                storage_backend=storage_backend,
                storage_key=storage_key,
            )
            self.db.add(company_file)
            self.db.flush()
            document = self.create_document(
                tenant_id=tenant_id,
                title=(title or "").strip() or Path(parsed.filename).stem,
                text=parsed.text,
                source_type=parsed.extension,
                company_id=company_id,
                deal_id=deal_id,
                file_id=company_file.id,
                visibility=scope,
                extraction_method=parsed.extraction_method,
                source_pages=parsed.source_pages,
                page_texts=parsed.pages,
                commit=False,
            )
            company_file.download_url = f"/knowledge/documents/{document.id}/download"
            self.db.commit()
            self.db.refresh(document)
            return document
        except Exception:
            self.db.rollback()
            try:
                delete_knowledge_file(storage_backend, storage_key)
            except Exception:
                pass
            raise

    def list_documents(
        self,
        tenant_id: UUID,
        scope: str = "global",
        company_id: UUID | None = None,
        deal_id: UUID | None = None,
        include_global: bool = False,
    ) -> list[KnowledgeDocument]:
        self._validate_scope_context(tenant_id, scope, company_id, deal_id)
        query = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.tenant_id == tenant_id)
        query = query.filter(self._document_scope_filter(scope, company_id, deal_id, include_global))
        return query.order_by(KnowledgeDocument.created_at.desc()).all()

    def search(
        self,
        tenant_id: UUID,
        query: str,
        limit: int = 6,
        scope: str = "global",
        company_id: UUID | None = None,
        deal_id: UUID | None = None,
        document_id: UUID | None = None,
        include_global: bool = False,
    ) -> list[RankedChunk]:
        self._validate_scope_context(tenant_id, scope, company_id, deal_id)
        self._validate_document_context(
            tenant_id,
            document_id,
            scope,
            company_id,
            deal_id,
            include_global,
        )
        query_embedding = self.embedding_service.embed(query)
        rows_query = (
            self.db.query(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .filter(
                KnowledgeChunk.tenant_id == tenant_id,
                KnowledgeDocument.status == "ready",
                self._chunk_scope_filter(scope, company_id, deal_id, include_global),
                self._embedding_identity_filter(len(query_embedding)),
            )
        )
        if document_id is not None:
            rows_query = rows_query.filter(KnowledgeChunk.document_id == document_id)

        if self.db.get_bind().dialect.name == "postgresql":
            distance = KnowledgeChunk.embedding_vector.cosine_distance(query_embedding)
            candidate_limit = min(100, max(20, limit * 4))
            vector_rows = (
                rows_query.add_columns(distance.label("distance"))
                .order_by(distance)
                .limit(candidate_limit)
                .all()
            )
            search_vector = func.to_tsvector("simple", KnowledgeChunk.text)
            search_query = func.websearch_to_tsquery("simple", query)
            lexical_rank = func.ts_rank_cd(search_vector, search_query)
            lexical_rows = (
                rows_query.add_columns(lexical_rank.label("lexical_rank"))
                .filter(search_vector.op("@@")(search_query))
                .order_by(lexical_rank.desc())
                .limit(candidate_limit)
                .all()
            )
            return self._merge_hybrid_results(
                query,
                query_embedding,
                vector_rows,
                lexical_rows,
                limit,
            )

        ranked: list[RankedChunk] = []
        for chunk, document in rows_query.all():
            semantic_score = self._cosine_similarity(query_embedding, chunk.embedding_vector)
            lexical_score = self._lexical_similarity(query, chunk.text)
            score = 0.7 * max(0.0, semantic_score) + 0.3 * lexical_score
            method = "hybrid" if semantic_score > 0 and lexical_score > 0 else (
                "semantic" if semantic_score > 0 else "lexical"
            )
            ranked.append(
                RankedChunk(
                    chunk=chunk,
                    document=document,
                    score=score,
                    retrieval_method=method,
                )
            )

        return sorted(ranked, key=lambda item: item.score, reverse=True)[:limit]

    def reindex_all(self, tenant_id: UUID | None = None, batch_size: int = 32) -> int:
        query = self.db.query(KnowledgeChunk).order_by(KnowledgeChunk.created_at, KnowledgeChunk.id)
        if tenant_id is not None:
            query = query.filter(KnowledgeChunk.tenant_id == tenant_id)
        chunks = query.all()
        try:
            for offset in range(0, len(chunks), batch_size):
                batch = chunks[offset : offset + batch_size]
                embeddings = self.embedding_service.embed_many([chunk.text for chunk in batch])
                if len(embeddings) != len(batch):
                    raise RuntimeError("Embedding provider returned an unexpected vector count")
                for chunk, embedding in zip(batch, embeddings, strict=True):
                    chunk.embedding_vector = embedding
                    for field, value in self.embedding_service.metadata(len(embedding)).items():
                        setattr(chunk, field, value)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return len(chunks)

    def answer(
        self,
        tenant_id: UUID,
        user_id: UUID,
        question: str,
        limit: int = 6,
        scope: str = "global",
        company_id: UUID | None = None,
        deal_id: UUID | None = None,
        document_id: UUID | None = None,
        include_global: bool = False,
    ) -> KnowledgeAnswer:
        ranked_chunks = self.search(
            tenant_id=tenant_id,
            query=question,
            limit=limit,
            scope=scope,
            company_id=company_id,
            deal_id=deal_id,
            document_id=document_id,
            include_global=include_global,
        )
        if not ranked_chunks or ranked_chunks[0].score <= 0.05:
            answer = "Не нашел подтвержденный ответ в выбранных источниках."
            query_row = self._save_query(
                tenant_id,
                user_id,
                question,
                answer,
                scope,
                company_id,
                deal_id,
                document_id,
                include_global,
                [],
            )
            return KnowledgeAnswer(answer=answer, chunks=[], query=query_row)

        answer = self._grounded_answer(question, ranked_chunks, scope)
        query_row = self._save_query(
            tenant_id,
            user_id,
            question,
            answer,
            scope,
            company_id,
            deal_id,
            document_id,
            include_global,
            ranked_chunks,
        )
        return KnowledgeAnswer(answer=answer, chunks=ranked_chunks, query=query_row)

    def _grounded_answer(self, question: str, ranked_chunks: list[RankedChunk], scope: str) -> str:
        llm_api_key = settings.llm_api_key or settings.openai_api_key
        if llm_api_key:
            from openai import OpenAI

            context = "\n\n".join(
                f"[{index + 1}] {item.document.title}\n{item.chunk.text}"
                for index, item in enumerate(ranked_chunks)
            )
            prompt = (
                f"Режим базы знаний: {scope}. Ответь только по переданному контексту. "
                "Не используй знания о других компаниях. Если ответа нет, прямо скажи об этом.\n\n"
                f"Вопрос: {question}\n\nКонтекст:\n{context}"
            )
            try:
                client = OpenAI(
                    api_key=llm_api_key,
                    base_url=settings.llm_base_url,
                    timeout=12.0,
                    max_retries=0,
                )
                if settings.llm_base_url:
                    response = client.chat.completions.create(
                        model=settings.llm_model,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    return response.choices[0].message.content or self._extractive_answer(ranked_chunks[0])

                response = client.responses.create(
                    model=settings.llm_model,
                    input=prompt,
                )
                return response.output_text or self._extractive_answer(ranked_chunks[0])
            except Exception:
                return self._extractive_answer(ranked_chunks[0], llm_unavailable=True)

        return self._extractive_answer(ranked_chunks[0])

    def _extractive_answer(self, best: RankedChunk, llm_unavailable: bool = False) -> str:
        prefix = "LLM сейчас недоступна. " if llm_unavailable else ""
        return (
            f"{prefix}Нашел наиболее близкий фрагмент в базе знаний. "
            f"Источник: {best.document.title}. "
            f"Фрагмент: {best.chunk.text[:700]}"
        )

    def _save_query(
        self,
        tenant_id: UUID,
        user_id: UUID,
        question: str,
        answer: str,
        scope: str,
        company_id: UUID | None,
        deal_id: UUID | None,
        document_id: UUID | None,
        include_global: bool,
        ranked_chunks: list[RankedChunk],
    ) -> KnowledgeQuery:
        sources = [
            {
                "document_id": str(item.document.id),
                "chunk_id": str(item.chunk.id),
                "page_number": item.chunk.page_number,
                "score": item.score,
                "retrieval_method": item.retrieval_method,
            }
            for item in ranked_chunks
        ]
        query_row = KnowledgeQuery(
            tenant_id=tenant_id,
            user_id=user_id,
            scope=scope,
            company_id=company_id,
            deal_id=deal_id,
            document_id=document_id,
            include_global=include_global,
            question=question,
            answer=answer,
            retrieval_mode="hybrid",
            sources_json=json.dumps(sources),
            top_score=ranked_chunks[0].score if ranked_chunks else None,
        )
        self.db.add(query_row)
        self.db.commit()
        self.db.refresh(query_row)
        return query_row

    def save_feedback(
        self,
        tenant_id: UUID,
        user_id: UUID,
        query_id: UUID,
        rating: str,
        comment: str | None,
    ) -> KnowledgeQuery | None:
        query_row = (
            self.db.query(KnowledgeQuery)
            .filter(
                KnowledgeQuery.id == query_id,
                KnowledgeQuery.tenant_id == tenant_id,
                KnowledgeQuery.user_id == user_id,
            )
            .one_or_none()
        )
        if query_row is None:
            return None
        query_row.feedback_rating = rating
        query_row.feedback_comment = (comment or "").strip() or None
        query_row.feedback_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(query_row)
        return query_row

    def _validate_scope_context(
        self,
        tenant_id: UUID,
        scope: str,
        company_id: UUID | None,
        deal_id: UUID | None,
    ) -> None:
        if scope not in {"global", "company", "deal"}:
            raise ValueError("Unknown knowledge scope")
        if scope == "global":
            if company_id is not None or deal_id is not None:
                raise ValueError("Global knowledge cannot receive company_id or deal_id")
            return
        if company_id is None:
            raise ValueError("Company knowledge requires company_id")
        company = (
            self.db.query(Company)
            .filter(Company.tenant_id == tenant_id, Company.id == company_id)
            .one_or_none()
        )
        if company is None:
            raise ValueError("Company does not belong to current workspace")
        if scope == "company":
            if deal_id is not None:
                raise ValueError("Company knowledge cannot receive deal_id; use deal scope")
            return
        if deal_id is None:
            raise ValueError("Deal knowledge requires deal_id")
        deal = (
            self.db.query(Deal)
            .filter(Deal.tenant_id == tenant_id, Deal.id == deal_id)
            .one_or_none()
        )
        if deal is None or deal.company_id != company_id:
            raise ValueError("Deal does not belong to selected company")

    def _document_scope_filter(
        self,
        scope: str,
        company_id: UUID | None,
        deal_id: UUID | None,
        include_global: bool,
    ):
        global_filter = KnowledgeDocument.visibility == "global"
        if scope == "global":
            return global_filter
        if scope == "company":
            scoped_filter = KnowledgeDocument.company_id == company_id
        else:
            scoped_filter = or_(
                KnowledgeDocument.deal_id == deal_id,
                and_(KnowledgeDocument.company_id == company_id, KnowledgeDocument.deal_id.is_(None)),
            )
        return or_(global_filter, scoped_filter) if include_global else scoped_filter

    def _validate_document_context(
        self,
        tenant_id: UUID,
        document_id: UUID | None,
        scope: str,
        company_id: UUID | None,
        deal_id: UUID | None,
        include_global: bool,
    ) -> None:
        if document_id is None:
            return
        scope_filter = self._document_scope_filter(
            scope,
            company_id,
            deal_id,
            include_global,
        )
        document = (
            self.db.query(KnowledgeDocument)
            .filter(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.status == "ready",
                scope_filter,
            )
            .one_or_none()
        )
        if document is None:
            raise ValueError("Document does not belong to selected knowledge context")

    def _chunk_scope_filter(
        self,
        scope: str,
        company_id: UUID | None,
        deal_id: UUID | None,
        include_global: bool,
    ):
        global_filter = KnowledgeChunk.scope == "global"
        if scope == "global":
            return global_filter
        if scope == "company":
            scoped_filter = and_(
                KnowledgeChunk.company_id == company_id,
                KnowledgeChunk.deal_id.is_(None),
            )
        else:
            scoped_filter = or_(
                KnowledgeChunk.deal_id == deal_id,
                and_(KnowledgeChunk.company_id == company_id, KnowledgeChunk.deal_id.is_(None)),
            )
        return or_(global_filter, scoped_filter) if include_global else scoped_filter

    def _split_text(self, text: str) -> list[str]:
        clean_text = re.sub(r"\s+", " ", text).strip()
        size = settings.rag_chunk_size
        overlap = settings.rag_chunk_overlap
        chunks: list[str] = []
        start = 0
        while start < len(clean_text):
            end = min(start + size, len(clean_text))
            chunk = clean_text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == len(clean_text):
                break
            start = max(0, end - overlap)
        return chunks

    def _split_source(
        self,
        text: str,
        page_texts: tuple[str, ...] | None,
    ) -> list[tuple[str, int | None]]:
        if page_texts is None:
            return [(chunk, None) for chunk in self._split_text(text)]
        chunks: list[tuple[str, int | None]] = []
        for page_number, page_text in enumerate(page_texts, start=1):
            chunks.extend((chunk, page_number) for chunk in self._split_text(page_text))
        return chunks

    def _merge_hybrid_results(
        self,
        query: str,
        query_embedding: list[float],
        vector_rows: list[tuple],
        lexical_rows: list[tuple],
        limit: int,
    ) -> list[RankedChunk]:
        candidates: dict[UUID, tuple[KnowledgeChunk, KnowledgeDocument, float]] = {}
        for chunk, document, distance in vector_rows:
            candidates[chunk.id] = (chunk, document, 1.0 - float(distance))
        for chunk, document, _rank in lexical_rows:
            if chunk.id not in candidates:
                candidates[chunk.id] = (
                    chunk,
                    document,
                    self._cosine_similarity(query_embedding, list(chunk.embedding_vector)),
                )

        lexical_ids = {chunk.id for chunk, _document, _rank in lexical_rows}
        ranked: list[RankedChunk] = []
        for chunk, document, semantic_score in candidates.values():
            lexical_score = self._lexical_similarity(query, chunk.text)
            score = 0.7 * max(0.0, semantic_score) + 0.3 * lexical_score
            method = "hybrid" if chunk.id in lexical_ids and semantic_score > 0 else (
                "lexical" if chunk.id in lexical_ids else "semantic"
            )
            ranked.append(
                RankedChunk(
                    chunk=chunk,
                    document=document,
                    score=score,
                    retrieval_method=method,
                )
            )
        return sorted(ranked, key=lambda item: item.score, reverse=True)[:limit]

    def _lexical_similarity(self, query: str, text: str) -> float:
        query_terms = set(re.findall(r"[\wа-яА-ЯёЁ]+", query.lower()))
        text_terms = set(re.findall(r"[\wа-яА-ЯёЁ]+", text.lower()))
        if not query_terms or not text_terms:
            return 0.0
        return len(query_terms & text_terms) / len(query_terms)

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        dot = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
        return dot / (left_norm * right_norm)

    def _embedding_identity_filter(self, dimensions: int):
        metadata = self.embedding_service.metadata(dimensions)
        return and_(
            KnowledgeChunk.embedding_provider == metadata["embedding_provider"],
            KnowledgeChunk.embedding_model == metadata["embedding_model"],
            KnowledgeChunk.embedding_version == metadata["embedding_version"],
            KnowledgeChunk.embedding_dimensions == dimensions,
        )
