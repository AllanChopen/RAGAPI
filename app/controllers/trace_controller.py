from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.trace_schema import (
    DataDictionaryIngestRequest,
    DataDictionaryIngestResponse,
    FieldUsageTraceRequest,
    FieldUsageTraceResponse,
)
from app.services.trace_service import TraceService


router = APIRouter(prefix="/trace", tags=["traceability"])


@router.post("/dictionary/ingest", response_model=DataDictionaryIngestResponse)
def ingest_dictionary(payload: DataDictionaryIngestRequest, db: Session = Depends(get_db)) -> DataDictionaryIngestResponse:
    try:
        return TraceService.ingest_data_dictionary(db, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while ingesting data dictionary",
        ) from exc


@router.post("/field-usage", response_model=FieldUsageTraceResponse)
def trace_field_usage(payload: FieldUsageTraceRequest, db: Session = Depends(get_db)) -> FieldUsageTraceResponse:
    try:
        return TraceService.trace_field_usage(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while tracing field usage",
        ) from exc
