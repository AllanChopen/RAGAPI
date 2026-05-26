from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.context_chunk import ContextChunk
from app.schemas.vector_schema import (
    VectorHealthResponse,
    VectorSearchRequest,
    VectorSearchResponse,
    VectorSearchResult,
    VectorUpsertRequest,
    VectorUpsertResponse,
)
from app.services.embedding_service import EmbeddingService


class VectorService:
    @staticmethod
    def ensure_vector_extension(db: Session) -> None:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    @staticmethod
    def health(db: Session) -> VectorHealthResponse:
        extension_exists = bool(
            db.execute(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")).scalar()
        )
        table_exists = bool(
            db.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'context_chunks')"
                )
            ).scalar()
        )

        return VectorHealthResponse(
            vector_extension_enabled=extension_exists,
            context_chunks_table_exists=table_exists,
            embedding_dimensions=settings.embedding_dimensions,
        )

    @staticmethod
    def upsert_test_chunk(db: Session, payload: VectorUpsertRequest) -> VectorUpsertResponse:
        if len(payload.embedding) != settings.embedding_dimensions:
            raise ValueError(
                f"Embedding dimension mismatch. Expected {settings.embedding_dimensions}, received {len(payload.embedding)}"
            )

        chunk = ContextChunk(
            source=payload.source,
            content=payload.content,
            metadata_json=payload.metadata_json,
            embedding=payload.embedding,
        )
        db.add(chunk)
        db.commit()
        db.refresh(chunk)

        return VectorUpsertResponse(
            id=chunk.id,
            source=chunk.source,
            embedding_dimensions=len(payload.embedding),
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

        # payload.source may be None, a single string, or a list of strings
        rows = []
        if payload.source:
            # normalize comma-separated into list
            sources_list = payload.source if isinstance(payload.source, list) else (
                [p.strip() for p in payload.source.split(",") if p.strip()] if isinstance(payload.source, str) and "," in payload.source else [payload.source]
            )

            # if uploaded sources present, perform a two-stage search to prioritize them
            uploaded_sources = [s for s in sources_list if isinstance(s, str) and s.startswith("uploaded:")]
            other_sources = [s for s in sources_list if s not in uploaded_sources]

            if uploaded_sources:
                stmt_uploaded = stmt.filter(ContextChunk.source.in_(uploaded_sources))
                rows_uploaded = stmt_uploaded.order_by("distance").limit(payload.top_k).all()
                rows.extend(rows_uploaded)

                if len(rows) < payload.top_k and other_sources:
                    stmt_other = stmt.filter(ContextChunk.source.in_(other_sources))
                    rows_other = stmt_other.order_by("distance").limit(payload.top_k).all()
                    # combine, avoiding duplicate ids
                    existing_ids = {r.id for r in rows}
                    for r in rows_other:
                        if r.id not in existing_ids:
                            rows.append(r)
                            existing_ids.add(r.id)
                            if len(rows) >= payload.top_k:
                                break
            else:
                stmt = stmt.filter(ContextChunk.source.in_(sources_list))
                rows = stmt.order_by("distance").limit(payload.top_k).all()
        else:
            rows = stmt.order_by("distance").limit(payload.top_k).all()

        matches: list[VectorSearchResult] = []
        for row in rows:
            similarity = max(0.0, 1.0 - float(row.distance))
            matches.append(
                VectorSearchResult(
                    id=row.id,
                    source=row.source,
                    content=row.content,
                    metadata_json=row.metadata_json or {},
                    similarity=similarity,
                )
            )

        return VectorSearchResponse(query=payload.query, top_k=payload.top_k, matches=matches)
