from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.vector_schema import (
    VectorHealthResponse,
    VectorSearchRequest,
    VectorSearchResponse,
    VectorUpsertRequest,
    VectorUpsertResponse,
)
from app.services.vector_service import VectorService


router = APIRouter(prefix="/vector", tags=["vector"])


@router.get("/health", response_model=VectorHealthResponse, summary="Check pgvector status")
def vector_health(db: Session = Depends(get_db)) -> VectorHealthResponse:
    try:
        return VectorService.health(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while checking vector extension",
        ) from exc


@router.post("/test-upsert", response_model=VectorUpsertResponse, summary="Insert a test embedding chunk")
def test_upsert_vector(payload: VectorUpsertRequest, db: Session = Depends(get_db)) -> VectorUpsertResponse:
    try:
        return VectorService.upsert_test_chunk(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while writing vector data",
        ) from exc


@router.post("/search", response_model=VectorSearchResponse, summary="Semantic search over context chunks")
def search_vector_context(payload: VectorSearchRequest, db: Session = Depends(get_db)) -> VectorSearchResponse:
    try:
        return VectorService.semantic_search(db, payload)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while searching vector context",
        ) from exc
