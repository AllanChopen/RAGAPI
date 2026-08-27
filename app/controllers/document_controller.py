from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import WithJsonSchema
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.document_schema import DocumentIngestResponse
from app.services.document_service import DocumentService


router = APIRouter(prefix="/documents", tags=["Documentos"])

BinaryUploadFile = Annotated[
    UploadFile,
    WithJsonSchema({"type": "string", "format": "binary"}),
]

@router.post(
    "/ingest",
    response_model=DocumentIngestResponse,
    summary="Indexar documentos del proyecto",
    description=(
        "Carga uno o varios archivos asociados a un proyecto, extrae su contenido, "
        "lo divide en fragmentos, genera embeddings y almacena el resultado en el índice vectorial. "
        "Admite documentación, scripts SQL, hojas de cálculo y otros formatos soportados por el RAG."
    ),
    response_description="Resumen de los documentos indexados y cantidad de fragmentos creados.",
)
def ingest_documents(
    project_id: Annotated[
        str,
        Form(description="Identificador del proyecto al que pertenecen los documentos."),
    ],
    files: Annotated[
        list[BinaryUploadFile],
        File(description="Seleccione uno o varios archivos para indexar."),
    ],
    db: Session = Depends(get_db),
) -> DocumentIngestResponse:
    try:
        return DocumentService.ingest_files(project_id=project_id, files=files, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La base de datos no está disponible mientras se indexan los documentos.",
        ) from exc
