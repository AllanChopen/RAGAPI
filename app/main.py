import logging
import os
import sys
from contextlib import asynccontextmanager

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import app.models
from app.controllers.document_controller import router as document_router
from app.controllers.frontend_controller import router as frontend_router
from app.controllers.health_v1_controller import router as health_v1_router
from app.controllers.query_controller import router as query_router
from app.controllers.project_index_controller import router as project_index_router
from app.controllers.repository_controller import router as repository_router
from app.core.database import Base, engine
from app.core.settings import settings


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except SQLAlchemyError as exc:
        logger.warning("No fue posible verificar o crear la extensión pgvector al iniciar: %s", exc)

    try:
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError as exc:
        logger.warning("No fue posible verificar o crear las tablas del RAG al iniciar: %s", exc)

    yield


def create_app() -> FastAPI:
    tags_metadata = [
        {
            "name": "Repositorios",
            "description": "Consulta de ramas e indexación de repositorios Git por proyecto.",
        },
        {
            "name": "Documentos",
            "description": "Carga e indexación de documentación, scripts SQL y archivos soportados por el RAG.",
        },
        {
            "name": "RAG",
            "description": "Consultas fundamentadas y comparación de ramas usando recuperación aumentada por generación.",
        },
        {
            "name": "Índice de proyectos",
            "description": "Administración del contexto vectorial almacenado para cada project_id.",
        },
        {
            "name": "Estado y métricas",
            "description": "Verificación del estado del RAG y métricas básicas de consultas.",
        },
    ]

    app = FastAPI(
        title=settings.app_name,
        description=(
            "API RAG para proyectos de software. Permite indexar repositorios Git y documentos, "
            "realizar recuperación semántica, generar respuestas respaldadas por fuentes y comparar ramas."
        ),
        version="2.0.1",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        openapi_tags=tags_metadata,
        lifespan=lifespan,
    )

    app.include_router(repository_router, prefix=settings.api_v1_prefix)
    app.include_router(document_router, prefix=settings.api_v1_prefix)
    app.include_router(query_router, prefix=settings.api_v1_prefix)
    app.include_router(project_index_router, prefix=settings.api_v1_prefix)
    app.include_router(health_v1_router, prefix=settings.api_v1_prefix)

    app.include_router(frontend_router, prefix="")

    return app


if __name__ == "__main__":
    try:
        import uvicorn

        uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=8000)
    except Exception:
        print(
            "Ejecute el servidor con: python -m uvicorn app.main:create_app "
            "--factory --host 127.0.0.1 --port 8000"
        )
