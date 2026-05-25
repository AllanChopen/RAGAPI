import json

from fastapi import APIRouter, Depends, HTTPException, status
import httpx
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.settings import settings
from app.schemas.rag_schema import RAGAskRequest, RAGAskResponse
from app.services.hf_service import HFService
from app.services.rag_service import RAGService


router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/ask", response_model=RAGAskResponse, summary="Ask questions using retrieved repository context")
def ask_rag(payload: RAGAskRequest, db: Session = Depends(get_db)) -> RAGAskResponse:
    try:
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
