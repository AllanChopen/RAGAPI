from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.repository_schema import (
    RepositoryBranchesRequest,
    RepositoryBranchesResponse,
    RepositoryCommitsRequest,
    RepositoryCommitsResponse,
    RepositoryCommitIngestRequest,
    RepositoryCommitIngestResponse,
    RepositoryIngestRequest,
    RepositoryIngestResponse,
)
from app.services.repository_service import RepositoryService


router = APIRouter(prefix="/repositories", tags=["Repositorios"])


@router.post(
    "/commits",
    response_model=RepositoryCommitsResponse,
    summary="Listar commits recientes de una rama",
    description="Consulta los commits recientes de la rama indicada o de la rama predeterminada.",
)
def list_repository_commits(payload: RepositoryCommitsRequest) -> RepositoryCommitsResponse:
    try:
        return RepositoryService.list_commits(payload.repository_url, payload.branch, payload.limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/commits/ingest",
    response_model=RepositoryCommitIngestResponse,
    summary="Indexar commits específicos",
    description="Indexa el contenido y los cambios de los commits indicados sin borrar las ramas u otros commits ya indexados.",
)
def ingest_repository_commits(
    payload: RepositoryCommitIngestRequest,
    db: Session = Depends(get_db),
) -> RepositoryCommitIngestResponse:
    try:
        return RepositoryService.ingest_commits(payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La base de datos no está disponible mientras se indexan los commits.",
        ) from exc


@router.post(
    "/branches",
    response_model=RepositoryBranchesResponse,
    summary="Listar ramas del repositorio",
    description="Obtiene las ramas remotas disponibles, el commit punta de cada una y la rama predeterminada del repositorio.",
    response_description="Repositorio, rama predeterminada y listado de ramas disponibles.",
)
def list_repository_branches(payload: RepositoryBranchesRequest) -> RepositoryBranchesResponse:
    try:
        return RepositoryService.list_branches(payload.repository_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/ingest",
    response_model=RepositoryIngestResponse,
    summary="Indexar ramas del repositorio",
    description="Clona el repositorio, procesa las ramas seleccionadas, genera fragmentos y embeddings, y almacena el contenido en el índice vectorial del proyecto.",
    response_description="Resumen de las ramas indexadas, archivos procesados y fragmentos creados.",
)
def ingest_repository(
    payload: RepositoryIngestRequest,
    db: Session = Depends(get_db),
) -> RepositoryIngestResponse:
    try:
        return RepositoryService.ingest(payload, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La base de datos no está disponible mientras se indexa el repositorio.",
        ) from exc
