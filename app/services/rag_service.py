from sqlalchemy.orm import Session

from app.core.settings import settings
from app.schemas.rag_schema import RAGAskRequest, RAGAskResponse, RAGCitation
from app.schemas.vector_schema import VectorSearchRequest
from app.services.hf_service import HFService
from app.services.vector_service import VectorService


class RAGService:
    @staticmethod
    def _build_prompt_and_citations(db: Session, payload: RAGAskRequest) -> tuple[str, list[RAGCitation]]:
        retrieval = VectorService.semantic_search(
            db,
            VectorSearchRequest(query=payload.query, top_k=payload.top_k, source=payload.source),
        )

        context_blocks: list[str] = []
        citations: list[RAGCitation] = []

        for idx, match in enumerate(retrieval.matches, start=1):
            if match.similarity < settings.rag_min_similarity:
                continue

            metadata = match.metadata_json or {}
            file_path = metadata.get("file_path")
            line_start = metadata.get("line_start")
            line_end = metadata.get("line_end")
            tab = metadata.get("tab")
            location = file_path or "unknown"
            if line_start and line_end:
                location = f"{location}:{line_start}-{line_end}"
            if tab:
                location = f"{location} [tab: {tab}]"

            context_blocks.append(
                "\n".join(
                    [
                        f"[Chunk {idx}]",
                        f"source: {match.source}",
                        f"location: {location}",
                        f"similarity: {match.similarity:.4f}",
                        f"content:\n{match.content}",
                    ]
                )
            )
            citations.append(
                RAGCitation(
                    chunk_id=match.id,
                    source=match.source,
                    similarity=match.similarity,
                    file_path=file_path,
                    line_start=int(line_start) if line_start is not None else None,
                    line_end=int(line_end) if line_end is not None else None,
                    tab=str(tab) if tab is not None else None,
                )
            )

        history_text = RAGService._format_history(payload.conversation_history)
        context_text = "\n\n".join(context_blocks) if context_blocks else "No relevant context found."

        prompt = (
            "You are a strict technical assistant for repository traceability. "
            "You MUST use only the provided retrieved context and citations. "
            "Do not use external or prior model knowledge. "
            "If evidence is insufficient, answer exactly: 'No hay evidencia suficiente en los documentos cargados.'\n\n"
            f"Conversation memory:\n{history_text}\n\n"
            f"User question:\n{payload.query}\n\n"
            f"Retrieved context:\n{context_text}\n\n"
            "Return a concise answer in Spanish and include a short 'Fuentes' section with file and line/tab references."
        )

        return prompt, citations

    @staticmethod
    def ask(db: Session, payload: RAGAskRequest) -> RAGAskResponse:
        prompt, citations = RAGService._build_prompt_and_citations(db, payload)

        if not citations:
            answer = "No hay evidencia suficiente en los documentos cargados."
            return RAGAskResponse(
                answer=answer,
                citations=[],
                context_chunks_used=0,
                retrieval_query=payload.query,
                model=settings.hf_model_name,
            )

        answer, _ = HFService.infer(
            prompt=prompt,
            max_new_tokens=payload.max_new_tokens,
            temperature=payload.temperature,
        )

        answer = RAGService._append_citations(answer, citations)

        return RAGAskResponse(
            answer=answer,
            citations=citations,
            context_chunks_used=len(citations),
            retrieval_query=payload.query,
            model=settings.hf_model_name,
        )

    @staticmethod
    def prepare_generation(db: Session, payload: RAGAskRequest) -> tuple[str, list[RAGCitation]]:
        return RAGService._build_prompt_and_citations(db, payload)

    @staticmethod
    def _format_history(history: list[dict[str, str]]) -> str:
        if not history:
            return "No previous turns"

        recent = history[-settings.rag_memory_turns :]
        lines: list[str] = []
        for idx, turn in enumerate(recent, start=1):
            user = turn.get("user", "")
            assistant = turn.get("assistant", "")
            lines.append(f"Turn {idx} user: {user}")
            lines.append(f"Turn {idx} assistant: {assistant}")
        return "\n".join(lines)

    @staticmethod
    def _append_citations(answer: str, citations: list[RAGCitation]) -> str:
        lines: list[str] = [answer.strip(), "", "Fuentes:"]
        for citation in citations:
            location = citation.file_path or "unknown"
            if citation.line_start and citation.line_end:
                location = f"{location}:{citation.line_start}-{citation.line_end}"
            if citation.tab:
                location = f"{location} [tab: {citation.tab}]"
            lines.append(f"- {location}")
        return "\n".join(lines).strip()
