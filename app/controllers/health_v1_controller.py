from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.settings import settings
from app.schemas.api_rag_schema import RAGHealthResponse, RAGMetricsResponse
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.metrics_service import MetricsService
from app.services.vector_service import VectorService


router = APIRouter(tags=["Estado y métricas"])


@router.get(
    "/health",
    response_model=RAGHealthResponse,
    summary="Consultar el estado del servicio RAG",
    description=(
        "Verifica la conexión con PostgreSQL, la disponibilidad de pgvector y la configuración "
        "de los servicios de embeddings y del modelo de lenguaje."
    ),
    response_description="Estado general del RAG y de sus dependencias principales.",
)
def health(db: Session = Depends(get_db)) -> RAGHealthResponse:
    try:
        db.execute(text("SELECT 1"))
        vector = VectorService.health(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La base de datos no está disponible.",
        ) from exc

    database_status = "ok"
    vector_status = (
        "ok"
        if vector.vector_extension_enabled and vector.context_chunks_table_exists
        else "unavailable"
    )
    embedding_status = "configured" if EmbeddingService.is_configured() else "not_configured"
    llm_status = "configured" if LLMService.is_configured() else "not_configured"
    overall = (
        "healthy"
        if vector_status == "ok"
        and embedding_status == "configured"
        and llm_status == "configured"
        else "degraded"
    )

    return RAGHealthResponse(
        status=overall,
        database=database_status,
        vector_store=vector_status,
        embedding_service=embedding_status,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model_name,
        llm_service=llm_status,
        llm_provider=settings.llm_provider,
        llm_model=settings.active_llm_model,
    )


@router.get(
    "/metrics",
    response_model=RAGMetricsResponse,
    summary="Consultar métricas de uso del RAG",
    description=(
        "Devuelve la cantidad total de consultas, consultas exitosas, consultas fallidas "
        "y el tiempo promedio de respuesta registrado por el servicio RAG."
    ),
    response_description="Métricas acumuladas de consultas realizadas al RAG.",
)
def metrics(db: Session = Depends(get_db)) -> RAGMetricsResponse:
    try:
        return MetricsService.get_metrics(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La base de datos no está disponible mientras se consultan las métricas del RAG.",
        ) from exc
