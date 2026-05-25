from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.controllers.chat_controller import router as chat_router
from app.controllers.git_controller import router as git_router
from app.controllers.hf_controller import router as hf_router
from app.controllers.health_controller import router as health_router
from app.controllers.item_controller import router as item_router
from app.controllers.rag_controller import router as rag_router
from app.controllers.trace_controller import router as trace_router
from app.controllers.vector_controller import router as vector_router
from app.core.database import Base, engine
from app.core.settings import settings
import app.models


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError as exc:
        logger.warning("Skipping database initialization during startup: %s", exc)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="FastAPI entrypoint with Swagger UI enabled for local testing.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        lifespan=lifespan,
    )

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(item_router, prefix=settings.api_prefix)
    app.include_router(hf_router, prefix=settings.api_prefix)
    app.include_router(git_router, prefix=settings.api_prefix)
    app.include_router(vector_router, prefix=settings.api_prefix)
    app.include_router(rag_router, prefix=settings.api_prefix)
    app.include_router(chat_router, prefix=settings.api_prefix)
    app.include_router(trace_router, prefix=settings.api_prefix)

    return app