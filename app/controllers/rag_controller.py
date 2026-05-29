import json

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
import httpx
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import uuid
from typing import List, Optional

from io import BytesIO
from openpyxl import load_workbook
from bs4 import BeautifulSoup

from app.core.database import get_db
from app.core.settings import settings
from app.schemas.rag_schema import RAGAskRequest, RAGAskResponse
from app.services.hf_service import HFService
from app.services.rag_service import RAGService
from app.models.context_chunk import ContextChunk
from app.services.embedding_service import EmbeddingService


router = APIRouter(prefix="/rag", tags=["rag"])


def _ingest_files_and_repo(db: Session, files, repo_url: Optional[str], keep_uploaded: bool = True):
    import tempfile
    from pathlib import Path
    from app.services.git_service import GitService

    session_id = str(uuid.uuid4())
    tmp_source = f"uploaded:{session_id}"
    uploaded_chunks = 0
    repo_name = None
    repo_chunks = 0

    if files:
        for upload in files:
            filename = upload.filename or "uploaded"
            content_bytes = upload.file.read()
            text = ""
            extracted_chunks = None
            if filename.lower().endswith(".xlsx"):
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
                try:
                    tmp.write(content_bytes)
                    tmp.flush()
                    tmp_path = Path(tmp.name)
                    file_chunks = GitService._extract_xlsx_chunks(tmp_path, max_chunks=10000)
                    extracted_chunks = file_chunks
                finally:
                    try:
                        tmp.close()
                    except Exception:
                        pass
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
            elif filename.lower().endswith('.drawio') or filename.lower().endswith('.xml'):
                try:
                    soup = BeautifulSoup(content_bytes, "xml")
                    parts: list[str] = []
                    for tag in soup.find_all():
                        if tag.has_attr('value'):
                            parts.append(tag.get('value'))
                    parts.extend([t.strip() for t in soup.stripped_strings])
                    seen = set(); dedup = []
                    for p in parts:
                        if not p: continue
                        if p in seen: continue
                        seen.add(p); dedup.append(p)
                    text = "\n".join(dedup)
                except Exception:
                    text = content_bytes.decode("utf-8", errors="ignore")
            else:
                try:
                    text = content_bytes.decode("utf-8")
                except Exception:
                    text = str(content_bytes)

            if extracted_chunks:
                for chunk_info in extracted_chunks:
                    chunk = chunk_info.get("content")
                    metadata = {
                        "file_name": filename,
                        "file_path": filename,
                        "tab": chunk_info.get("tab"),
                        "line_start": chunk_info.get("line_start"),
                        "line_end": chunk_info.get("line_end"),
                    }
                    embedding = EmbeddingService.embed_text(chunk)
                    db_chunk = ContextChunk(
                        source=tmp_source,
                        content=chunk,
                        metadata_json=metadata,
                        embedding=embedding,
                    )
                    db.add(db_chunk)
                    uploaded_chunks += 1
            else:
                # fallback chunking
                def chunk_text(text: str, max_chunk_chars: int = 1000, overlap: int = 200) -> list[str]:
                    if not text:
                        return []
                    chunks: list[str] = []
                    start = 0
                    length = len(text)
                    while start < length:
                        end = min(start + max_chunk_chars, length)
                        chunks.append(text[start:end])
                        if end == length:
                            break
                        start = max(0, end - overlap)
                    return chunks

                chunks = chunk_text(text, max_chunk_chars=1000, overlap=200)
                for chunk in chunks:
                    embedding = EmbeddingService.embed_text(chunk)
                    db_chunk = ContextChunk(
                        source=tmp_source,
                        content=chunk,
                        metadata_json={"file_name": filename},
                        embedding=embedding,
                    )
                    db.add(db_chunk)
                    uploaded_chunks += 1

        db.commit()

    # ingest repo if provided
    if repo_url:
        try:
            from app.schemas.git_schema import GitIngestRequest
            from app.services.git_service import GitService

            ingest_payload = GitIngestRequest(repo_url=repo_url)
            ingest_resp = GitService.ingest_repository(ingest_payload, db)
            repo_name = ingest_resp.repo_name
            repo_chunks = ingest_resp.chunks_inserted
        except Exception:
            repo_name = None

    return {"uploaded_source": tmp_source if uploaded_chunks>0 else None, "uploaded_chunks": uploaded_chunks, "repo_name": repo_name, "repo_chunks": repo_chunks}



@router.post("/ask", response_model=RAGAskResponse, summary="Ask questions using retrieved repository context")
def ask_rag(payload: RAGAskRequest, db: Session = Depends(get_db)) -> RAGAskResponse:
    try:
        # enforce defaults so end users cannot override system assumptions
        try:
            payload.top_k = 10
            payload.temperature = 0.2
        except Exception:
            pass
        return RAGService.ask(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Hugging Face API error: {exc.response.text}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to connect to Hugging Face API: {str(exc)}",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while running retrieval",
        ) from exc


@router.post("/ask/stream", summary="Ask questions with streaming RAG response (SSE)")
def ask_rag_stream(payload: RAGAskRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    try:
        prompt, citations = RAGService.prepare_generation(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while running retrieval",
        ) from exc

    def event_stream():
        meta_event = {
            "type": "meta",
            "retrieval_query": payload.query,
            "model": settings.hf_model_name,
            "context_chunks_used": len(citations),
            "citations": [citation.model_dump() for citation in citations],
        }
        yield f"data: {json.dumps(meta_event, ensure_ascii=False)}\n\n"

        try:
            for token in HFService.infer_stream(
                prompt=prompt,
                max_new_tokens=payload.max_new_tokens,
                temperature=payload.temperature,
            ):
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except httpx.HTTPStatusError as exc:
            error_event = {"type": "error", "detail": f"Hugging Face API error: {exc.response.text}"}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        except httpx.HTTPError as exc:
            error_event = {"type": "error", "detail": f"Unable to connect to Hugging Face API: {str(exc)}"}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/ask/upload", response_model=RAGAskResponse, summary="Ask with uploaded files as context (temporary)")
def ask_with_uploads(
    query: str = Form(...),
    repo_url: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    top_k: int = Form(10),
    max_new_tokens: int = Form(200),
    temperature: float = Form(0.2),
    source: Optional[str] = Form(None),
    combine_sources: bool = Form(False),
    sources: Optional[str] = Form(None),
    keep_uploaded: bool = Form(False),
    conversation_history: Optional[str] = Form(None),
    debug: bool = Form(False),
    db: Session = Depends(get_db),
) -> RAGAskResponse:
    """Accept uploaded files, index them temporarily and run RAG against them.

    The uploaded chunks are removed after the request completes.
    conversation_history may be a JSON string representing the list of turns.
    """
    import json as _json

    session_id = str(uuid.uuid4())
    tmp_source = f"uploaded:{session_id}"

    try:
        # Importante:
        # El frontend puede guardar campos extra como citations para mostrarlos en pantalla,
        # pero el prompt solo necesita user y assistant.
        history = []
        if conversation_history:
            try:
                raw_history = _json.loads(conversation_history)

                if isinstance(raw_history, list):
                    for turn in raw_history[-6:]:
                        if not isinstance(turn, dict):
                            continue

                        history.append(
                            {
                                "user": str(turn.get("user", "")),
                                "assistant": str(turn.get("assistant", "")),
                            }
                        )
            except Exception:
                history = []

        def chunk_text(text: str, max_chunk_chars: int = 1000, overlap: int = 200) -> list[str]:
            if not text:
                return []
            chunks: list[str] = []
            start = 0
            length = len(text)
            while start < length:
                end = min(start + max_chunk_chars, length)
                chunks.append(text[start:end])
                if end == length:
                    break
                start = max(0, end - overlap)
            return chunks

        # process uploaded files
        if files:
            for upload in files:
                filename = upload.filename or "uploaded"
                content_bytes = upload.file.read()
                text = ""
                if filename.lower().endswith(".xlsx"):
                    # write bytes to a temporary file and reuse GitService's xlsx extractor
                    import tempfile
                    from pathlib import Path
                    from app.services.git_service import GitService

                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
                    try:
                        tmp.write(content_bytes)
                        tmp.flush()
                        tmp_path = Path(tmp.name)
                        # extract row-wise chunks (each row becomes a chunk)
                        file_chunks = GitService._extract_xlsx_chunks(tmp_path, max_chunks=10000)
                        parts: list[str] = []
                        # we'll transform file_chunks into a single text for fallback, but keep chunks
                        extracted_chunks = file_chunks
                        text = "\n".join([c["content"] for c in extracted_chunks])
                    finally:
                        try:
                            tmp.close()
                        except Exception:
                            pass
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass
                elif filename.lower().endswith(".drawio") or filename.lower().endswith(".xml"):
                    try:
                        # Parse Draw.io/XML as XML for reliable extraction (avoid HTML parser warnings)
                        soup = BeautifulSoup(content_bytes, "xml")
                        parts: list[str] = []
                        # extract node values and visible strings
                        for tag in soup.find_all():
                            if tag.has_attr("value"):
                                parts.append(tag.get("value"))
                        parts.extend([t.strip() for t in soup.stripped_strings])
                        # deduplicate while preserving order
                        seen = set()
                        dedup: list[str] = []
                        for p in parts:
                            if not p:
                                continue
                            if p in seen:
                                continue
                            seen.add(p)
                            dedup.append(p)
                        text = "\n".join(dedup)
                    except Exception:
                        text = content_bytes.decode("utf-8", errors="ignore")
                else:
                    try:
                        text = content_bytes.decode("utf-8")
                    except Exception:
                        text = str(content_bytes)

                # for xlsx we already built row-wise chunks; otherwise chunk the plain text
                if filename.lower().endswith(".xlsx") and extracted_chunks:
                    for chunk_info in extracted_chunks:
                        chunk = chunk_info.get("content")
                        metadata = {
                            "file_name": filename,
                            "file_path": filename,
                            "tab": chunk_info.get("tab"),
                            "line_start": chunk_info.get("line_start"),
                            "line_end": chunk_info.get("line_end"),
                        }
                        embedding = EmbeddingService.embed_text(chunk)
                        db_chunk = ContextChunk(
                            source=tmp_source,
                            content=chunk,
                            metadata_json=metadata,
                            embedding=embedding,
                        )
                        db.add(db_chunk)
                else:
                    # split into chunks with overlap
                    chunks = chunk_text(text, max_chunk_chars=1000, overlap=200)

                    for chunk in chunks:
                        embedding = EmbeddingService.embed_text(chunk)
                        db_chunk = ContextChunk(
                            source=tmp_source,
                            content=chunk,
                            metadata_json={"file_name": filename, "file_path": filename},
                            embedding=embedding,
                        )
                        db.add(db_chunk)
            db.commit()

        # decide which sources to search
                # decide which sources to search
        # Regla:
        # - Si hay solo repo, consulta solo ese repo.
        # - Si hay solo archivos, consulta solo esos archivos.
        # - Si hay repo + archivos, consulta ambos.
        # - Si el frontend manda sources, se respetan esas fuentes.
        selected_sources: list[str] = []
        repo_name_from_request: Optional[str] = None

        def add_selected(value: Optional[str]) -> None:
            if not value:
                return
            if value not in selected_sources:
                selected_sources.append(value)

        def ensure_repo_ingested() -> Optional[str]:
            nonlocal repo_name_from_request

            if repo_name_from_request:
                return repo_name_from_request

            if not repo_url:
                return None

            try:
                from app.schemas.git_schema import GitIngestRequest
                from app.services.git_service import GitService

                ingest_payload = GitIngestRequest(repo_url=repo_url)
                ingest_resp = GitService.ingest_repository(ingest_payload, db)
                repo_name_from_request = ingest_resp.repo_name
                return repo_name_from_request
            except Exception:
                return None

        if sources:
            parts = [p.strip() for p in sources.split(",") if p.strip()]

            for part in parts:
                if part == "uploaded":
                    # uploaded significa los archivos enviados en esta misma petición
                    if files:
                        add_selected(tmp_source)
                elif part == "repo":
                    add_selected(ensure_repo_ingested())
                elif part == "api":
                    # No existe una fuente real llamada api en la tabla de chunks.
                    # Se ignora para evitar búsquedas vacías.
                    continue
                else:
                    # Fuente exacta persistida, por ejemplo:
                    # uploaded:uuid o blackjack-javascript-main
                    add_selected(part)

        if not selected_sources:
            if files:
                add_selected(tmp_source)

            if repo_url:
                add_selected(ensure_repo_ingested())

            if source:
                add_selected(source)

        selected_source = None
        if len(selected_sources) == 1:
            selected_source = selected_sources[0]
        elif len(selected_sources) > 1:
            selected_source = selected_sources

        # Enforce hardcoded defaults: final users shouldn't change these params
        forced_top_k = 10
        forced_temperature = 0.2

        payload = RAGAskRequest(
            query=query,
            top_k=forced_top_k,
            max_new_tokens=max_new_tokens,
            temperature=forced_temperature,
            source=selected_source,
            debug=debug,
            conversation_history=history,
        )

        response = RAGService.ask(db, payload)

        return response
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Hugging Face API error: {exc.response.text}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to connect to Hugging Face API: {str(exc)}",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable while running retrieval",
        ) from exc
    finally:
        # cleanup temporary uploaded chunks unless caller requested to keep them
        if not keep_uploaded:
            try:
                db.query(ContextChunk).filter(ContextChunk.source == tmp_source).delete(synchronize_session=False)
                db.commit()
            except Exception:
                db.rollback()


@router.post('/ingest', summary='Ingest uploaded files and/or repo and return readiness')
def ingest_files(
    repo_url: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    keep_uploaded: bool = Form(True),
    db: Session = Depends(get_db),
):
    """Ingest files and/or repo and return a simple readiness summary.

    The uploaded chunks will be kept if `keep_uploaded` is true. Returns the
    `uploaded_source` name which can be passed as a `sources` value when asking.
    """
    try:
        summary = _ingest_files_and_repo(db=db, files=files, repo_url=repo_url, keep_uploaded=keep_uploaded)
        return {"ok": True, **summary}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post('/reset_session', summary='Reset uploaded session context (delete uploaded chunks)')
def reset_session(db: Session = Depends(get_db)):
    """Delete all uploaded temporary chunks (source like 'uploaded:%'). Returns count deleted."""
    try:
        q = db.query(ContextChunk).filter(ContextChunk.source.like('uploaded:%'))
        count = q.count()
        q.delete(synchronize_session=False)
        db.commit()
        return {"ok": True, "deleted_uploaded_chunks": count}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
