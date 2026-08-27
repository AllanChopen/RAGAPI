from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.context_chunk import ContextChunk
from app.schemas.vector_schema import (
    VectorHealthResponse,
    VectorSearchRequest,
    VectorSearchResponse,
    VectorSearchResult,
)
from app.services.embedding_service import EmbeddingService


class VectorService:
    @staticmethod
    def health(db: Session) -> VectorHealthResponse:
        vector_extension_enabled = bool(
            db.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                    ")"
                )
            ).scalar()
        )
        context_chunks_table_exists = bool(
            db.execute(
                text("SELECT to_regclass('public.context_chunks') IS NOT NULL")
            ).scalar()
        )

        return VectorHealthResponse(
            vector_extension_enabled=vector_extension_enabled,
            context_chunks_table_exists=context_chunks_table_exists,
            embedding_dimensions=settings.embedding_dimensions,
        )

    @staticmethod
    def semantic_search(db: Session, payload: VectorSearchRequest) -> VectorSearchResponse:
        query_embedding = EmbeddingService.embed_text(payload.query)

        stmt = db.query(
            ContextChunk.id,
            ContextChunk.source,
            ContextChunk.content,
            ContextChunk.metadata_json,
            ContextChunk.embedding.cosine_distance(query_embedding).label("distance"),
        )

        stmt = stmt.filter(
            ContextChunk.metadata_json["project_id"].astext == payload.project_id
        )

        if payload.branches:
            stmt = stmt.filter(
                or_(
                    ContextChunk.metadata_json["source_type"].astext != "repository",
                    ContextChunk.metadata_json["branch"].astext.in_(payload.branches),
                )
            )

        if payload.source_types:
            stmt = stmt.filter(
                ContextChunk.metadata_json["source_type"].astext.in_(payload.source_types)
            )

        if payload.file_paths:
            stmt = stmt.filter(
                ContextChunk.metadata_json["file_path"].astext.in_(payload.file_paths)
            )

        sources = VectorService._normalize_sources(payload.source)
        if sources:
            stmt = stmt.filter(ContextChunk.source.in_(sources))

        rows = stmt.order_by("distance").limit(payload.top_k).all()
        matches = [
            VectorSearchResult(
                id=row.id,
                source=row.source,
                content=row.content,
                metadata_json=row.metadata_json or {},
                similarity=max(-1.0, min(1.0, 1.0 - float(row.distance))),
            )
            for row in rows
        ]

        return VectorSearchResponse(
            query=payload.query,
            top_k=payload.top_k,
            matches=matches,
        )

    @staticmethod
    def _normalize_sources(source: str | list[str] | None) -> list[str]:
        if not source:
            return []
        if isinstance(source, list):
            return [item for item in source if item]
        return [item.strip() for item in source.split(",") if item.strip()]
