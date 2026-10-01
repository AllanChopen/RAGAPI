import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.settings import settings
from app.models.context_chunk import ContextChunk
from app.schemas.api_rag_schema import (
    RAGCompareRequest,
    RAGCompareResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGSource,
)
from app.schemas.rag_schema import RAGAskRequest, RAGAskResponse
from app.services.rag_service import RAGService
from app.services.repository_service import RepositoryService


router = APIRouter(tags=["RAG"])


@router.post(
    "/query",
    response_model=RAGQueryResponse,
    summary="Consultar el RAG sobre un proyecto",
    description="Recupera fragmentos relevantes del proyecto y genera una respuesta fundamentada. Puede restringirse a ramas Git, un documento o un commit indexado.",
    response_description="Respuesta generada por el RAG junto con sus fuentes estructuradas.",
)
def query_rag(
    payload: RAGQueryRequest,
    db: Session = Depends(get_db),
) -> RAGQueryResponse:
    try:
        _ensure_query_context(db, payload.project_id, payload.branches, payload.document)
        resolved_commit, resolved_repository = _resolve_commit_context(
            db, payload.project_id, payload.commit, payload.repository
        )
        response = RAGService.ask(
            db,
            RAGAskRequest(
                project_id=payload.project_id,
                query=payload.question,
                branches=payload.branches,
                document=payload.document,
                commit=resolved_commit,
                repository=resolved_repository,
                top_k=settings.rag_default_top_k,
                max_new_tokens=settings.llm_max_output_tokens,
                conversation_history=payload.conversation_history,
                debug=payload.debug,
            ),
        )
        return _query_response(payload, response)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"El proveedor de IA respondió con un error: {exc.response.text}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No fue posible conectar con el proveedor de IA: {exc}",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La base de datos no está disponible mientras se ejecuta la recuperación RAG.",
        ) from exc


@router.post(
    "/compare",
    response_model=RAGCompareResponse,
    summary="Comparar dos ramas Git indexadas",
    description="Obtiene un Git diff real entre dos ramas y utiliza el RAG para explicar los cambios con evidencia de los archivos modificados.",
    response_description="Comparación de ramas, cambios detectados y fuentes utilizadas por el RAG.",
)
def compare_branches(
    payload: RAGCompareRequest,
    db: Session = Depends(get_db),
) -> RAGCompareResponse:
    try:
        repository, changes = RepositoryService.diff_branches(
            payload.repository_url,
            payload.branch_a,
            payload.branch_b,
        )
        _ensure_indexed_branches(
            db=db,
            project_id=payload.project_id,
            repository=repository,
            branches=[payload.branch_a, payload.branch_b],
        )

        diff_context = _format_diff(payload.branch_a, payload.branch_b, changes)
        changed_paths = list(
            dict.fromkeys(
                path
                for change in changes
                for path in [change.previous_path, change.path]
                if path
            )
        )
        response = RAGService.ask(
            db,
            RAGAskRequest(
                project_id=payload.project_id,
                query=payload.question,
                branches=[payload.branch_a, payload.branch_b],
                source=RepositoryService._source_name(payload.project_id, repository),
                file_paths=changed_paths or None,
                top_k=settings.rag_default_top_k,
                max_new_tokens=settings.llm_max_output_tokens,
                additional_context=diff_context,
                debug=payload.debug,
            ),
        )

        return RAGCompareResponse(
            project_id=payload.project_id,
            repository=repository,
            branch_a=payload.branch_a,
            branch_b=payload.branch_b,
            question=payload.question,
            answer=response.answer,
            changes=changes,
            sources=_sources(response),
            context_chunks_used=response.context_chunks_used,
            provider=response.provider,
            model=response.model,
            response_time_ms=response.response_time_ms,
            debug_matches=response.debug_matches,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"El proveedor de IA respondió con un error: {exc.response.text}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No fue posible conectar con el proveedor de IA: {exc}",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La base de datos no está disponible mientras se comparan las ramas.",
        ) from exc


def _query_response(payload: RAGQueryRequest, response: RAGAskResponse) -> RAGQueryResponse:
    return RAGQueryResponse(
        project_id=payload.project_id,
        question=payload.question,
        answer=response.answer,
        sources=_sources(response),
        context_chunks_used=response.context_chunks_used,
        provider=response.provider,
        model=response.model,
        response_time_ms=response.response_time_ms,
        debug_matches=response.debug_matches,
    )


def _sources(response: RAGAskResponse) -> list[RAGSource]:
    return [
        RAGSource(
            chunk_id=citation.chunk_id,
            source_type=citation.source_type,
            source=citation.source,
            repository=citation.repository,
            document=citation.document,
            branch=citation.branch,
            commit=citation.commit,
            file_path=citation.file_path,
            line_start=citation.line_start,
            line_end=citation.line_end,
            page=citation.page,
            tab=citation.tab,
            artifact_type=citation.artifact_type,
            score=citation.similarity,
        )
        for citation in response.citations
    ]


def _ensure_query_context(
    db: Session,
    project_id: str,
    branches: list[str] | None,
    document: str | None = None,
) -> None:
    project_filter = ContextChunk.metadata_json["project_id"].astext == project_id
    if db.query(ContextChunk.id).filter(project_filter).first() is None:
        raise LookupError(
            f"El proyecto '{project_id}' no tiene contexto RAG indexado. Primero indexe un repositorio o documentos."
        )

    if document:
        indexed_document = (
            db.query(ContextChunk.id)
            .filter(
                project_filter,
                ContextChunk.metadata_json["source_type"].astext == "document",
                ContextChunk.metadata_json["document"].astext == document,
            )
            .first()
        )
        if indexed_document is None:
            raise LookupError(
                f"El documento '{document}' no está indexado para el proyecto '{project_id}'."
            )

    if branches:
        rows = (
            db.query(ContextChunk.metadata_json["branch"].astext)
            .filter(
                project_filter,
                ContextChunk.metadata_json["source_type"].astext == "repository",
            )
            .distinct()
            .all()
        )
        indexed_branches = {row[0] for row in rows if row[0]}
        missing = [branch for branch in branches if branch not in indexed_branches]
        if missing:
            raise LookupError(
                "Las siguientes ramas no están indexadas para este proyecto: "
                + ", ".join(missing)
            )


def _resolve_commit_context(
    db: Session,
    project_id: str,
    commit_prefix: str | None,
    repository: str | None,
) -> tuple[str | None, str | None]:
    if not commit_prefix:
        return None, None

    metadata = ContextChunk.metadata_json
    query = db.query(metadata["repository"].astext, metadata["commit"].astext).filter(
        metadata["project_id"].astext == project_id,
        metadata["source_type"].astext.in_(
            ["repository", "repository_commit", "commit_metadata"]
        ),
        metadata["commit"].astext.like(f"{commit_prefix}%"),
    )
    if repository:
        query = query.filter(metadata["repository"].astext == repository)
    matches = {(name, sha) for name, sha in query.distinct().all() if name and sha}
    if not matches:
        raise LookupError(
            f"El commit '{commit_prefix}' no está indexado para el proyecto '{project_id}'."
        )
    if len(matches) > 1:
        raise LookupError(
            "El SHA indicado coincide con varios commits o repositorios indexados; "
            "envíe el SHA completo y, si aplica, repository."
        )
    name, sha = matches.pop()
    return sha, name


def _ensure_indexed_branches(
    db: Session,
    project_id: str,
    repository: str,
    branches: list[str],
) -> None:
    rows = (
        db.query(ContextChunk.metadata_json["branch"].astext)
        .filter(
            ContextChunk.metadata_json["project_id"].astext == project_id,
            ContextChunk.metadata_json["source_type"].astext == "repository",
            ContextChunk.metadata_json["repository"].astext == repository,
            ContextChunk.metadata_json["branch"].astext.in_(branches),
        )
        .distinct()
        .all()
    )
    indexed = {row[0] for row in rows if row[0]}
    missing = [branch for branch in branches if branch not in indexed]
    if missing:
        raise LookupError(
            "Las siguientes ramas deben indexarse antes de realizar la comparación: "
            + ", ".join(missing)
        )


def _format_diff(branch_a: str, branch_b: str, changes) -> str:
    if not changes:
        return f"Git diff verificado entre {branch_a} y {branch_b}: no hay archivos diferentes."

    lines = [f"Git diff verificado entre {branch_a} y {branch_b}:"]
    for change in changes:
        if change.previous_path:
            lines.append(f"- {change.status}: {change.previous_path} -> {change.path}")
        else:
            lines.append(f"- {change.status}: {change.path}")
    return "\n".join(lines)
