from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.git_schema import GitIngestRequest, GitIngestResponse, GitScanResponse, GitSourceRequest
from app.services.git_service import GitService


router = APIRouter(prefix="/git", tags=["git"])


@router.post("/scan", response_model=GitScanResponse, summary="Scan Git repository source code")
def scan_git_repository(payload: GitSourceRequest) -> GitScanResponse:
    try:
        return GitService.scan_repository(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/ingest", response_model=GitIngestResponse, summary="Ingest Git source into vector context store")
def ingest_git_repository(payload: GitIngestRequest, db: Session = Depends(get_db)) -> GitIngestResponse:
    try:
        return GitService.ingest_repository(payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
