from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.context_chunk import ContextChunk
from app.schemas.api_rag_schema import RAGIndexDeleteResponse


router = APIRouter(prefix="/projects", tags=["Índice de proyectos"])


@router.delete(
    "/{project_id}/index",
    response_model=RAGIndexDeleteResponse,
    summary="Eliminar el índice RAG de un proyecto",
    description="Elimina todos los fragmentos y embeddings asociados al project_id indicado. No elimina el proyecto del backend general.",
    response_description="Cantidad de fragmentos eliminados del índice RAG.",
)
def delete_project_index(
    project_id: str,
    db: Session = Depends(get_db),
) -> RAGIndexDeleteResponse:
    try:
        query = db.query(ContextChunk).filter(
            ContextChunk.metadata_json["project_id"].astext == project_id
        )
        count = query.count()
        query.delete(synchronize_session=False)
        db.commit()
        return RAGIndexDeleteResponse(project_id=project_id, deleted_chunks=count)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La base de datos no está disponible mientras se elimina el índice del proyecto.",
        ) from exc
